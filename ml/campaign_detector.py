"""
ml/campaign_detector.py

Unified Campaign Detector for Scam Shield.
Replaces legacy coordination_engine and network_analyzer.
Features:
  - Vectorized embedding cosine similarity (all-MiniLM-L6-v2) with LRU cache.
  - Time-decayed sliding window graph.
  - Rate-normalized synchrony (prevents flagging organic hype spikes).
  - Stream topic centroid divergence (off-topicness).
  - Explicit organic-vs-malicious synchrony separation.
"""

import re
import time
import hashlib
import logging
from typing import List, Dict, Any, Tuple, Optional
import numpy as np

from ml.session_state import SessionState, UserProfile
from ml.intent_rules import match_intent_rules

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.80
WINDOW_SECONDS = 60
MAX_WINDOW_SIZE = 350
EMBEDDING_DIM = 384

# ── Lazy-loaded SentenceTransformer Model ────────────────────────────────────
_st_model = None
_model_failed = False

def get_sentence_model():
    global _st_model, _model_failed
    if _st_model is None and not _model_failed:
        try:
            from sentence_transformers import SentenceTransformer
            _st_model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("SentenceTransformer all-MiniLM-L6-v2 loaded.")
        except Exception as e:
            logger.warning(f"Could not load SentenceTransformer: {e}")
            _model_failed = True
    return _st_model


# ── LRU Embedding Cache ──────────────────────────────────────────────────────
_EMB_CACHE: Dict[str, np.ndarray] = {}
_EMB_CACHE_MAX = 1000

def _get_embedding(text: str) -> np.ndarray:
    if not text:
        return np.zeros(EMBEDDING_DIM, dtype=np.float32)
    key = hashlib.md5(text.lower().strip().encode("utf-8")).hexdigest()[:16]
    if key in _EMB_CACHE:
        return _EMB_CACHE[key]

    model = get_sentence_model()
    if model is not None:
        try:
            vec = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
            if len(_EMB_CACHE) >= _EMB_CACHE_MAX:
                _EMB_CACHE.pop(next(iter(_EMB_CACHE)))
            _EMB_CACHE[key] = vec.astype(np.float32)
            return _EMB_CACHE[key]
        except Exception as e:
            logger.debug(f"Embedding encoding failed: {e}")

    # Fallback deterministic pseudo-embedding if model fails
    rng = np.random.default_rng(int(key, 16) % (2**32))
    vec = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    _EMB_CACHE[key] = vec
    return vec


# ── Skeleton Helper ──────────────────────────────────────────────────────────
_SKELETON_SUBS = [
    (re.compile(r"@[\w.]{3,}"), "@HANDLE"),
    (re.compile(r"0x[a-fA-F0-9]{40}|[13][a-km-zA-HJ-NP-Z1-9]{25,34}"), "WALLET"),
    (re.compile(r"https?://\S+|t\.me/\S+|wa\.me/\S+|discord\.gg/\S+", re.I), "LINK"),
    (re.compile(r"\b\d+\b"), "NUM"),
]

def extract_skeleton(text: str) -> str:
    s = text.lower().strip()
    for pat, rep in _SKELETON_SUBS:
        s = pat.sub(rep, s)
    return re.sub(r"\s+", " ", s).strip()


def skeleton_jaccard(s1: str, s2: str) -> float:
    t1, t2 = set(s1.split()), set(s2.split())
    if not t1 or not t2:
        return 0.0
    return len(t1 & t2) / len(t1 | t2)


# ── Campaign Feature Extractor ───────────────────────────────────────────────

