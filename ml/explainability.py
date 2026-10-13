"""
explainability.py

ExplainabilityEngine: Converts raw signal outputs into prioritized,
human-readable, actionable reasons for display in the extension popover.

Design principles:
  1. Reasons are specific and informative, not generic ("spam detected").
  2. Positive signals (genuine indicators) are also surfaced, not just negatives.
  3. Reasons are de-duplicated and ordered by severity.
  4. Each reason is tagged with its source signal for transparency.
  5. A summary verdict is generated that explains the trust tier.

Output schema:
  {
    "verdict": str,         -- one-line human-readable summary
    "reasons": [            -- ordered list of flagged/positive signals
      {
        "text": str,
        "type": "flag" | "positive" | "info",
        "signal": str       -- which analyzer produced this
      }
    ],
    "signal_breakdown": {   -- per-signal scores (0.0–1.0) for the visual bar
      "linguistic": float,
      "text": float,
      "coordination": float,
      "behavioral": float,
      "network": float
    }
  }
"""

from typing import Optional


# ── Tier thresholds ────────────────────────────────────────────────────────────
_TIERS = [
    (0.80, "✅ Trusted", "This message shows strong indicators of genuine user activity."),
    (0.60, "🔵 Likely Genuine", "This message appears genuine with minor uncertain signals."),
    (0.40, "⚡ Suspicious", "This message has notable suspicious signals — review before engaging."),
    (0.20, "⚠️ High Risk", "Multiple strong scam/bot indicators detected. Avoid engaging."),
    (0.00, "🚫 Scam / Bot", "Highly likely automated or scam content. Do not interact."),
]


def _get_tier_info(trust_score: float) -> tuple[str, str]:
    """Returns (tier_label, tier_description) for a given trust score."""
    for threshold, label, desc in _TIERS:
        if trust_score >= threshold:
            return label, desc
    return _TIERS[-1][1], _TIERS[-1][2]


def _positive_signals_from_features(
    behavioral_features: dict,
    coord_sub_signals: dict,
    network_features: dict,
) -> list[dict]:
    """
    Identifies genuine/positive signals to surface in the popover.
    These are important for building user trust in the system.
    """
    positives = []

    # Behavioral positives
    if behavioral_features.get("total_session_messages", 0) >= 5:
        positives.append({
            "text": f"User has {behavioral_features['total_session_messages']} messages in this session — established participant.",
            "type": "positive",
            "signal": "behavioral",
        })

    ttr = behavioral_features.get("ttr", 1.0)
    if ttr > 0.75:
        positives.append({
            "text": "High vocabulary diversity across user's messages — consistent with genuine human expression.",
            "type": "positive",
            "signal": "behavioral",
        })

    velocity = behavioral_features.get("msg_velocity", 0)
    if velocity <= 2:
        positives.append({
            "text": "Normal messaging rate — not spam-level activity.",
            "type": "positive",
            "signal": "behavioral",
        })

    # Network positives
    if not network_features.get("is_in_clique", False) and network_features.get("edge_count", 0) > 0:
        positives.append({
            "text": "No coordinated clique membership detected in session graph.",
            "type": "positive",
            "signal": "network",
        })

    return positives


def build_explanation(
    trust_score: float,
    signal_scores: dict,
    all_raw_reasons: list[str],
    signal_sources: dict,
    behavioral_features: Optional[dict] = None,
    coord_sub_signals: Optional[dict] = None,
    network_features: Optional[dict] = None,
) -> dict:
    """
    Builds the complete explanation object for display in the popover.

    Args:
        trust_score: Final fused trust score (0.0–1.0)
        signal_scores: { "linguistic": float, "text": float, ... }
        all_raw_reasons: Aggregated list of raw reason strings from all signals
        signal_sources: { reason_text: signal_name } mapping for tagging
        behavioral_features: Output features from BehavioralProfiler
        coord_sub_signals: Sub-signals from CoordinationEngine v2
        network_features: Features from NetworkAnalyzer

    Returns:
        { "verdict": str, "reasons": [dict], "signal_breakdown": dict }
    """
    tier_label, tier_desc = _get_tier_info(trust_score)

    # ── Build flagged reasons list ─────────────────────────────────────────────
    flagged_reasons = []
    seen_texts = set()

    for reason_text in all_raw_reasons:
        if reason_text in seen_texts:
            continue
        seen_texts.add(reason_text)
        source_signal = signal_sources.get(reason_text, "ensemble")
        flagged_reasons.append({
            "text": reason_text,
            "type": "flag",
            "signal": source_signal,
        })

    # ── Coordination sub-signal explanations ──────────────────────────────────
    if coord_sub_signals:
        timing_pval = coord_sub_signals.get("timing_burst_pval")
        if timing_pval is not None and timing_pval < 0.05:
            info_text = (
                f"Statistically anomalous message burst detected "
                f"(p={timing_pval:.3f} < 0.05 under Poisson model)."
            )
            if info_text not in seen_texts:
                flagged_reasons.append({
                    "text": info_text,
                    "type": "info",
                    "signal": "coordination",
                })
                seen_texts.add(info_text)

        if coord_sub_signals.get("lexical_template_match"):
            info_text = "Message matches a template skeleton shared by other accounts in this session."
            if info_text not in seen_texts:
                flagged_reasons.append({
                    "text": info_text,
                    "type": "flag",
                    "signal": "coordination",
                })
                seen_texts.add(info_text)

    # ── Add positive signals (only when score is above 0.5) ──────────────────
    positive_reasons = []
    if trust_score >= 0.5:
        positive_reasons = _positive_signals_from_features(
            behavioral_features or {},
            coord_sub_signals or {},
            network_features or {},
        )

    # ── If no flags at all, add a clean bill of health ────────────────────────
    if not flagged_reasons and trust_score >= 0.7:
        flagged_reasons.append({
            "text": "No security flags triggered across all 5 detection signals.",
            "type": "positive",
            "signal": "ensemble",
        })

    # Combine: flags first, then positives (max 6 items for clean UI)
    all_reasons = flagged_reasons + positive_reasons
    all_reasons = all_reasons[:8]  # cap for popover readability

    return {
        "verdict": f"{tier_label} — {tier_desc}",
        "reasons": all_reasons,
        "signal_breakdown": {
            "linguistic": round(signal_scores.get("linguistic", 1.0), 3),
            "text": round(signal_scores.get("text", 1.0), 3),
            "coordination": round(signal_scores.get("coordination", 1.0), 3),
            "behavioral": round(signal_scores.get("behavioral", 1.0), 3),
            "network": round(signal_scores.get("network", 1.0), 3),
        },
    }
