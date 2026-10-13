"""
coordination_engine.py  (v3 — Bug-fixed + Repetition-aware)

Signal 3 of 5: Coordinated Inauthentic Behavior detection.

v3 fixes vs v2:
  - BUG FIX: Same-user repetition is now detected. Previously, the engine skipped
    same-user messages in both semantic similarity and template matching, making
    it blind to the most common real-world bot pattern: one account posting
    the same message repeatedly.
  - NEW Sub-detector 4: Self-Repetition — detects when this user has posted
    near-identical content in this session. This is a STRONG bot signal.
  - BURST_COUNT_THRESHOLD reduced from 3 to 2 (cross-user coordination).
  - SIMILARITY_THRESHOLD for self-repetition is 0.92 (stricter: must be very close).

Sub-detector 1: Semantic Similarity (cross-user)
  Counts how many DIFFERENT users posted semantically similar content in window.
  Threshold: 2+ different users = coordination flag.

Sub-detector 2: Lexical Template Detection
  Detects fill-in-the-blank template attacks by comparing message skeletons.

Sub-detector 3: Timing Burst (Poisson)
  Statistical test for anomalous message arrival rate.

Sub-detector 4 (NEW): Same-User Repetition
  Detects when this user has already posted the same/near-identical message
  in this session. Checks: exact match, skeleton match, semantic match (≥0.92).
"""

import re
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
SIMILARITY_THRESHOLD         = 0.83   # cross-user cosine similarity threshold
SELF_REPEAT_THRESHOLD        = 0.90   # same-user self-repetition similarity
TIME_WINDOW_SECONDS          = 60     # rolling window size (seconds)
BURST_COUNT_THRESHOLD        = 2      # min DIFFERENT users to flag cross-user coordination (was 3)
TEMPLATE_MATCH_THRESHOLD     = 2      # min accounts sharing a template skeleton
BURST_PVAL_THRESHOLD         = 0.01   # p-value threshold for Poisson burst
MIN_WINDOW_FOR_POISSON       = 5      # minimum messages before Poisson test


# ── Sentence transformer model (lazy-loaded singleton) ────────────────────────
_model = None

def _get_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Loaded sentence-transformer: all-MiniLM-L6-v2")
        except Exception as e:
            logger.warning(f"Failed to load sentence-transformer: {e}")
            _model = False
    return _model if _model is not False else None


# ── Template skeleton extractor ────────────────────────────────────────────────
_SKELETON_SUBS = [
    (re.compile(r"@[\w]{3,}"), "@HANDLE"),
    (re.compile(r"0x[a-fA-F0-9]{40}"), "WALLET"),
    (re.compile(r"[13][a-km-zA-HJ-NP-Z1-9]{25,34}"), "WALLET"),
    (re.compile(r"\b\d+(?:\.\d+)?\s*(?:btc|eth|usdt|usd|sol)\b", re.I), "AMOUNT COIN"),
    (re.compile(r"\$\d+(?:,\d{3})*(?:\.\d+)?"), "AMOUNT"),
    (re.compile(r"\b\d{10,}\b"), "PHONENUMBER"),
    (re.compile(r"https?://\S+|t\.me/\S+|wa\.me/\S+", re.I), "LINK"),
    (re.compile(r"\b\d+\b"), "NUM"),
]

def _extract_skeleton(text: str) -> str:
    skeleton = text.lower().strip()
    for pattern, replacement in _SKELETON_SUBS:
        skeleton = pattern.sub(replacement, skeleton)
    skeleton = re.sub(r"\s+", " ", skeleton).strip()
    return skeleton


def _skeleton_overlap(sk1: str, sk2: str) -> float:
    """Token Jaccard overlap between two skeletons."""
    t1, t2 = set(sk1.split()), set(sk2.split())
    if not t1 or not t2:
        return 0.0
    return len(t1 & t2) / len(t1 | t2)


