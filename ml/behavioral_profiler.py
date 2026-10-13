"""
behavioral_profiler.py  (v3)

Signal 4 of 5: Per-user in-session behavioral analysis.

v3 adds:
  - Self-similarity signal: detects when a user's current message is nearly
    identical to their own recent messages (word-level Jaccard similarity).
    This is the most direct indicator of a script-driven bot.
  - Reduced threshold for first-message promo penalty (now fired on 1+ promo token).

Key signals:
  - Message velocity
  - Type-Token Ratio (low = template recycling)
  - Per-message self-similarity to user's own recent messages (NEW)
  - First-message-in-session risk
  - Username structural pattern
  - Prior flagging history
"""

import re
import math
import logging
from ml.session_state import UserProfile

logger = logging.getLogger(__name__)

_SEQUENTIAL_DIGITS_RE = re.compile(r"\d{4,}")
_RANDOM_ALPHANUM_RE = re.compile(r"[A-Za-z]\d[A-Za-z]\d|[0-9]{3,}[a-z]")


def _username_entropy(username: str) -> float:
    if not username:
        return 0.0
    freq: dict = {}
    for ch in username.lower():
        freq[ch] = freq.get(ch, 0) + 1
    total = len(username)
    return -sum((c / total) * math.log2(c / total) for c in freq.values())


def _score_username(username: str) -> float:
    """
    Returns a risk score [0.0=risky, 1.0=genuine] based on structural properties.
    Bots tend to have: high digit density, high entropy, alternating patterns.
    """
    if not username:
        return 0.5
    username_body = re.sub(r"[_\-\s]", "", username)
    length = len(username_body)
    if length < 4:
        return 0.8

    digit_count = sum(c.isdigit() for c in username_body)
    digit_ratio = digit_count / length
    entropy = _username_entropy(username_body)
    risk = 0.0

    if digit_ratio > 0.40:
        risk += 0.35
    if entropy > 3.5 and length > 12:
        risk += 0.30
    if _SEQUENTIAL_DIGITS_RE.search(username):
        risk += 0.20
    if _RANDOM_ALPHANUM_RE.search(username):
        risk += 0.15
    if length > 20 and digit_ratio > 0.25:
        risk += 0.15

    return 1.0 - min(risk, 0.95)


def _word_jaccard(a: str, b: str) -> float:
    """Word-level Jaccard similarity between two strings."""
    set_a = set(a.lower().split())
    set_b = set(b.lower().split())
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _self_similarity_score(current_text: str, past_texts: list[str]) -> tuple[float, int]:
    """
    Returns (max_similarity, count_similar) for the current message vs
    the user's past messages. Uses word-level Jaccard similarity.
    'similar' means Jaccard >= 0.70 and message has >= 4 words.
    """
    if len(current_text.split()) < 4:
        return 0.0, 0  # too short to be meaningful
    similar_count = 0
    max_sim = 0.0
    for past in past_texts[-20:]:  # only look at last 20 messages for efficiency
        sim = _word_jaccard(current_text, past)
        if sim > max_sim:
            max_sim = sim
        if sim >= 0.70:
            similar_count += 1
    return max_sim, similar_count


def analyze_behavior(comment: dict, user_profile: UserProfile) -> dict:
    """
    Analyzes behavioral signals for the user who authored this comment.
    """
    reasons: list[str] = []
    penalty = 0.0

    username = comment.get("username", "")
    text = comment.get("text", "")

    # ── Message velocity ──────────────────────────────────────────────────────
    msg_velocity = user_profile.get_velocity(window_seconds=60)
    if msg_velocity >= 12:
        penalty += 0.40
        reasons.append(
            f"Extremely high message velocity: {msg_velocity} messages in the last 60s "
            "(bot-level rate)."
        )
    elif msg_velocity >= 7:
        penalty += 0.20
        reasons.append(
            f"High message velocity: {msg_velocity} messages in the last 60s."
        )
    elif msg_velocity >= 4:
        penalty += 0.08

    # ── Self-similarity: does THIS message look like the user's past messages? ─
    # This is the most direct bot signal: same user, same text, over and over.
    past_texts = user_profile.message_texts[:-1]  # exclude the current message (already recorded)
    if past_texts:
        max_sim, similar_count = _self_similarity_score(text, past_texts)
        if similar_count >= 2:
            penalty += 0.95
            reasons.append(
                f"This message is nearly identical to {similar_count} of this user's "
                f"previous messages in this session (similarity={max_sim:.0%}) — "
                "scripted repetition detected."
            )
        elif similar_count == 1:
            penalty += 0.65
            reasons.append(
                f"This message closely matches a previous message by this user "
                f"(similarity={max_sim:.0%}) — possible template bot."
            )

    # ── Type-Token Ratio (vocabulary diversity) ───────────────────────────────
    ttr = user_profile.get_type_token_ratio()
    is_first_message = user_profile.is_first_message()

    if not is_first_message and ttr < 0.25 and user_profile.total_messages >= 3:
        penalty += 0.30
        reasons.append(
            f"Very low vocabulary diversity (TTR={ttr:.2f}) across this user's messages "
            "— consistent with template-based bot messaging."
        )
    elif not is_first_message and ttr < 0.40 and user_profile.total_messages >= 5:
        penalty += 0.15
        reasons.append(
            f"Low vocabulary diversity (TTR={ttr:.2f}) — possible message template recycling."
        )

    # ── First-message promotional risk ───────────────────────────────────────
    if is_first_message:
        promo_keywords = {
            "dm", "message", "send", "invest", "earn", "profit",
            "win", "won", "giveaway", "bitcoin", "btc", "eth", "crypto",
            "telegram", "whatsapp", "contact"
        }
        if promo_keywords & set(text.lower().split()):
            penalty += 0.20
            reasons.append(
                "User's first message in this session is promotional — "
                "genuine viewers rarely open with solicitations."
            )

    # ── Username structural risk ──────────────────────────────────────────────
    username_risk_score = _score_username(username)
    penalty += (1.0 - username_risk_score) * 0.25
    if username_risk_score < 0.45:
        reasons.append(
            f"Username '{username}' matches auto-generated patterns "
            "(high digit density or random character structure)."
        )

    # ── Prior flagging history ────────────────────────────────────────────────
    if user_profile.flagged_count >= 2:
        penalty += 0.20
        reasons.append(
            f"User '{username}' has had {user_profile.flagged_count} prior flagged "
            "messages in this session."
        )

    score = max(0.0, min(1.0, 1.0 - penalty))

    return {
        "score": score,
        "features": {
            "msg_velocity": msg_velocity,
            "ttr": round(ttr, 3),
            "is_first_message": is_first_message,
            "username_risk": round(username_risk_score, 3),
            "total_session_messages": user_profile.total_messages,
            "prior_flags": user_profile.flagged_count,
        },
        "reasons": reasons,
    }
