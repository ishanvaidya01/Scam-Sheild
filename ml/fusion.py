"""
fusion.py  (v3)

The FusionLayer: Combines all 5 signal scores into a final calibrated trust score.
Every signal call is wrapped in try/except — this function NEVER raises.
If a signal fails, it contributes a neutral score (1.0) and no reasons.

Default signal weights (sum to 1.0):
  Coordination:  0.35
  Behavioral:    0.30
  Text:          0.18
  Linguistic:    0.12
  Network:       0.05
"""

import re
import logging
from typing import Optional

from ml.session_state import SessionState
from ml.text_scorer import score_text
from ml.coordination_engine import check_coordination, TIME_WINDOW_SECONDS
from ml.linguistic_analyzer import analyze_linguistics
from ml.behavioral_profiler import analyze_behavior
from ml.network_analyzer import analyze_network
from ml.explainability import build_explanation
from ml.calibrator import get_calibrator

_EMOJI_RE = re.compile(
    r"[\U0001F000-\U0001FFFF\U00002600-\U000027FF"
    r"\u2705\U0001F6AB\u26A1\u26A0\uFE0F\u200D]+",
    re.UNICODE,
)

logger = logging.getLogger(__name__)

# ── Default signal weights ─────────────────────────────────────────────────────
_DEFAULT_WEIGHTS = {
    "coordination": 0.35,  # up from 0.30 — hardest signal to fake
    "behavioral":   0.30,  # up from 0.25 — tracks user history
    "text":         0.18,  # down from 0.20
    "linguistic":   0.12,  # down from 0.15
    "network":      0.05,  # down from 0.10 — requires large graph to be useful
}

# ── Tier mapping ───────────────────────────────────────────────────────────────
_TIERS = [
    (0.80, "trusted",    "✅ Trusted"),
    (0.60, "likely",     "🔵 Likely Genuine"),
    (0.40, "suspicious", "⚡ Suspicious"),
    (0.20, "high_risk",  "⚠️ High Risk"),
    (0.00, "scam",       "🚫 Scam / Bot"),
]

def _get_tier(score: float) -> tuple[str, str]:
    for threshold, tier_id, tier_label in _TIERS:
        if score >= threshold:
            return tier_id, tier_label
    return "scam", "🚫 Scam / Bot"


def _get_weights(session: SessionState) -> dict:
    """
    Returns sensitivity-adjusted signal weights, always summing to 1.0.
    Only coordination changes with sensitivity; other weights scale proportionally.
    """
    coord_w = session.get_coordination_weight()
    # Remaining budget for the other 4 signals, split proportionally from defaults
    remaining = 1.0 - coord_w
    others_sum = (
        _DEFAULT_WEIGHTS["behavioral"]
        + _DEFAULT_WEIGHTS["text"]
        + _DEFAULT_WEIGHTS["linguistic"]
        + _DEFAULT_WEIGHTS["network"]
    )
    scale = remaining / others_sum if others_sum > 0 else 1.0
    return {
        "coordination": coord_w,
        "behavioral":   _DEFAULT_WEIGHTS["behavioral"]   * scale,
        "text":         _DEFAULT_WEIGHTS["text"]         * scale,
        "linguistic":   _DEFAULT_WEIGHTS["linguistic"]   * scale,
        "network":      _DEFAULT_WEIGHTS["network"]      * scale,
    }


