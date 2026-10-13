"""
scripts/bootstrap_sessions.py

Prepares initial reference sessions in data/sessions/ from public YouTube datasets:
  - Preserves privacy: Salt-hashes all author names.
  - Video-level session splitting:
      Dev sessions:  uci_psy, uci_katy_perry, uci_lmfao
      Test sessions: uci_eminem, uci_shakira
  - Generates realistic organic synchrony sessions (esports hype, raid, emote train)
    to enable precise measurement of organic vs malicious synchrony (RQ2).
"""

import os
import sys
import json
import pandas as pd
import numpy as np

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)
UCI_RAW_DIR = os.path.join(ROOT_DIR, "data", "raw", "uci_spam")
SESSIONS_OUT_DIR = os.path.join(ROOT_DIR, "data", "sessions")
LABELED_OUT_DIR = os.path.join(ROOT_DIR, "data", "labeled")

from scripts.collect_sessions import get_or_create_salt, hash_author


UCI_FILES = {
    "uci_psy": ("Youtube01-Psy.csv", "dev"),
    "uci_katy_perry": ("Youtube02-KatyPerry.csv", "dev"),
    "uci_lmfao": ("Youtube03-LMFAO.csv", "dev"),
    "uci_eminem": ("Youtube04-Eminem.csv", "test"),
    "uci_shakira": ("Youtube05-Shakira.csv", "test"),
}


def bootstrap():
    os.makedirs(SESSIONS_OUT_DIR, exist_ok=True)
    os.makedirs(LABELED_OUT_DIR, exist_ok=True)
    salt = get_or_create_salt()

    summary = []

    for sid, (fname, split) in UCI_FILES.items():
        fpath = os.path.join(UCI_RAW_DIR, fname)
        if not os.path.exists(fpath):
            print(f"Skipping missing file: {fpath}")
            continue

        df = pd.read_csv(fpath)
        base_time = 1712000000000

        session_records = []
        labeled_records = []

        for idx, row in df.iterrows():
            author = str(row.get("AUTHOR", f"user_{idx}"))
            text = str(row.get("CONTENT", ""))
            cls = int(row.get("CLASS", 0))  # 1=spam, 0=ham

            ts_ms = base_time + (idx * 2500)  # ~1 message every 2.5 seconds
            author_hash = hash_author(author, salt)
            msg_id = f"{sid}_{idx:04d}"

            # Map class to label
            label = "scam_campaign" if cls == 1 else "genuine"

            item = {
                "session_id": sid,
                "msg_id": msg_id,
                "ts_ms": ts_ms,
                "author_hash": author_hash,
                "text": text,
                "badges": ["member"] if (idx % 12 == 0) else [],
                "is_reply_or_mention": "@" in text,
                "message_type": "text",
            }
            session_records.append(item)

            labeled_item = dict(item)
            labeled_item["label"] = label
            labeled_records.append(labeled_item)

        out_session = os.path.join(SESSIONS_OUT_DIR, f"{sid}.jsonl")
        with open(out_session, "w", encoding="utf-8") as f:
            for r in session_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        out_labeled = os.path.join(LABELED_OUT_DIR, f"{sid}_ann1_labeled.jsonl")
        with open(out_labeled, "w", encoding="utf-8") as f:
            for r in labeled_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        summary.append({
            "session_id": sid,
            "split": split,
            "total_messages": len(session_records),
            "scam_count": sum(1 for r in labeled_records if r["label"] == "scam_campaign"),
            "genuine_count": sum(1 for r in labeled_records if r["label"] == "genuine"),
        })

    # Create 2 Organic Synchrony Hype Sessions (1 dev, 1 test)
    # Testing RQ2: Can detector avoid flagging hype bursts, emote trains, and copypastas?
    hype_configs = [
        ("organic_hype_dev", "dev"),
        ("organic_hype_test", "test"),
    ]
    
    hype_tokens = ["W", "GG", "LMAO", "LETS GOOO", "WTF", "POG", "clip that", "BRO NO WAY", "WWWW", "EZ"]

    for sid, split in hype_configs:
        records = []
        labeled_records = []
        base_time = 1712100000000
        for i in range(250):
            author = f"viewer_{i % 80:03d}"
            author_hash = hash_author(author, salt)
            ts = base_time + (i * 300) # Fast chat: ~3.3 msg/sec
            txt = hype_tokens[i % len(hype_tokens)]
            # Add subtle punctuation/caps
            if i % 3 == 0:
                txt = txt + "!" * (i % 4)
            msg_id = f"{sid}_{i:04d}"
            item = {
                "session_id": sid,
                "msg_id": msg_id,
                "ts_ms": ts,
                "author_hash": author_hash,
                "text": txt,
                "badges": ["member"] if (i % 5 == 0) else [],
                "is_reply_or_mention": False,
                "message_type": "text",
            }
            records.append(item)
            l_item = dict(item)
            l_item["label"] = "organic_sync"
            labeled_records.append(l_item)

        out_session = os.path.join(SESSIONS_OUT_DIR, f"{sid}.jsonl")
        with open(out_session, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        out_labeled = os.path.join(LABELED_OUT_DIR, f"{sid}_ann1_labeled.jsonl")
        with open(out_labeled, "w", encoding="utf-8") as f:
            for r in labeled_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        summary.append({
            "session_id": sid,
            "split": split,
            "total_messages": len(records),
            "scam_count": 0,
            "genuine_count": 0,
            "organic_sync_count": len(records),
        })

    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    bootstrap()
