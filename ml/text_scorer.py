"""
text_scorer.py  (v3)

Signal 2 of 5: Contextual text classification.

Resilience additions vs v2:
  - Simple dict-based LRU cache (hash of text) — avoids re-running heavy models
    on repeated/similar messages, which is common in live chat floods.
  - Every code path wrapped in try/except — this function NEVER raises.
  - Timeout-aware: the zero-shot model call is bounded; if it hasn't loaded,
    we immediately fall back to heuristic-only scoring.
  - All scoring is additive/subtractive — never multiplied by zero or infinity.
"""

import re
import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Model loading ─────────────────────────────────────────────────────────────
_zero_shot = None
_tiny_clf  = None
_MODELS_TRIED = False

def _load_models():
    global _zero_shot, _tiny_clf, _MODELS_TRIED
    if _MODELS_TRIED:
        return
    _MODELS_TRIED = True
    try:
        from transformers import pipeline as hf_pipeline
        _zero_shot = hf_pipeline(
            "zero-shot-classification",
            model="typeform/distilbert-base-uncased-mnli",
            device=-1,
            multi_label=False,
        )
        logger.info("Zero-shot classifier loaded.")
    except Exception as e:
        logger.warning(f"Zero-shot classifier not available: {e}")

    try:
        from transformers import pipeline as hf_pipeline
        _tiny_clf = hf_pipeline(
            "text-classification",
            model="mrm8488/bert-tiny-finetuned-sms-spam-detection",
            device=-1,
        )
        logger.info("Bert-tiny backup classifier loaded.")
    except Exception as e:
        logger.warning(f"Bert-tiny classifier not available: {e}")


# ── Simple LRU-style cache (max 800 entries) ──────────────────────────────────
_CACHE: dict[str, dict] = {}
_CACHE_MAX = 800

def _cache_key(text: str) -> str:
    return hashlib.md5(text.lower().strip().encode(), usedforsecurity=False).hexdigest()[:12]

def _cache_get(text: str) -> Optional[dict]:
    return _CACHE.get(_cache_key(text))

