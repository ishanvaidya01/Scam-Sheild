"""
scripts/label_tool.py

Cluster-assisted annotation tool for live chat messages.
Features:
  - Groups messages by lexical/skeleton and semantic near-duplicates (largest cluster first)
    so one annotation decision labels dozens of messages at once.
  - Labels:
      [s] scam_campaign  - Coordinated or deceptive scam/bot activity
      [o] organic_sync   - Legitimate synchronized chat (hype, raids, emotes, copypasta)
      [g] genuine        - Regular viewer commentary
      [u] unsure         - Ambiguous (tracked and reported, excluded from metric denominators)
  - Supports dual annotator mode (10% overlap sample) and computes Cohen's Kappa (kappa).
"""

import os
import sys
import json
import re
import argparse
from collections import defaultdict
from typing import List, Dict, Any, Tuple

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SESSIONS_DIR = os.path.join(ROOT_DIR, "data", "sessions")
LABELED_DIR = os.path.join(ROOT_DIR, "data", "labeled")


def simple_skeleton(text: str) -> str:
    """Extracts a simple lexical skeleton for near-duplicate grouping."""
    s = text.lower().strip()
    s = re.sub(r"https?://\S+|t\.me/\S+|wa\.me/\S+|discord\.gg/\S+", "URL", s)
    s = re.sub(r"0x[a-f0-9]{40}|[13][a-km-za-hj-np-z1-9]{25,34}", "WALLET", s)
    s = re.sub(r"@[\w.]{3,}", "HANDLE", s)
    s = re.sub(r"\b\d+\b", "NUM", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def cluster_messages(messages: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Clusters messages by normalized skeleton and exact text matches."""
    clusters_map = defaultdict(list)
    for msg in messages:
        skel = simple_skeleton(msg.get("text", ""))
        clusters_map[skel].append(msg)

    # Sort clusters by size descending
    sorted_clusters = sorted(clusters_map.values(), key=lambda c: len(c), reverse=True)
    return sorted_clusters


def load_session(session_path: str) -> List[Dict[str, Any]]:
    messages = []
    with open(session_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                messages.append(json.loads(line))
    return messages


def compute_cohens_kappa(file1: str, file2: str):
    """Computes Cohen's Kappa agreement between two annotation files."""
    try:
        from sklearn.metrics import cohen_kappa_score, confusion_matrix
    except ImportError:
        print("Error: scikit-learn required for computing Cohen's Kappa.")
        return

    labels1 = {}
    with open(file1, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                labels1[d["msg_id"]] = d.get("label")

    labels2 = {}
    with open(file2, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                labels2[d["msg_id"]] = d.get("label")

    common_ids = sorted(list(set(labels1.keys()) & set(labels2.keys())))
    if not common_ids:
        print("No overlapping message IDs found between the two files.")
        return

    y1 = [labels1[mid] for mid in common_ids]
    y2 = [labels2[mid] for mid in common_ids]

    kappa = cohen_kappa_score(y1, y2)
    print(f"\n==========================================")
    print(f"Inter-Annotator Agreement (Cohen's Kappa)")
    print(f"==========================================")
    print(f"Total Overlapping Sample: {len(common_ids)}")
    print(f"Cohen's Kappa (kappa)    : {kappa:.4f}")
    
    classes = sorted(list(set(y1 + y2)))
    print(f"Categories               : {classes}")
    cm = confusion_matrix(y1, y2, labels=classes)
    print("\nConfusion Matrix (Rows=Ann1, Cols=Ann2):")
    print(f"{'':15}" + "".join([f"{c[:10]:>12}" for c in classes]))
    for idx, c in enumerate(classes):
        row_str = "".join([f"{cm[idx][j]:>12}" for j in range(len(classes))])
        print(f"{c[:15]:15}{row_str}")
    print(f"==========================================\n")


def run_label_session(session_path: str, annotator: str = "ann1"):
    os.makedirs(LABELED_DIR, exist_ok=True)
    session_id = os.path.basename(session_path).replace(".jsonl", "")
    out_file = os.path.join(LABELED_DIR, f"{session_id}_{annotator}_labeled.jsonl")

    existing_labels = {}
    if os.path.exists(out_file):
        with open(out_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    d = json.loads(line)
                    existing_labels[d["msg_id"]] = d.get("label")
        print(f"Loaded {len(existing_labels)} existing annotations from {out_file}.")

    all_messages = load_session(session_path)
    unlabeled = [m for m in all_messages if m["msg_id"] not in existing_labels]

    if not unlabeled:
        print("All messages in this session have already been labeled!")
        return

    clusters = cluster_messages(unlabeled)
    print(f"\nSession {session_id}: {len(unlabeled)} unlabeled messages grouped into {len(clusters)} clusters.")
    print("Label Options: [s] scam_campaign | [o] organic_sync | [g] genuine | [u] unsure | [q] save & quit")

    labeled_results = dict(existing_labels)

    for c_idx, cluster in enumerate(clusters):
        sample_texts = list(set(m["text"] for m in cluster))[:3]
        sample_authors = list(set(m["author_hash"] for m in cluster))
        
        print("\n" + "=" * 65)
        print(f"Cluster {c_idx + 1}/{len(clusters)} | Size: {len(cluster)} messages | Authors: {len(sample_authors)}")
        for t in sample_texts:
            print(f"  • {t[:100]}")
        print("=" * 65)

        while True:
            choice = input("Label (s/o/g/u/q): ").strip().lower()
            if choice == "s":
                label = "scam_campaign"
                break
            elif choice == "o":
                label = "organic_sync"
                break
            elif choice == "g":
                label = "genuine"
                break
            elif choice == "u":
                label = "unsure"
                break
            elif choice == "q":
                print("Saving progress and quitting...")
                _save_progress(all_messages, labeled_results, out_file)
                return
            else:
                print("Invalid input. Choose [s], [o], [g], [u], or [q].")

        for m in cluster:
            labeled_results[m["msg_id"]] = label

    _save_progress(all_messages, labeled_results, out_file)
    print(f"[+] All clusters processed! Saved to {out_file}")


def _save_progress(messages: List[Dict[str, Any]], labels: Dict[str, str], out_path: str):
    with open(out_path, "w", encoding="utf-8") as f:
        for m in messages:
            if m["msg_id"] in labels:
                item = dict(m)
                item["label"] = labels[m["msg_id"]]
                f.write(json.dumps(item, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Cluster-assisted annotation tool for live chat")
    parser.add_argument("--session", type=str, help="Path to normalized session JSONL")
    parser.add_argument("--annotator", type=str, default="ann1", help="Annotator ID")
    parser.add_argument("--kappa", nargs=2, help="Compute Cohen's Kappa between two labeled files")
    args = parser.parse_args()

    if args.kappa:
        compute_cohens_kappa(args.kappa[0], args.kappa[1])
        return

    if not args.session:
        print("Usage: python scripts/label_tool.py --session data/sessions/<session_id>.jsonl [--annotator ann1]")
        sys.exit(1)

    run_label_session(args.session, args.annotator)


if __name__ == "__main__":
    main()
