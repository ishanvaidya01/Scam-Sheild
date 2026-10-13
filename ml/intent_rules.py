"""
ml/intent_rules.py

Deterministic rule-based intent matching for overt scam and solicitation indicators.
Replaces the heavyweight spaCy linguistic analyzer.
Focuses strictly on surface forms that an attacker must expose to monetize:
  - URLs and known link shorteners
  - Off-platform contact channels (Telegram, WhatsApp, Discord)
  - Crypto wallet addresses
  - Direct solicitation keywords (DM, profit, investment, giveaway)
"""

import re
from typing import Dict, List

# ── Regex Patterns ────────────────────────────────────────────────────────────

WALLET_RE = re.compile(
    r"\b(0x[a-fA-F0-9]{40}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b"
)

LINK_RE = re.compile(
    r"\b(?:https?://|t\.me/|wa\.me/|chat\.whatsapp\.com/|discord\.gg/|bit\.ly/|tinyurl\.com/|cutt\.ly/|rb\.gy/|linktr\.ee/)\S+",
    re.IGNORECASE,
)

HANDLE_RE = re.compile(r"@[\w.]{3,}")

SOLICITATION_RE = re.compile(
    r"\b(?:dm\s+(?:me|on)|contact\s+(?:me|on|via)|whatsapp|telegram|invest(?:ment)?|guaranteed\s+profit|claim\s+(?:free|bonus|reward|giveaway)|send\s+\d+\s*(?:btc|eth|sol|usdt))\b",
    re.IGNORECASE,
)


def match_intent_rules(text: str) -> Dict[str, any]:
    """
    Scans a message for high-precision solicitation and contact patterns.
    Returns matched features and a boolean flag.
    """
    if not text:
        return {"has_intent_rule_hit": False, "matched_patterns": []}

    matches: List[str] = []
    if WALLET_RE.search(text):
        matches.append("crypto_wallet")
    if LINK_RE.search(text):
        matches.append("external_or_shortener_link")
    if SOLICITATION_RE.search(text):
        matches.append("solicitation_keyword")
    if HANDLE_RE.search(text) and ("telegram" in text.lower() or "whatsapp" in text.lower() or "dm" in text.lower()):
        matches.append("handle_with_contact_intent")

    return {
        "has_intent_rule_hit": len(matches) > 0,
        "matched_patterns": matches,
        "hit_count": len(matches),
    }
