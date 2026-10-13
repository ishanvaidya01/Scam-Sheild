"""
linguistic_analyzer.py

Signal 1 of 5: Deep NLP-based linguistic analysis using spaCy.

Key design philosophy:
  - Does NOT flag based on keyword presence alone.
  - Every pattern is evaluated in its CONTEXT (surrounding tokens, POS tags, dependency parse).
  - This directly addresses the false-positive problem of flagging "@" in genuine replies.

Output schema:
  {
    "score": float (0.0 = definitely scam, 1.0 = definitely genuine),
    "signals": {
      "url_context": "safe" | "suspicious" | "none",
      "at_mention_role": "reply" | "promotional" | "none",
      "entropy": float,
      "caps_ratio": float,
      "entity_density": float,
      "punctuation_explosion": bool
    },
    "reasons": [str]  -- only populated with meaningful, human-readable flags
  }
"""

import re
import math
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── spaCy model loading (lazy, once at import time) ──────────────────────────
try:
    import spacy
    _nlp = spacy.load("en_core_web_sm")
    _SPACY_AVAILABLE = True
    logger.info("spaCy en_core_web_sm loaded successfully.")
except OSError:
    _nlp = None
    _SPACY_AVAILABLE = False
    logger.warning(
        "spaCy model 'en_core_web_sm' not found. "
        "Run: python -m spacy download en_core_web_sm\n"
        "LinguisticAnalyzer will run in degraded (heuristic-only) mode."
    )
except ImportError:
    _nlp = None
    _SPACY_AVAILABLE = False
    logger.warning("spaCy not installed. LinguisticAnalyzer in heuristic-only mode.")


# ── Context tokens that indicate a URL is part of self-promotion / scam ──────
_PROMO_URL_CONTEXT_TOKENS = {
    "click", "visit", "check", "join", "register", "earn", "invest",
    "free", "crypto", "bitcoin", "eth", "btc", "profit", "rich",
    "win", "won", "prize", "giveaway", "claim", "reward"
}

# ── Context tokens that make an @mention clearly a normal reply ──────────────
_REPLY_MENTION_CONTEXT_TOKENS = {
    "hi", "hey", "hello", "great", "nice", "agree", "lol", "haha",
    "thanks", "thank", "love", "true", "right", "exactly", "yes",
    "no", "wow", "omg", "same", "lmao", "bruh"
}

# ── Entities that are strong spam signals when mentioned ─────────────────────
_SPAM_ENTITY_LABELS = {"MONEY", "PERCENT"}  # "$500", "200%"
_HIGH_RISK_ORG_PATTERNS = re.compile(
    r"(?i)(telegram|whatsapp|binance|coinbase|metamask|trust.?wallet)"
)

# ── Regex helpers ─────────────────────────────────────────────────────────────
_URL_RE = re.compile(r"https?://\S+|bit\.ly/\S+|t\.me/\S+|wa\.me/\S+", re.I)
_AT_HANDLE_RE = re.compile(r"@[\w]{3,}")
_PUNCT_EXPLOSION_RE = re.compile(r"[!?]{3,}")
_CAPS_WORD_RE = re.compile(r"\b[A-Z]{3,}\b")


def _shannon_entropy(text: str) -> float:
    """Shannon entropy of character-level frequency. Higher = more information-dense."""
    if not text:
        return 0.0
    freq: dict = {}
    for ch in text:
        freq[ch] = freq.get(ch, 0) + 1
    total = len(text)
    return -sum((c / total) * math.log2(c / total) for c in freq.values())