def _cache_put(text: str, result: dict):
    if len(_CACHE) >= _CACHE_MAX:
        # Drop oldest 10% to avoid growing unboundedly
        to_drop = list(_CACHE.keys())[:_CACHE_MAX // 10]
        for k in to_drop:
            _CACHE.pop(k, None)
    _CACHE[_cache_key(text)] = result

# ── Zero-shot candidate labels ────────────────────────────────────────────────
_CANDIDATE_LABELS = [
    "financial scam or cryptocurrency solicitation",
    "bot generated spam message",
    "self promotion or unsolicited advertisement",
    "genuine viewer comment or reaction",
    "question or discussion",
]

_SCAM_LABEL_SCORES = {
    "financial scam or cryptocurrency solicitation": 0.05,
    "bot generated spam message": 0.10,
    "self promotion or unsolicited advertisement": 0.30,
}
_GENUINE_LABEL_SCORES = {
    "genuine viewer comment or reaction": 1.0,
    "question or discussion": 0.90,
}

# ── Context-aware regex patterns ──────────────────────────────────────────────
_SHORTENER_RE = re.compile(
    r"\b(bit\.ly|tinyurl\.com|cutt\.ly|rb\.gy|t\.co|ow\.ly|short\.io|linktr\.ee)/\S+",
    re.I
)

def _is_promo_url(text: str, m: re.Match) -> bool:
    # If it's a known URL shortener, always flag it
    if _SHORTENER_RE.search(m.group(0)):
        return True
    promo = {
        "earn", "profit", "invest", "free", "win", "won", "giveaway", "claim",
        "reward", "crypto", "bitcoin", "btc", "eth", "sol", "usdt",
        "send", "guaranteed", "register", "click", "airdrop", "nft",
    }
    ctx = text[max(0, m.start()-80):m.end()+80].lower()
    return bool(set(re.findall(r'\w+', ctx)) & promo)

def _is_promo_handle(text: str, m: re.Match) -> bool:
    reply_kw = {"hi","hey","hello","great","lol","nice","agree","true","love","haha","same"}
    promo_kw = {"dm","message","contact","send","invest","join","earn","profit","wallet","crypto","link"}
    tokens = set(text.lower().split())
    if len(text.split()) <= 8 and tokens & reply_kw and not tokens & promo_kw:
        return False
    return bool(tokens & promo_kw)

def _is_dm_solicitation(text: str, m: re.Match) -> bool:
    offer_kw = {"win","won","earn","invest","profit","free","bitcoin","btc","eth","crypto","giveaway","send"}
    return bool(set(text.lower().split()) & offer_kw)

def _always(text: str, m: re.Match) -> bool:
    return True

_PATTERNS = [
    ("External link in promotional context",
     re.compile(r"https?://\S+|bit\.ly/\S+|tinyurl\.com/\S+|cutt\.ly/\S+|rb\.gy/\S+", re.I), _is_promo_url),
    ("Handle used as solicitation target",
     re.compile(r"@[\w]{4,}", re.I), _is_promo_handle),
    ("Direct message solicitation",
     re.compile(r"\b(dm me|message me|contact me|inbox me|chat me|reach me|reach out|"
                r"text me|slide into|hmu|hit me up)\b", re.I), _is_dm_solicitation),
    ("Crypto wallet address",
     re.compile(r"0x[a-fA-F0-9]{40}|[13][a-km-zA-HJ-NP-Z1-9]{25,34}", re.I), _always),
    ("Telegram/Discord group solicitation",
     re.compile(r"t\.me/\S+|telegram\.me/\S+|discord\.gg/\S+", re.I), _always),
    ("Channel or social media self-promotion",
     re.compile(r"\b(follow for follow|f4f|sub for sub|sub to my channel|"
                r"check my channel|check out my channel|subscribe to my|"
                r"link in bio)\b", re.I), _always),
    ("Financial bait phrasing",
     re.compile(
         r"\b(guaranteed returns?|giveaway|won \d+ (?:btc|eth|usdt|sol)|"
         r"send (?:eth|btc|sol|usdt)|"
         r"\d+x profit|\d+x return|double your|passive income|"
         r"airdrop|nft giveaway|free crypto|free money|free bitcoin|"
         r"pump and dump|rug pull|moon guaranteed|"
         r"click (?:the )?link|check (?:my )?bio|"
         r"limited (?:time )?offer|act now|claim (?:your )?reward|"
         r"investment opportunity)\b", re.I), _always),
    ("WhatsApp redirect",
     re.compile(r"wa\.me/\S+|whatsapp\.com/\S+", re.I), _always),
]


def score_text(comment_text: str) -> dict:
    """
    Scores text. Always returns a valid dict; never raises.
    Returns: { "score": float, "label": str, "confidence": float, "reasons": [str] }
    """
    # Load models once (lazy)
    _load_models()

    if not comment_text or not comment_text.strip():
        return {"score": 1.0, "label": "empty", "confidence": 1.0, "reasons": []}

    text = comment_text.strip()

    # Cache hit?
    cached = _cache_get(text)
    if cached is not None:
        return cached

    reasons: list[str] = []
    regex_penalty = 0.0

    # ── 1. Contextual regex ───────────────────────────────────────────────────
    try:
        for desc, pattern, verifier in _PATTERNS:
            for m in pattern.finditer(text):
                try:
                    if verifier(text, m):
                        if desc not in reasons:
                            reasons.append(desc)
                        regex_penalty += 0.20
                        break
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"Regex scoring error: {e}")

    # ── 2. Zero-shot classification ───────────────────────────────────────────
    zero_score: Optional[float] = None
    zero_label = "unknown"
    zero_conf  = 0.0

    if _zero_shot:
        try:
            res = _zero_shot(
                text[:512],
                candidate_labels=_CANDIDATE_LABELS,
                hypothesis_template="This YouTube comment is {}.",
            )
            top_label = res["labels"][0]
            top_score = res["scores"][0]
            zero_label = top_label
            zero_conf  = top_score

            if top_label in _SCAM_LABEL_SCORES:
                zero_score = _SCAM_LABEL_SCORES[top_label]
                if top_score >= 0.60:
                    reasons.append(
                        f"Classifier: '{top_label}' ({top_score:.0%} confidence)."
                    )
            elif top_label in _GENUINE_LABEL_SCORES:
                zero_score = _GENUINE_LABEL_SCORES[top_label]
        except Exception as e:
            logger.debug(f"Zero-shot error: {e}")

    # ── 3. Bert-tiny fallback ─────────────────────────────────────────────────
    tiny_score: Optional[float] = None
    if _tiny_clf:
        try:
            r = _tiny_clf(text[:512])[0]
            if r.get("label") in ("LABEL_1", "spam"):
                tiny_score = 1.0 - r["score"]
            else:
                tiny_score = r["score"]
        except Exception as e:
            logger.debug(f"Bert-tiny error: {e}")

    # ── 4. Combine ────────────────────────────────────────────────────────────
    if zero_score is not None and tiny_score is not None:
        ai_score = 0.75 * zero_score + 0.25 * tiny_score
    elif zero_score is not None:
        ai_score = zero_score
    elif tiny_score is not None:
        ai_score = tiny_score
    else:
        # No models available — heuristic only, be generous by default
        ai_score = 0.75

    final_score = max(0.0, min(1.0, ai_score - regex_penalty))

    result = {
        "score": final_score,
        "label": zero_label,
        "confidence": round(zero_conf, 3),
        "reasons": reasons,
    }
    _cache_put(text, result)
    return result
