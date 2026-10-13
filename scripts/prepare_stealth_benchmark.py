"""
scripts/prepare_stealth_benchmark.py

Generates frozen injected attack benchmarks across all stealth levels (L0-L4, L3-single)
for held-out Dev and Test sessions, and records their cryptographic SHA-256 hashes in eval/FROZEN.md.
"""

import os
import sys
import json
import hashlib

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from attacks.inject import create_injected_dataset, compute_sha256

SESSIONS_DIR = os.path.join(ROOT_DIR, "data", "sessions")
EVAL_DIR = os.path.join(ROOT_DIR, "eval")
FROZEN_MD = os.path.join(EVAL_DIR, "FROZEN.md")


def prepare_benchmark():
    os.makedirs(EVAL_DIR, exist_ok=True)

    # 1. Dev Injections
    psy_session = os.path.join(SESSIONS_DIR, "uci_psy.jsonl")
    dev_records = create_injected_dataset(psy_session, out_prefix="session_psy", split_name="dev")

    # 2. Test Injections
    eminem_session = os.path.join(SESSIONS_DIR, "uci_eminem.jsonl")
    test_records = create_injected_dataset(eminem_session, out_prefix="session_eminem", split_name="test")

    # Hashes of raw session files
    session_hashes = {}
    for fname in sorted(os.listdir(SESSIONS_DIR)):
        if fname.endswith(".jsonl"):
            fpath = os.path.join(SESSIONS_DIR, fname)
            session_hashes[fname] = compute_sha256(fpath)

    # Write eval/FROZEN.md
    lines = [
        "# Frozen Test Split & Adversarial Benchmark Hashes\n\n",
        "> Non-negotiable Rule 2: Dev/test splits are by SESSION (stream). ",
        "The test split and the red-team attack set are frozen before any detector tuning; ",
        "hashes are recorded below.\n\n",
        "## 1. Frozen Raw & Labeled Session Datasets\n\n",
        "| Session File | Split | SHA-256 Checksum |\n",
        "|---|---|---|\n",
    ]

    for fname, h in session_hashes.items():
        split = "test" if ("eminem" in fname or "shakira" in fname or "test" in fname) else "dev"
        lines.append(f"| `{fname}` | {split} | `{h}` |\n")

    lines.append("\n## 2. Frozen Test Attack Injections (Stealth Ladder)\n\n")
    lines.append("| Injected Dataset | Stealth Level | Attack Messages | Genuine Messages | SHA-256 Checksum |\n")
    lines.append("|---|---|---|---|---|\n")

    for r in test_records:
        lines.append(
            f"| `{r['file']}` | {r['stealth_level']} | {r['attack_count']} | {r['genuine_count']} | `{r['sha256']}` |\n"
        )

    lines.append("\n## 3. Dev Attack Injections (For Operating Point & Ablation Tuning)\n\n")
    lines.append("| Injected Dataset | Stealth Level | Attack Messages | Genuine Messages | SHA-256 Checksum |\n")
    lines.append("|---|---|---|---|---|\n")

    for r in dev_records:
        lines.append(
            f"| `{r['file']}` | {r['stealth_level']} | {r['attack_count']} | {r['genuine_count']} | `{r['sha256']}` |\n"
        )

    with open(FROZEN_MD, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"[+] Frozen hashes recorded in {FROZEN_MD}")
    return dev_records, test_records


if __name__ == "__main__":
    prepare_benchmark()