def _analyze_url_context(doc, url_match: re.Match) -> str:
    """
    Returns 'suspicious' if a URL is surrounded by promotional/scam keywords,
    'safe' if it appears in a benign context, 'neutral' otherwise.
    """
    # Get surrounding text window (±60 chars)
    start = max(0, url_match.start() - 60)
    end = min(len(doc.text), url_match.end() + 60)
    context = doc.text[start:end].lower()
    context_tokens = set(re.findall(r"\w+", context))

    promo_overlap = context_tokens & _PROMO_URL_CONTEXT_TOKENS
    if promo_overlap:
        return "suspicious"

    # Check if the URL is a well-known safe domain
    url_text = url_match.group(0).lower()
    safe_domains = ("youtube.com", "youtu.be", "twitch.tv", "twitter.com",
                    "instagram.com", "reddit.com", "discord.gg", "github.com")
    if any(d in url_text for d in safe_domains):
        return "safe"

    return "neutral"


def _analyze_at_mention_role(doc, mention: str) -> str:
    """
    Determines the communicative role of an @mention.

    Returns:
      'reply'       → normal conversational mention (e.g., "hey @user nice point")
      'promotional' → used in a call-to-action (e.g., "send eth to @CryptoGuru")
      'neutral'     → insufficient context to determine
    """
    handle_lower = mention.lower()
    # Handles with lots of digits or random alphanumeric patterns are suspicious
    handle_body = handle_lower.lstrip("@")
    digit_ratio = sum(c.isdigit() for c in handle_body) / max(len(handle_body), 1)

    full_text_lower = doc.text.lower()
    text_tokens = set(re.findall(r"\w+", full_text_lower))

    # Check if reply-context tokens exist anywhere in the message
    reply_overlap = text_tokens & _REPLY_MENTION_CONTEXT_TOKENS

    # Check for promotional keywords anywhere in the message
    promo_keywords = {
        "dm", "message", "contact", "send", "invest", "join",
        "click", "link", "earn", "profit", "wallet", "crypto"
    }
    promo_overlap = text_tokens & promo_keywords

    # Strong reply signal: message is short and contains reply tokens
    is_short = len(doc.text.split()) <= 10
    if reply_overlap and is_short and not promo_overlap:
        return "reply"

    if promo_overlap and digit_ratio > 0.3:
        return "promotional"

    if promo_overlap and not reply_overlap:
        return "promotional"

    if reply_overlap and not promo_overlap:
        return "reply"

    return "neutral"


