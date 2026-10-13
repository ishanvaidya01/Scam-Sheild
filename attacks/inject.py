"""
attacks/inject.py

Injects synthetic Stealth Ladder attacks (L0 - L4, L3-single) into real recorded sessions.
Genuine traffic is 100% authentic; only the attack is synthetic.
Every injected event is labeled with ground truth:
  - ground_truth: "attack" | "genuine"
  - stealth_level: "L0" | "L1" | "L2" | "L3" | "L4" | "L3-single" | "none"
  - campaign_id: str | None
"""

import os
import sys
import json
import random
import hashlib
import secrets
from typing import List, Dict, Any, Optional

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SESSIONS_DIR = os.path.join(ROOT_DIR, "data", "sessions")
INJECTED_DIR = os.path.join(ROOT_DIR, "data", "injected")
FROZEN_FILE = os.path.join(ROOT_DIR, "eval", "FROZEN.md")

from attacks.attack_generator import AttackGenerator
from scripts.collect_sessions import get_or_create_salt, hash_author


def compute_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def inject_attacks_into_session(
    session_messages: List[Dict[str, Any]],
    stealth_level: str,
    campaign_id: str,
    salt: str,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """
    Blends synthetic campaign messages into real session messages with realistic timing.
    """
    random.seed(seed)
    gen = AttackGenerator()

    if not session_messages:
        return []

    # Sort session messages by timestamp
    session_messages = sorted(session_messages, key=lambda m: m.get("ts_ms", 0))
    start_ts = session_messages[0].get("ts_ms", 1000)
    end_ts = session_messages[-1].get("ts_ms", start_ts + 60000)
    duration_ms = max(end_ts - start_ts, 60000)

    # Label all existing messages as genuine
    combined = []
    for m in session_messages:
        msg = dict(m)
        if "ground_truth" not in msg:
            msg["ground_truth"] = "genuine"
        if "stealth_level" not in msg:
            msg["stealth_level"] = "none"
        combined.append(msg)

    # Generate attack messages
    if stealth_level == "L0":
        raw_attacks = gen.generate_l0_campaign(num_bots=5, burst_messages=10)
        # Burst: all arrive within 5 seconds at the 40% mark of the session
        burst_start = start_ts + int(duration_ms * 0.40)
        for i, att in enumerate(raw_attacks):
            ts = burst_start + random.randint(0, 5000)
            combined.append({
                "session_id": session_messages[0].get("session_id", "session"),
                "msg_id": f"inj_l0_{campaign_id}_{i:03d}",
                "ts_ms": ts,
                "author_hash": hash_author(att["author"], salt),
                "text": att["text"],
                "badges": [],
                "is_reply_or_mention": False,
                "message_type": "text",
                "ground_truth": "attack",
                "stealth_level": "L0",
                "campaign_id": campaign_id,
            })

    elif stealth_level == "L1":
        raw_attacks = gen.generate_l1_campaign(num_bots=6, total_messages=15)
        # 15 messages within 30 seconds
        burst_start = start_ts + int(duration_ms * 0.35)
        for i, att in enumerate(raw_attacks):
            ts = burst_start + random.randint(0, 30000)
            combined.append({
                "session_id": session_messages[0].get("session_id", "session"),
                "msg_id": f"inj_l1_{campaign_id}_{i:03d}",
                "ts_ms": ts,
                "author_hash": hash_author(att["author"], salt),
                "text": att["text"],
                "badges": [],
                "is_reply_or_mention": False,
                "message_type": "text",
                "ground_truth": "attack",
                "stealth_level": "L1",
                "campaign_id": campaign_id,
            })

    elif stealth_level == "L2":
        raw_attacks = gen.generate_l2_campaign(num_bots=8)
        # 8 unique paraphrases over 60 seconds
        burst_start = start_ts + int(duration_ms * 0.45)
        for i, att in enumerate(raw_attacks):
            ts = burst_start + random.randint(0, 60000)
            combined.append({
                "session_id": session_messages[0].get("session_id", "session"),
                "msg_id": f"inj_l2_{campaign_id}_{i:03d}",
                "ts_ms": ts,
                "author_hash": hash_author(att["author"], salt),
                "text": att["text"],
                "badges": [],
                "is_reply_or_mention": False,
                "message_type": "text",
                "ground_truth": "attack",
                "stealth_level": "L2",
                "campaign_id": campaign_id,
            })

    elif stealth_level == "L3":
        raw_attacks = gen.generate_l3_campaign(num_bots=6)
        # Infiltrates stream over 120 seconds with jittered human timing
        attack_start = start_ts + int(duration_ms * 0.30)
        curr_ts = attack_start
        for i, att in enumerate(raw_attacks):
            curr_ts += random.randint(8000, 25000)
            combined.append({
                "session_id": session_messages[0].get("session_id", "session"),
                "msg_id": f"inj_l3_{campaign_id}_{i:03d}",
                "ts_ms": curr_ts,
                "author_hash": hash_author(att["author"], salt),
                "text": att["text"],
                "badges": [],
                "is_reply_or_mention": False,
                "message_type": "text",
                "ground_truth": "attack",
                "stealth_level": "L3",
                "campaign_id": campaign_id,
            })

    elif stealth_level == "L4":
        raw_attacks = gen.generate_l4_campaign(num_accounts=10)
        # Low-and-slow: spread evenly over entire session
        step = max(int(duration_ms / (len(raw_attacks) + 1)), 15000)
        for i, att in enumerate(raw_attacks):
            ts = start_ts + (i + 1) * step + random.randint(-5000, 5000)
            combined.append({
                "session_id": session_messages[0].get("session_id", "session"),
                "msg_id": f"inj_l4_{campaign_id}_{i:03d}",
                "ts_ms": ts,
                "author_hash": hash_author(att["author"], salt),
                "text": att["text"],
                "badges": [],
                "is_reply_or_mention": False,
                "message_type": "text",
                "ground_truth": "attack",
                "stealth_level": "L4",
                "campaign_id": campaign_id,
            })

    elif stealth_level == "L3-single":
        att = gen.generate_l3_single()
        ts = start_ts + int(duration_ms * 0.5)
        combined.append({
            "session_id": session_messages[0].get("session_id", "session"),
            "msg_id": f"inj_l3s_{campaign_id}_001",
            "ts_ms": ts,
            "author_hash": hash_author(att["author"], salt),
            "text": att["text"],
            "badges": [],
            "is_reply_or_mention": False,
            "message_type": "text",
            "ground_truth": "attack",
            "stealth_level": "L3-single",
            "campaign_id": campaign_id,
        })

    # Sort final combined timeline by timestamp
    combined.sort(key=lambda m: m["ts_ms"])
    return combined


def create_injected_dataset(session_file: str, out_prefix: str, split_name: str = "dev"):
    """Creates a suite of injected attack datasets for a session and saves to data/injected/."""
    os.makedirs(INJECTED_DIR, exist_ok=True)
    salt = get_or_create_salt()

    session_messages = []
    with open(session_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                session_messages.append(json.loads(line))

    levels = ["L0", "L1", "L2", "L3", "L4", "L3-single"]
    records = []

    for lvl in levels:
        cid = f"camp_{lvl.lower()}_{split_name}"
        injected = inject_attacks_into_session(session_messages, lvl, cid, salt)
        out_filename = f"{out_prefix}_{split_name}_{lvl}.jsonl"
        out_path = os.path.join(INJECTED_DIR, out_filename)
        
        with open(out_path, "w", encoding="utf-8") as f:
            for item in injected:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        file_hash = compute_sha256(out_path)
        records.append({
            "file": out_filename,
            "split": split_name,
            "stealth_level": lvl,
            "sha256": file_hash,
            "total_messages": len(injected),
            "attack_count": sum(1 for m in injected if m.get("ground_truth") == "attack"),
            "genuine_count": sum(1 for m in injected if m.get("ground_truth") == "genuine"),
        })

    return records