def extract_campaign_features(
    new_comment: Dict[str, Any],
    session: SessionState,
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """
    Extracts multi-signal campaign features for learned fusion.
    Returns:
        (features_dict, cluster_metadata)
    """
    text = (new_comment.get("text") or "").strip()
    username = new_comment.get("username") or new_comment.get("author_hash") or "unknown"
    current_ts = new_comment.get("timestamp") or new_comment.get("ts_ms") or int(time.time() * 1000)
    badges = new_comment.get("badges") or []
    is_trusted = 1.0 if any(b in ("member", "moderator", "verified") for b in badges) else 0.0

    # User profile lookup
    profile = session.get_or_create_profile(username)
    first_seen_delta_sec = (current_ts - (profile.first_message_ts or current_ts)) / 1000.0
    account_msg_count = float(profile.total_messages)

    # Text intent rules
    rule_res = match_intent_rules(text)
    intent_hit_count = float(rule_res["hit_count"])
    has_rule_hit = 1.0 if rule_res["has_intent_rule_hit"] else 0.0

    # Get new embedding
    emb = _get_embedding(text)
    new_skel = extract_skeleton(text)

    # Rolling window messages
    window = session.rolling_window
    window_count = len(window)

    if window_count == 0:
        # First message in session
        features = {
            "cluster_account_count": 1.0,
            "cluster_cohesion": 1.0,
            "rate_normalized_synchrony": 0.0,
            "off_topic_distance": 0.0,
            "skeleton_reuse_ratio": 0.0,
            "account_first_seen_delta": first_seen_delta_sec,
            "account_msg_count": account_msg_count,
            "is_trusted_badge": is_trusted,
            "intent_rules_hit": has_rule_hit,
            "is_organic_hype_pattern": 0.0,
        }
        meta = {"cluster_accounts": [username], "cluster_size": 1, "is_cluster": False}
        return features, meta

    # Vectorized similarity against rolling window
    emb_list = []
    for w in window:
        w_emb = w.get("embedding")
        if w_emb is None or not isinstance(w_emb, np.ndarray) or w_emb.shape != (EMBEDDING_DIM,):
            w_emb = _get_embedding(w.get("text", ""))
            w["embedding"] = w_emb
        emb_list.append(w_emb)
    E = np.vstack(emb_list)  # (N, 384)
    sims = np.dot(E, emb)   # Cosine similarity vector

    # Overall chat velocity (msgs/sec)
    oldest_ts = min(w.get("timestamp", current_ts) for w in window)
    elapsed_sec = max((current_ts - oldest_ts) / 1000.0, 1.0)
    overall_chat_rate = window_count / elapsed_sec

    # Cluster: window messages with similarity >= threshold
    cluster_indices = np.where(sims >= SIMILARITY_THRESHOLD)[0]
    cluster_msgs = [window[idx] for idx in cluster_indices]
    cluster_sims = sims[cluster_indices]

    # Distinct accounts in cluster (excluding this account if multiple)
    cluster_accounts = set(w.get("username", "") for w in cluster_msgs)
    cluster_accounts.add(username)
    distinct_accounts_count = float(len(cluster_accounts))

    # Cluster cohesion
    cluster_cohesion = float(np.mean(cluster_sims)) if len(cluster_sims) > 0 else 0.0

    # Cluster velocity (msgs/sec)
    cluster_arrival_rate = len(cluster_msgs) / elapsed_sec
    # Rate-normalized synchrony: ratio of cluster rate to background rate
    rate_normalized_synchrony = float(cluster_arrival_rate / (overall_chat_rate + 0.05))

    # Stream centroid & off-topic distance
    stream_centroid = np.mean(E, axis=0)
    norm_centroid = np.linalg.norm(stream_centroid)
    if norm_centroid > 0:
        stream_centroid /= norm_centroid
    topic_similarity = float(np.dot(stream_centroid, emb))
    off_topic_distance = float(max(0.0, 1.0 - topic_similarity))

    # Skeleton reuse ratio
    skel_matches = 0
    for w in window:
        w_skel = w.get("skeleton") or extract_skeleton(w.get("text", ""))
        w["skeleton"] = w_skel
        if skeleton_jaccard(new_skel, w_skel) >= 0.75:
            skel_matches += 1
    skeleton_reuse = float(skel_matches / max(window_count, 1))

    # Organic Hype Detection (RQ2):
    # Characteristics of organic hype:
    #   - Short text (<= 10 chars, e.g. "W", "GG", "LMAO", "clip that")
    #   - High overall chat rate (burst across whole stream)
    #   - Many distinct accounts (broad community participation)
    #   - Zero intent rule hits (no links, handles, wallets, DMs)
    #   - Low off-topic distance (matches chat topic flow)
    is_short_text = len(text) <= 12
    is_broad_burst = distinct_accounts_count >= 3 and overall_chat_rate >= 1.5
    is_clean = (has_rule_hit == 0.0)
    is_organic_hype = 1.0 if (is_short_text and is_broad_burst and is_clean) else 0.0

    # Cache embedding in comment payload for window reuse
    new_comment["embedding"] = emb
    new_comment["skeleton"] = new_skel

    features = {
        "cluster_account_count": distinct_accounts_count,
        "cluster_cohesion": cluster_cohesion,
        "rate_normalized_synchrony": rate_normalized_synchrony,
        "off_topic_distance": off_topic_distance,
        "skeleton_reuse_ratio": skeleton_reuse,
        "account_first_seen_delta": first_seen_delta_sec,
        "account_msg_count": account_msg_count,
        "is_trusted_badge": is_trusted,
        "intent_rules_hit": has_rule_hit,
        "is_organic_hype_pattern": is_organic_hype,
    }

    meta = {
        "cluster_accounts": list(cluster_accounts),
        "cluster_size": len(cluster_msgs) + 1,
        "is_cluster": distinct_accounts_count >= 2,
    }

    return features, meta