def get_trust_score(comment: dict, session: SessionState) -> dict:
    """
    Synchronous fusion entry point. Runs all 5 signals and fuses them.

    Args:
        comment:  { "comment_id", "text", "username", "timestamp" }
        session:  SessionState object for this WebSocket connection

    Returns:
        {
          "comment_id": str,
          "trust_score": float,
          "tier": str,
          "tier_label": str,
          "verdict": str,
          "reasons": [ { "text": str, "type": str, "signal": str } ],
          "signal_breakdown": { "linguistic": f, "text": f, ... }
        }
    """
    # ── Defaults for every signal (used as fallback if a signal crashes) ─────
    _NEUTRAL_SIGNAL = {"score": 1.0, "reasons": [], "features": {}, "sub_signals": {}}
    _NEUTRAL_COORD  = {
        "is_coordinated": False, "coordination_score": 1.0,
        "sub_signals": {}, "reason": None, "new_embedding": None,
    }

    text       = comment.get("text", "")
    username   = comment.get("username", "")
    comment_id = comment.get("comment_id", "")
    timestamp  = comment.get("timestamp", 0)

    # ── User profile (always safe) ────────────────────────────────────────────
    try:
        user_profile = session.get_or_create_profile(username)
        user_profile.record_message(text, timestamp)
    except Exception as e:
        logger.warning(f"User profile error: {e}")
        from ml.session_state import UserProfile
        user_profile = UserProfile(username=username)

    # ── Signal 3: Coordination ────────────────────────────────────────────────
    try:
        coord_result = check_coordination(comment, session.rolling_window)
    except Exception as e:
        logger.warning(f"Coordination signal error: {e}")
        coord_result = dict(_NEUTRAL_COORD)

    # ── Signal 1: Linguistic ──────────────────────────────────────────────────
    try:
        ling_result = analyze_linguistics(text)
    except Exception as e:
        logger.warning(f"Linguistic signal error: {e}")
        ling_result = dict(_NEUTRAL_SIGNAL)

    # ── Signal 2: Text classifier ─────────────────────────────────────────────
    try:
        text_result = score_text(text)
    except Exception as e:
        logger.warning(f"Text signal error: {e}")
        text_result = {"score": 1.0, "label": "unknown", "confidence": 0.0, "reasons": []}

    # ── Signal 4: Behavioral ──────────────────────────────────────────────────
    try:
        behav_result = analyze_behavior(comment, user_profile)
    except Exception as e:
        logger.warning(f"Behavioral signal error: {e}")
        behav_result = {"score": 1.0, "features": {}, "reasons": []}

    # ── Signal 5: Network Graph ───────────────────────────────────────────────
    try:
        new_emb = coord_result.get("new_embedding")
        network_result = analyze_network(
            comment=comment,
            session_edges=session.graph_edges,
            session_user_profiles=session.user_profiles,
            new_embedding=new_emb,
            recent_window=session.rolling_window,
        )
    except Exception as e:
        logger.warning(f"Network signal error: {e}")
        network_result = {"score": 1.0, "features": {}, "reasons": []}

    # ── Raw scores ────────────────────────────────────────────────────────────
    signal_scores = {
        "linguistic":   max(0.0, min(1.0, ling_result.get("score", 1.0))),
        "text":         max(0.0, min(1.0, text_result.get("score", 1.0))),
        "coordination": max(0.0, min(1.0, coord_result.get("coordination_score", 1.0))),
        "behavioral":   max(0.0, min(1.0, behav_result.get("score", 1.0))),
        "network":      max(0.0, min(1.0, network_result.get("score", 1.0))),
    }

    # ── Hard overrides ────────────────────────────────────────────────────────
    hard_override = None
    try:
        import re as _re
        _wallet_re = _re.compile(r"0x[a-fA-F0-9]{40}|[13][a-km-zA-HJ-NP-Z1-9]{25,34}")

        # Override 1: Bot ring confirmed (large clique + coordinated)
        if coord_result.get("is_coordinated") and network_result["features"].get("clique_size", 0) >= 4:
            hard_override = 0.02

        # Override 2: Extreme velocity + promotional text
        velocity = behav_result["features"].get("msg_velocity", 0)
        if velocity >= 15 and text_result.get("score", 1.0) < 0.3:
            hard_override = min(hard_override or 0.05, 0.05)

        # Override 3: Crypto wallet address present
        if _wallet_re.search(text or ""):
            hard_override = min(hard_override or 0.03, 0.03)

        # Override 4 (NEW): Same-user self-repetition detected — the single most
        # reliable bot signal in live chat. A real user NEVER sends the same
        # message multiple times in a session on purpose.
        coord_sub = coord_result.get("sub_signals", {})
        self_repeat_count = coord_sub.get("self_repeat_count", 0)
        self_repeat_detected = coord_sub.get("self_repeat_detected", False)
        if self_repeat_count >= 2:
            # 3+ identical messages from same user = almost certainly a bot
            hard_override = min(hard_override or 0.10, 0.10)
        elif self_repeat_detected:
            # 2 identical messages = high risk, cap at 0.20
            hard_override = min(hard_override or 0.20, 0.20)

    except Exception as e:
        logger.debug(f"Hard override check error: {e}")

    # ── Weighted ensemble ─────────────────────────────────────────────────────
    try:
        if hard_override is not None:
            raw_score = hard_override
        else:
            weights = _get_weights(session)
            raw_score = sum(weights[sig] * sc for sig, sc in signal_scores.items())
        raw_score = max(0.0, min(1.0, raw_score))
    except Exception as e:
        logger.warning(f"Ensemble error: {e}")
        raw_score = 0.5

    # ── Calibration ───────────────────────────────────────────────────────────
    try:
        trust_score = get_calibrator().calibrate(raw_score)
    except Exception as e:
        logger.debug(f"Calibration error: {e}")
        trust_score = raw_score

    # ── Tier ──────────────────────────────────────────────────────────────────
    try:
        tier_id, tier_label = _get_tier(trust_score)
    except Exception:
        tier_id, tier_label = "suspicious", "Suspicious"

    # ── Session stats ─────────────────────────────────────────────────────────
    try:
        session.total_scanned += 1
        if trust_score < session.get_sensitivity_threshold():
            session.total_flagged += 1
            user_profile.flagged_count += 1
        if trust_score < 0.20:
            session.total_scam += 1
    except Exception:
        pass

    # ── Collect reasons ───────────────────────────────────────────────────────
    all_raw_reasons: list[str] = []
    signal_sources: dict[str, str] = {}

    def _collect(result: dict, sig_name: str):
        for r in result.get("reasons", []):
            if r and r not in signal_sources:
                all_raw_reasons.append(r)
                signal_sources[r] = sig_name

    _collect(ling_result,    "linguistic")
    _collect(text_result,    "text")
    _collect(behav_result,   "behavioral")
    _collect(network_result, "network")
    coord_reason = coord_result.get("reason")
    if coord_reason:
        for part in coord_reason.split("; "):
            if part and part not in signal_sources:
                all_raw_reasons.append(part)
                signal_sources[part] = "coordination"

    # ── Explainability ────────────────────────────────────────────────────────
    explanation = build_explanation(
        trust_score=trust_score,
        signal_scores=signal_scores,
        all_raw_reasons=all_raw_reasons,
        signal_sources=signal_sources,
        behavioral_features=behav_result.get("features", {}),
        coord_sub_signals=coord_result.get("sub_signals", {}),
        network_features=network_result.get("features", {}),
    )

    # ── Add comment to rolling window ─────────────────────────────────────────
    session.rolling_window.append(comment)

    return {
        "comment_id": comment_id,
        "trust_score": trust_score,
        "tier": tier_id,
        "tier_label": tier_label,
        "verdict": explanation["verdict"],
        "reasons": explanation["reasons"],
        "signal_breakdown": explanation["signal_breakdown"],
        "session_stats": {
            "total_scanned": session.total_scanned,
            "total_flagged": session.total_flagged,
            "total_scam": session.total_scam,
        },
    }