# ── Poisson burst detector ─────────────────────────────────────────────────────
def _poisson_burst_pval(window: list, current_time_ms: int, window_seconds: int) -> Optional[float]:
    if len(window) < MIN_WINDOW_FOR_POISSON:
        return None
    try:
        from scipy.stats import poisson as scipy_poisson
        oldest_ts = min(c["timestamp"] for c in window)
        elapsed_seconds = max((current_time_ms - oldest_ts) / 1000.0, 1.0)
        cutoff = current_time_ms - (window_seconds * 1000)
        recent_count = sum(1 for c in window if c["timestamp"] >= cutoff)
        baseline_rate = len(window) / elapsed_seconds
        expected = baseline_rate * window_seconds
        if expected < 0.5:
            return None
        pval = 1.0 - scipy_poisson.cdf(recent_count - 1, expected)
        return round(pval, 5)
    except Exception as e:
        logger.debug(f"Poisson test error: {e}")
        return None


def check_coordination(new_comment: dict, recent_window: list) -> dict:
    """
    Runs all 4 coordination sub-detectors.

    Returns:
        {
          "is_coordinated": bool,
          "coordination_score": float  (0=bot, 1=clean),
          "sub_signals": { ... },
          "reason": str | None,
          "new_embedding": tensor | None
        }
    """
    model = _get_model()
    text = new_comment.get("text", "")
    username = new_comment.get("username", "")
    current_time = new_comment.get("timestamp", int(time.time() * 1000))

    new_embedding = None
    reasons_parts: list[str] = []
    penalty = 0.0

    sub_signals = {
        "semantic_similar_count": 0,
        "semantic_similar_users": [],
        "self_repeat_count": 0,       # NEW: how many times this user repeated this message
        "self_repeat_detected": False, # NEW
        "lexical_template_match": False,
        "matched_template": None,
        "timing_burst_pval": None,
        "timing_is_burst": False,
    }

    # ── Compute new embedding once ─────────────────────────────────────────────
    if model and text:
        try:
            new_embedding = model.encode(text, convert_to_tensor=True)
        except Exception as e:
            logger.warning(f"Embedding computation failed: {e}")

    # ── Sub-detector 1: Cross-user semantic similarity ────────────────────────
    # Counts how many DIFFERENT OTHER users posted similar content.
    if new_embedding is not None:
        try:
            from sentence_transformers import util as st_util
            seen_other_users: set[str] = set()
            cross_similar_count = 0

            for past_comment in recent_window:
                past_user = past_comment.get("username", "")
                if past_user == username:
                    continue  # same user handled by sub-detector 4 below
                if past_user in seen_other_users:
                    continue  # already counted this user once

                if "embedding" not in past_comment:
                    try:
                        past_comment["embedding"] = model.encode(
                            past_comment["text"], convert_to_tensor=True
                        )
                    except Exception:
                        continue

                cos_sim = st_util.cos_sim(new_embedding, past_comment["embedding"]).item()
                if cos_sim >= SIMILARITY_THRESHOLD:
                    seen_other_users.add(past_user)
                    cross_similar_count += 1

            sub_signals["semantic_similar_count"] = cross_similar_count
            sub_signals["semantic_similar_users"] = list(seen_other_users)

            # If it's a very short generic question, require a much higher threshold to trigger a bot ring
            is_generic_question = len(text.split()) <= 6 and any(q in text.lower() for q in ['what', 'where', 'anyone', 'how', '?']) and not any(p in text.lower() for p in ['link', 'btc', 'eth', 'profit', 'dm', 'crypto'])
            effective_threshold = BURST_COUNT_THRESHOLD + 3 if is_generic_question else BURST_COUNT_THRESHOLD

            if cross_similar_count >= effective_threshold:
                penalty += 0.60
                reasons_parts.append(
                    f"{cross_similar_count} near-identical messages from different accounts "
                    f"in {TIME_WINDOW_SECONDS}s window — coordinated posting detected."
                )
        except Exception as e:
            logger.warning(f"Cross-user semantic similarity failed: {e}")

    # ── Sub-detector 4 (NEW): Same-user self-repetition ───────────────────────
    # This catches the #1 real-world bot pattern: one account posting
    # the same promotional message over and over.
    if text:
        new_skel = _extract_skeleton(text)
        new_comment["skeleton"] = new_skel
        self_repeat_count = 0

        for past_comment in recent_window:
            if past_comment.get("username", "") != username:
                continue  # only same user

            past_text = past_comment.get("text", "")

            # Method A: exact match (case-insensitive, stripped)
            if past_text.lower().strip() == text.lower().strip():
                self_repeat_count += 1
                continue

            # Method B: skeleton overlap
            past_skel = past_comment.get("skeleton") or _extract_skeleton(past_text)
            past_comment["skeleton"] = past_skel
            if _skeleton_overlap(new_skel, past_skel) >= 0.85 and len(new_skel.split()) >= 4:
                self_repeat_count += 1
                continue

            # Method C: semantic similarity for same-user paraphrased repeats.
            # Compute the past message's embedding if not already done
            # (sub-detector 1 skips same-user messages, so we do it here).
            if new_embedding is not None and model:
                if "embedding" not in past_comment and past_text:
                    try:
                        past_comment["embedding"] = model.encode(
                            past_text, convert_to_tensor=True
                        )
                    except Exception:
                        pass
                if "embedding" in past_comment:
                    try:
                        from sentence_transformers import util as st_util
                        sim = st_util.cos_sim(new_embedding, past_comment["embedding"]).item()
                        if sim >= SELF_REPEAT_THRESHOLD:
                            self_repeat_count += 1
                    except Exception:
                        pass

        sub_signals["self_repeat_count"] = self_repeat_count
        if self_repeat_count >= 1:
            sub_signals["self_repeat_detected"] = True
            # 1 repeat = moderate signal, 2+ = strong signal
            if self_repeat_count >= 2:
                penalty += 0.70
                reasons_parts.append(
                    f"This user has posted the same/near-identical message "
                    f"{self_repeat_count + 1} times — consistent with scripted bot behavior."
                )
            else:
                penalty += 0.40
                reasons_parts.append(
                    "User repeated this message — possible template bot (repeated once so far)."
                )

    # ── Sub-detector 2: Cross-user lexical template detection ────────────────
    if text:
        new_skel = new_comment.get("skeleton") or _extract_skeleton(text)
        skeleton_other_users: set[str] = set()

        for past_comment in recent_window:
            past_user = past_comment.get("username", "")
            if past_user == username:
                continue  # self-repetition is handled above
            if past_user in skeleton_other_users:
                continue

            past_skel = past_comment.get("skeleton") or _extract_skeleton(past_comment.get("text", ""))
            past_comment["skeleton"] = past_skel

            overlap = _skeleton_overlap(new_skel, past_skel)
            if overlap >= 0.80 and len(new_skel.split()) >= 4:
                skeleton_other_users.add(past_user)

        template_match_count = len(skeleton_other_users)
        if template_match_count >= TEMPLATE_MATCH_THRESHOLD:
            sub_signals["lexical_template_match"] = True
            sub_signals["matched_template"] = new_skel
            penalty += 0.45
            reasons_parts.append(
                f"Message matches a template skeleton shared by {template_match_count} "
                "other accounts — template-filling attack detected."
            )

    # ── Sub-detector 3: Timing Burst (Poisson) ────────────────────────────────
    pval = _poisson_burst_pval(recent_window, current_time, TIME_WINDOW_SECONDS)
    sub_signals["timing_burst_pval"] = pval
    if pval is not None and pval < BURST_PVAL_THRESHOLD:
        sub_signals["timing_is_burst"] = True
        penalty += 0.25
        reasons_parts.append(
            f"Statistically anomalous message burst (Poisson p-value={pval:.4f})."
        )

    # ── Final decision ────────────────────────────────────────────────────────
    coordination_score = max(0.0, min(1.0, 1.0 - penalty))
    is_coordinated = penalty >= 0.40

    if new_embedding is not None:
        new_comment["embedding"] = new_embedding

    return {
        "is_coordinated": is_coordinated,
        "coordination_score": coordination_score,
        "sub_signals": sub_signals,
        "reason": "; ".join(reasons_parts) if reasons_parts else None,
        "new_embedding": new_embedding,
    }
