"""
ml/fusion.py

Main fusion entry point for Scam Shield.
Connects:
  - Text scoring (ml.text_scorer)
  - Campaign & graph feature extraction (ml.campaign_detector)
  - Learned Logistic Regression fusion (ml.learned_fusion)
  - Top 3 concrete explainability items
"""

import time
import logging
from typing import Dict, Any, Optional

from ml.session_state import SessionState
from ml.text_scorer import score_text
from ml.campaign_detector import extract_campaign_features, MAX_WINDOW_SIZE, WINDOW_SECONDS
from ml.learned_fusion import get_learned_fusion_model

logger = logging.getLogger(__name__)


def clean_window(session: SessionState, current_time_ms: int):
    """Prunes expired comments and bounds rolling window capacity."""
    cutoff = current_time_ms - (WINDOW_SECONDS * 1000)
    session.rolling_window = [
        c for c in session.rolling_window if c.get("timestamp", c.get("ts_ms", 0)) >= cutoff
    ]
    if len(session.rolling_window) > MAX_WINDOW_SIZE:
        session.rolling_window = session.rolling_window[-MAX_WINDOW_SIZE:]


def get_trust_score(comment: Dict[str, Any], session: SessionState) -> Dict[str, Any]:
    """
    Evaluates an incoming live chat comment against session state.
    Returns:
        {
          "comment_id": str,
          "trust_score": float,
          "campaign_prob": float,
          "verdict": "clear" | "suspicious" | "likely_campaign" | "unverifiable",
          "verdict_label": str,
          "unverifiable": bool,
          "reasons": [ { "text": str, "type": str, "signal": str } ],
          "signal_breakdown": dict,
          "session_stats": dict
        }
    """
    text = (comment.get("text") or "").strip()
    username = comment.get("username") or comment.get("author_hash") or "unknown"
    comment_id = str(comment.get("comment_id") or comment.get("msg_id") or "")
    current_ts = int(comment.get("timestamp") or comment.get("ts_ms") or (time.time() * 1000))

    # Maintain window bounds
    clean_window(session, current_ts)

    # 1. User profile tracking
    profile = session.get_or_create_profile(username)
    profile.record_message(text, current_ts)

    # 2. Text intent scoring
    text_result = score_text(text)
    text_scam_prob = text_result.get("scam_prob", 0.0)

    # 3. Campaign & Graph features
    campaign_features, cluster_meta = extract_campaign_features(comment, session)

    # Combine text intent into feature vector
    campaign_features["text_scam_prob"] = text_scam_prob

    # 4. Learned Fusion
    fusion_model = get_learned_fusion_model()
    fusion_output = fusion_model.score_features(campaign_features, cluster_meta)

    # Update session rolling window
    comment_entry = {
        "comment_id": comment_id,
        "text": text,
        "username": username,
        "timestamp": current_ts,
        "embedding": comment.get("embedding"),
        "skeleton": comment.get("skeleton"),
    }
    session.rolling_window.append(comment_entry)

    # Session stats
    session.total_scanned += 1
    verdict = fusion_output["verdict"]
    if verdict == "likely_campaign":
        session.total_scam += 1
        session.total_flagged += 1
    elif verdict == "suspicious":
        session.total_flagged += 1

    return {
        "comment_id": comment_id,
        "trust_score": fusion_output["trust_score"],
        "campaign_prob": fusion_output["campaign_prob"],
        "verdict": verdict,
        "verdict_label": fusion_output["verdict_label"],
        "unverifiable": fusion_output["unverifiable"],
        "reasons": fusion_output["reasons"],
        "signal_breakdown": {
            "text_scam_prob": round(text_scam_prob, 3),
            "cluster_cohesion": round(campaign_features.get("cluster_cohesion", 0.0), 3),
            "rate_normalized_synchrony": round(campaign_features.get("rate_normalized_synchrony", 0.0), 3),
            "off_topic_distance": round(campaign_features.get("off_topic_distance", 0.0), 3),
            "skeleton_reuse": round(campaign_features.get("skeleton_reuse_ratio", 0.0), 3),
        },
        "session_stats": {
            "total_scanned": session.total_scanned,
            "total_flagged": session.total_flagged,
            "total_scam": session.total_scam,
        },
    }
