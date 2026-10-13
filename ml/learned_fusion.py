"""
ml/learned_fusion.py

Learned Fusion layer for Scam Shield.
Trains Logistic Regression on multi-signal features extracted from DEV sessions only.
Exports feature coefficients as the explanation source.
Outputs:
  - trust_score: float (0.0 to 1.0)
  - verdict: "clear" | "suspicious" | "likely_campaign" | "unverifiable"
  - unverifiable: bool
  - reasons: top 3 concrete evidence strings
"""

import os
import sys
import pickle
import logging
from typing import Dict, Any, List, Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FUSION_MODEL_PATH = os.path.join(os.path.dirname(__file__), "_fusion_model.pkl")

FEATURE_NAMES = [
    "text_scam_prob",
    "cluster_account_count",
    "cluster_cohesion",
    "rate_normalized_synchrony",
    "off_topic_distance",
    "skeleton_reuse_ratio",
    "account_first_seen_delta",
    "account_msg_count",
    "is_trusted_badge",
    "intent_rules_hit",
    "is_organic_hype_pattern",
]

# Meaningful natural-language explanation templates for top feature contributors
FEATURE_EXPLANATIONS = {
    "text_scam_prob": "Text intent model flagged high scam/solicitation likelihood",
    "cluster_account_count": "Coordinated with {val:.0f} accounts sharing semantically similar content",
    "cluster_cohesion": "High semantic similarity ({val:.0%}) with other recent comments",
    "rate_normalized_synchrony": "Anomalous message rate spike relative to background chat",
    "off_topic_distance": "High semantic drift ({val:.0%}) from stream conversation topic",
    "skeleton_reuse_ratio": "Repeated lexical template skeleton matching multiple messages",
    "account_first_seen_delta": "New account posted immediately upon arrival ({val:.0f}s)",
    "account_msg_count": "High message volume from this user in current session",
    "is_trusted_badge": "Channel Member / Moderator / Verified badge (protective)",
    "intent_rules_hit": "Direct solicitation detected: external link, wallet, or handle",
    "is_organic_hype_pattern": "Community-wide organic hype burst (not coordinated bot activity)",
}


