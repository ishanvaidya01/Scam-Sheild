"""
ml/text_scorer.py

Contextual text scoring interface.
Uses the trained char n-gram TF-IDF + Logistic Regression model from ml.text_intent
combined with high-precision regex matching from ml.intent_rules.
Fast, deterministic, and domain-grounded.
"""

import hashlib
import logging
from typing import Optional, Dict, Any

from ml.text_intent import get_text_intent_classifier
from ml.intent_rules import match_intent_rules

logger = logging.getLogger(__name__)

_CACHE: dict[str, dict] = {}
_CACHE_MAX = 800


def _cache_key(text: str) -> str:
    return hashlib.md5(text.lower().strip().encode(), usedforsecurity=False).hexdigest()[:12]


def _cache_get(text: str) -> Optional[dict]:
    return _CACHE.get(_cache_key(text))


def _cache_put(text: str, result: dict):
    if len(_CACHE) >= _CACHE_MAX:
        to_drop = list(_CACHE.keys())[:_CACHE_MAX // 10]
        for k in to_drop:
            _CACHE.pop(k, None)
    _CACHE[_cache_key(text)] = result


def score_text(comment_text: str) -> Dict[str, Any]:
    """
    Scores text for scam/solicitation intent. Always returns a valid dict; never raises.
    Returns: { "score": float, "scam_prob": float, "reasons": [str], "has_rule_hit": bool }
    """
    if not comment_text or not comment_text.strip():
        return {
            "score": 1.0,
            "scam_prob": 0.0,
            "reasons": [],
            "has_rule_hit": False,
        }

    text = comment_text.strip()
    cached = _cache_get(text)
    if cached is not None:
        return cached

    # 1. Intent Rules Check
    rule_res = match_intent_rules(text)
    has_rule_hit = rule_res["has_intent_rule_hit"]

    # 2. Text Intent ML Classifier
    clf = get_text_intent_classifier()
    ml_res = clf.score(text)
    scam_prob = ml_res["scam_prob"]

    reasons = []
    if has_rule_hit:
        reasons.extend(rule_res["matched_patterns"])
        # If overt pattern hit, increase scam probability
        scam_prob = max(scam_prob, 0.85)

    reasons.extend(ml_res["reasons"])
    # De-duplicate reasons
    seen = set()
    dedup_reasons = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            dedup_reasons.append(r)

    trust_score = round(max(0.0, min(1.0, 1.0 - scam_prob)), 4)

    result = {
        "score": trust_score,
        "scam_prob": scam_prob,
        "reasons": dedup_reasons,
        "has_rule_hit": has_rule_hit,
    }
    _cache_put(text, result)
    return result