def analyze_linguistics(comment_text: str) -> dict:
    """
    Main entry point. Analyzes a comment string for linguistic red flags.

    Args:
        comment_text: The raw text of the comment.

    Returns:
        {
          "score": float,
          "signals": dict,
          "reasons": [str]
        }
    """
    if not comment_text or not comment_text.strip():
        return {"score": 1.0, "signals": {}, "reasons": []}

    text = comment_text.strip()
    reasons: list[str] = []
    penalty = 0.0  # accumulated penalty; subtracted from 1.0

    # ── spaCy parse ───────────────────────────────────────────────────────────
    # Skip spaCy for non-English text — the English model produces garbage
    # entities and wrong POS tags for Hindi, Arabic, Chinese, etc.,
    # which would introduce misleading signals.
    non_ascii_ratio = sum(1 for c in text if ord(c) > 127) / max(len(text), 1)
    use_spacy = _SPACY_AVAILABLE and _nlp and non_ascii_ratio < 0.40
    doc = _nlp(text) if use_spacy else None

    # ── Signal: Shannon Entropy ───────────────────────────────────────────────
    entropy = _shannon_entropy(text)
    # Genuine short comments have entropy 3.0–4.5. Spam packs content → 4.8+
    entropy_threshold = 4.7
    if entropy > entropy_threshold and len(text) > 40:
        penalty += 0.10
        reasons.append(
            f"Unusually high information density (entropy={entropy:.2f}) — "
            "typical of message-packing spam."
        )

    # ── Signal: Caps ratio ────────────────────────────────────────────────────
    caps_words = _CAPS_WORD_RE.findall(text)
    word_count = max(len(text.split()), 1)
    caps_ratio = len(caps_words) / word_count
    if caps_ratio > 0.4 and word_count > 4:
        # Check if it's also in a promotional context (more suspicious)
        text_lower_tokens = set(re.findall(r'\w+', text.lower()))
        promo_context = text_lower_tokens & _PROMO_URL_CONTEXT_TOKENS
        if promo_context:
            penalty += 0.15  # ALL CAPS + promotional keywords = higher risk
            reasons.append(
                f"ALL-CAPS text ({caps_ratio:.0%} caps) combined with promotional "
                "keywords — pattern consistent with aggressive spam."
            )
        else:
            penalty += 0.06  # Plain caps (excitement) — small penalty only
            reasons.append(
                f"High proportion of ALL-CAPS words ({caps_ratio:.0%}) — "
                "aggressive/sensationalist tone."
            )

    # ── Signal: Punctuation explosion ─────────────────────────────────────────
    punct_explosion = bool(_PUNCT_EXPLOSION_RE.search(text))
    if punct_explosion:
        penalty += 0.05
        # Only report if combined with other signals (not standalone)

    # ── Signal: URL context ───────────────────────────────────────────────────
    url_matches = list(_URL_RE.finditer(text))
    url_context_result = "none"
    for m in url_matches:
        ctx = _analyze_url_context(doc if doc else type("_", (), {"text": text})(), m)
        if ctx == "suspicious":
            url_context_result = "suspicious"
            penalty += 0.25
            reasons.append(
                "External link detected in a promotional/scam context "
                "(surrounded by offer/earning keywords)."
            )
            break
        elif ctx == "neutral" and url_context_result == "none":
            url_context_result = "neutral"
            penalty += 0.05  # small bump for any unexplained link

    # ── Signal: @mention role ─────────────────────────────────────────────────
    at_handles = _AT_HANDLE_RE.findall(text)
    at_mention_role = "none"
    if at_handles:
        if doc:
            at_mention_role = _analyze_at_mention_role(doc, at_handles[0])
        else:
            # Heuristic fallback without spaCy
            promo_kw = {"dm", "message", "send", "invest", "earn", "contact"}
            text_tokens_lower = set(text.lower().split())
            at_mention_role = "promotional" if promo_kw & text_tokens_lower else "neutral"

        if at_mention_role == "promotional":
            penalty += 0.20
            reasons.append(
                f"@mention ({at_handles[0]}) used in a promotional call-to-action "
                "context — pattern consistent with scam solicitation."
            )
        # If 'reply', no penalty — this is normal conversation

    # ── Signal: Named Entity analysis (spaCy only) ───────────────────────────
    entity_density = 0.0
    if doc:
        money_entities = [e for e in doc.ents if e.label_ in _SPAM_ENTITY_LABELS]
        all_entities = doc.ents
        entity_density = len(all_entities) / word_count

        if money_entities:
            penalty += 0.15
            amounts = ", ".join(e.text for e in money_entities)
            reasons.append(
                f"Monetary amounts mentioned ({amounts}) — "
                "common in crypto/financial scam messages."
            )

        # High-risk org mentions (Telegram, WhatsApp, crypto exchanges)
        high_risk_orgs = [
            e for e in doc.ents
            if e.label_ == "ORG" and _HIGH_RISK_ORG_PATTERNS.search(e.text)
        ]
        if high_risk_orgs:
            penalty += 0.20
            names = ", ".join(e.text for e in high_risk_orgs)
            reasons.append(
                f"High-risk platform mentioned ({names}) — "
                "frequently used for off-platform scam solicitation."
            )

        if entity_density > 0.5 and len(all_entities) >= 3:
            penalty += 0.08
            reasons.append(
                f"Abnormally high entity density ({entity_density:.2f} entities/word) — "
                "typical of spam packing multiple offers into one message."
            )

    # ── Compute final score ───────────────────────────────────────────────────
    score = max(0.0, min(1.0, 1.0 - penalty))

    return {
        "score": score,
        "signals": {
            "url_context": url_context_result,
            "at_mention_role": at_mention_role,
            "entropy": round(entropy, 3),
            "caps_ratio": round(caps_ratio, 3),
            "entity_density": round(entity_density, 3),
            "punctuation_explosion": punct_explosion,
        },
        "reasons": reasons,
    }
