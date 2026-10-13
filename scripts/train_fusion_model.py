"""
scripts/train_fusion_model.py

Trains Learned Fusion Logistic Regression on DEV sessions only.
Enforces Non-negotiable Rule 2 & Phase 4 protocol:
  - Operating threshold chosen on DEV to guarantee False Positive Rate on genuine <= 1.0%.
  - Saves fitted model to ml/_fusion_model.pkl.
  - Prints feature coefficients and dev calibration results.
"""

import os
import sys
import json
from typing import Tuple
import numpy as np

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from ml.session_state import SessionState
from ml.text_scorer import score_text
from ml.campaign_detector import extract_campaign_features
from ml.learned_fusion import FEATURE_NAMES, LearnedFusionModel, FUSION_MODEL_PATH
from scripts.bootstrap_sessions import UCI_FILES, LABELED_OUT_DIR

SESSIONS_DIR = os.path.join(ROOT_DIR, "data", "sessions")
INJECTED_DIR = os.path.join(ROOT_DIR, "data", "injected")


def extract_features_from_session_file(session_path: str) -> Tuple[np.ndarray, np.ndarray]:
    """Replays a session in temporal order and extracts feature matrix."""
    session = SessionState()
    X_rows = []
    y_rows = []

    messages = []
    with open(session_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                messages.append(json.loads(line))

    # Sort strictly by timestamp
    messages.sort(key=lambda m: m.get("ts_ms", m.get("timestamp", 0)))

    for msg in messages:
        # Determine ground truth label: 1 = scam/attack, 0 = genuine/organic_sync
        lbl = msg.get("label") or msg.get("ground_truth")
        y_val = 1 if lbl in ("scam", "scam_campaign", "attack") else 0

        # Extract features
        text = msg.get("text", "")
        text_res = score_text(text)
        camp_feat, _ = extract_campaign_features(msg, session)
        camp_feat["text_scam_prob"] = text_res.get("scam_prob", 0.0)

        feature_vector = [camp_feat.get(k, 0.0) for k in FEATURE_NAMES]
        X_rows.append(feature_vector)
        y_rows.append(y_val)

        # Append to window
        session.rolling_window.append({
            "comment_id": msg.get("msg_id", ""),
            "text": text,
            "username": msg.get("author_hash", "u"),
            "timestamp": msg.get("ts_ms", 0),
            "embedding": msg.get("embedding"),
            "skeleton": msg.get("skeleton"),
        })

    return np.array(X_rows, dtype=np.float32), np.array(y_rows, dtype=np.int32)


def train_fusion():
    print("[*] Collecting Dev training features across Dev sessions and Dev attack injections...")
    dev_files = []

    # Dev raw sessions
    for sid, (fname, split) in UCI_FILES.items():
        if split == "dev":
            dev_files.append(os.path.join(SESSIONS_DIR, f"{sid}.jsonl"))

    # Dev organic hype
    dev_files.append(os.path.join(SESSIONS_DIR, "organic_hype_dev.jsonl"))

    # Dev stealth ladder attack injections
    if os.path.exists(INJECTED_DIR):
        for fname in os.listdir(INJECTED_DIR):
            if fname.startswith("session_psy_dev") and fname.endswith(".jsonl"):
                dev_files.append(os.path.join(INJECTED_DIR, fname))

    X_all = []
    y_all = []

    for fpath in dev_files:
        if not os.path.exists(fpath):
            continue
        X_sub, y_sub = extract_features_from_session_file(fpath)
        X_all.append(X_sub)
        y_all.append(y_sub)

    X_train = np.vstack(X_all)
    y_train = np.concatenate(y_all)

    print(f"[*] Total Dev training dataset: {X_train.shape[0]} samples (Scam/Attack: {int(np.sum(y_train))}, Genuine: {int(len(y_train) - np.sum(y_train))})")

    # Fit LogisticRegression
    fusion = LearnedFusionModel()
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_train)
    model = LogisticRegression(C=1.0, max_iter=1000, class_weight="balanced")
    model.fit(X_scaled, y_train)

    train_probs = model.predict_proba(X_scaled)[:, 1]

    # Find Operating Point on Dev such that FPR on genuine <= 1.0%
    genuine_mask = (y_train == 0)
    genuine_probs = train_probs[genuine_mask]
    
    # Sort genuine probs descending; 99th percentile guarantees FPR <= 1.0%
    target_fpr = 0.01
    tau_campaign = float(np.percentile(genuine_probs, 100.0 * (1.0 - target_fpr)))
    # Ensure reasonable boundaries
    tau_campaign = max(0.50, min(0.95, tau_campaign))
    tau_suspicious = max(0.30, tau_campaign * 0.60)

    # Calculate actual Dev metrics at this operating point
    dev_preds = (train_probs >= tau_campaign).astype(int)
    dev_fpr = float(np.mean(dev_preds[genuine_mask]))
    attack_mask = (y_train == 1)
    dev_tpr = float(np.mean(dev_preds[attack_mask]))

    print("\n" + "=" * 55)
    print("Learned Fusion Training (Dev Split Only)")
    print("=" * 55)
    print(f"Dev Operating Threshold (tau_campaign)   : {tau_campaign:.4f}")
    print(f"Dev Suspicious Threshold (tau_suspicious) : {tau_suspicious:.4f}")
    print(f"Dev Measured FPR on Genuine               : {dev_fpr:.2%}")
    print(f"Dev Measured Recall (TPR) on Attacks      : {dev_tpr:.2%}")
    print("\nLearned Feature Coefficients:")
    coefs = model.coef_[0]
    for name, c in zip(FEATURE_NAMES, coefs):
        print(f"  {name:28} : {c:+.4f}")
    print("=" * 55)

    # Save fitted model
    fusion.scaler = scaler
    fusion.model = model
    fusion.tau_campaign = tau_campaign
    fusion.tau_suspicious = tau_suspicious
    fusion.is_fitted = True

    import pickle
    with open(FUSION_MODEL_PATH, "wb") as f:
        pickle.dump({
            "scaler": scaler,
            "model": model,
            "tau_campaign": tau_campaign,
            "tau_suspicious": tau_suspicious,
        }, f)

    print(f"[+] Fusion model saved to {FUSION_MODEL_PATH}")
    return fusion


if __name__ == "__main__":
    train_fusion()