class LearnedFusionModel:
    """Logistic Regression ensemble trained on Dev session features."""

    def __init__(self):
        self.scaler = None
        self.model = None
        self.tau_campaign = 0.65
        self.tau_suspicious = 0.35
        self.is_fitted = False
        self._load()

    def _load(self):
        if os.path.exists(FUSION_MODEL_PATH):
            try:
                with open(FUSION_MODEL_PATH, "rb") as f:
                    bundle = pickle.load(f)
                    self.scaler = bundle["scaler"]
                    self.model = bundle["model"]
                    self.tau_campaign = bundle.get("tau_campaign", 0.65)
                    self.tau_suspicious = bundle.get("tau_suspicious", 0.35)
                    self.is_fitted = True
            except Exception as e:
                logger.warning(f"Could not load fusion model: {e}")

    def fit(self, X: np.ndarray, y: np.ndarray, tau_campaign: float = 0.65, tau_suspicious: float = 0.35):
        """Fits standard scaler and logistic regression on Dev data."""
        from sklearn.preprocessing import StandardScaler
        from sklearn.linear_model import LogisticRegression

        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)
        self.model = LogisticRegression(C=1.0, max_iter=1000, class_weight="balanced")
        self.model.fit(X_scaled, y)
        self.tau_campaign = tau_campaign
        self.tau_suspicious = tau_suspicious
        self.is_fitted = True

        with open(FUSION_MODEL_PATH, "wb") as f:
            pickle.dump({
                "scaler": self.scaler,
                "model": self.model,
                "tau_campaign": self.tau_campaign,
                "tau_suspicious": self.tau_suspicious,
            }, f)
        logger.info("Fitted learned fusion model on Dev split.")

    def predict_campaign_prob(self, feature_dict: Dict[str, float]) -> Tuple[float, List[Dict[str, Any]]]:
        """
        Returns continuous campaign probability P(campaign)
        and ordered feature contributions for top-3 explainability.
        """
        raw_x = np.array([feature_dict.get(k, 0.0) for k in FEATURE_NAMES], dtype=np.float32)

        if not self.is_fitted or self.model is None:
            # Safe linear fallback before model fitting
            p = (
                0.35 * feature_dict.get("text_scam_prob", 0.0)
                + 0.25 * (min(feature_dict.get("cluster_account_count", 1.0) - 1.0, 3.0) / 3.0)
                + 0.20 * feature_dict.get("intent_rules_hit", 0.0)
                + 0.15 * feature_dict.get("off_topic_distance", 0.0)
                - 0.30 * feature_dict.get("is_organic_hype_pattern", 0.0)
                - 0.20 * feature_dict.get("is_trusted_badge", 0.0)
            )
            prob = float(max(0.01, min(0.99, p)))
            contributions = [
                {"feature": k, "contrib": float(raw_x[i]), "val": float(raw_x[i])}
                for i, k in enumerate(FEATURE_NAMES) if raw_x[i] > 0
            ]
            return prob, contributions

        X_scaled = self.scaler.transform([raw_x])
        prob = float(self.model.predict_proba(X_scaled)[0][1])

        # Feature contributions: w_i * x_scaled_i
        coefs = self.model.coef_[0]
        contrib_values = coefs * X_scaled[0]
        contributions = []
        for i, fname in enumerate(FEATURE_NAMES):
            contributions.append({
                "feature": fname,
                "contrib": float(contrib_values[i]),
                "val": float(raw_x[i]),
            })

        # Sort by magnitude of contribution
        contributions.sort(key=lambda c: abs(c["contrib"]), reverse=True)
        return prob, contributions

    def score_features(self, feature_dict: Dict[str, float], cluster_meta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Computes final verdict, trust score, and top 3 explanations.
        """
        prob_campaign, contributions = self.predict_campaign_prob(feature_dict)
        trust_score = round(max(0.0, min(1.0, 1.0 - prob_campaign)), 4)

        # Check organic hype override (RQ2)
        if feature_dict.get("is_organic_hype_pattern", 0.0) == 1.0:
            prob_campaign = min(prob_campaign, 0.15)
            trust_score = 0.90

        # Abstention logic (L3-single / insufficient evidence)
        is_unverifiable = False
        is_single_msg = feature_dict.get("account_msg_count", 1.0) <= 1.0
        no_cluster = feature_dict.get("cluster_account_count", 1.0) <= 1.0
        no_rule_hits = feature_dict.get("intent_rules_hit", 0.0) == 0.0

        if is_single_msg and no_cluster and no_rule_hits and 0.30 <= prob_campaign <= 0.70:
            is_unverifiable = True
            verdict = "unverifiable"
            verdict_label = "Unverifiable"
        elif prob_campaign >= self.tau_campaign:
            verdict = "likely_campaign"
            verdict_label = "Likely Campaign"
        elif prob_campaign >= self.tau_suspicious:
            verdict = "suspicious"
            verdict_label = "Suspicious"
        else:
            verdict = "clear"
            verdict_label = "Clear"

        # Build top 3 concrete evidence strings
        top_reasons = []
        for item in contributions:
            fname = item["feature"]
            val = item["val"]
            contrib = item["contrib"]

            if val == 0 and fname != "is_trusted_badge":
                continue

            tmpl = FEATURE_EXPLANATIONS.get(fname, fname)
            try:
                reason_text = tmpl.format(val=val)
            except Exception:
                reason_text = tmpl

            top_reasons.append({
                "text": reason_text,
                "type": "positive" if contrib < 0 else "flag",
                "signal": fname.split("_")[0],
            })
            if len(top_reasons) >= 3:
                break

        return {
            "trust_score": trust_score,
            "campaign_prob": round(prob_campaign, 4),
            "verdict": verdict,
            "verdict_label": verdict_label,
            "unverifiable": is_unverifiable,
            "reasons": top_reasons,
        }


# Singleton instance
_FUSION_INSTANCE: Optional[LearnedFusionModel] = None

def get_learned_fusion_model() -> LearnedFusionModel:
    global _FUSION_INSTANCE
    if _FUSION_INSTANCE is None:
        _FUSION_INSTANCE = LearnedFusionModel()
    return _FUSION_INSTANCE
