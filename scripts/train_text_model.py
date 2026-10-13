"""
scripts/train_text_model.py

Trains char n-gram TF-IDF + Logistic Regression on DEV sessions (split by video)
and evaluates on held-out TEST sessions (split by video).
Reports honest PR-AUC, ROC-AUC, F1, Precision, and Recall.
"""

import os
import sys
import json
import numpy as np
from sklearn.metrics import (
    precision_score, recall_score, f1_score,
    precision_recall_curve, auc, roc_auc_score, classification_report
)

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from ml.text_intent import TextIntentClassifier, MODEL_PATH
from scripts.bootstrap_sessions import UCI_FILES, LABELED_OUT_DIR


def load_split_data(split_target: str):
    texts, labels = [], []
    for sid, (fname, split) in UCI_FILES.items():
        if split != split_target:
            continue
        lpath = os.path.join(LABELED_OUT_DIR, f"{sid}_ann1_labeled.jsonl")
        if not os.path.exists(lpath):
            continue
        with open(lpath, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    txt = item.get("text", "")
                    lbl = 1 if item.get("label") == "scam_campaign" else 0
                    texts.append(txt)
                    labels.append(lbl)
    return texts, labels


def train_and_eval():
    train_texts, train_labels = load_split_data("dev")
    test_texts, test_labels = load_split_data("test")

    print(f"[*] Training on DEV sessions ({len(train_texts)} samples)...")
    clf = TextIntentClassifier()
    clf.fit(train_texts, train_labels)

    print(f"[*] Evaluating on held-out TEST sessions ({len(test_texts)} samples)...")
    test_probs = [clf.predict_proba(t) for t in test_texts]
    test_preds = [1 if p >= 0.50 else 0 for p in test_probs]

    p = precision_score(test_labels, test_preds, zero_division=0)
    r = recall_score(test_labels, test_preds, zero_division=0)
    f1 = f1_score(test_labels, test_preds, zero_division=0)
    roc = roc_auc_score(test_labels, test_probs)

    precision_pts, recall_pts, _ = precision_recall_curve(test_labels, test_probs)
    pr_auc = auc(recall_pts, precision_pts)

    print("\n" + "=" * 50)
    print("Text-Intent Classifier (Char n-gram + LogReg)")
    print("Held-out TEST Sessions Evaluation")
    print("=" * 50)
    print(f"Precision : {p:.4f}")
    print(f"Recall    : {r:.4f}")
    print(f"F1 Score  : {f1:.4f}")
    print(f"ROC-AUC   : {roc:.4f}")
    print(f"PR-AUC    : {pr_auc:.4f}")
    print("=" * 50)

    return {
        "precision": p,
        "recall": r,
        "f1": f1,
        "roc_auc": roc,
        "pr_auc": pr_auc,
        "train_samples": len(train_texts),
        "test_samples": len(test_texts),
    }


if __name__ == "__main__":
    train_and_eval()
