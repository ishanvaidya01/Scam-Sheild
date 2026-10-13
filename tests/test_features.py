"""
tests/test_features.py

Unit tests for feature extraction and deterministic intent rules.
"""

import os
import sys
import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from ml.intent_rules import match_intent_rules, WALLET_RE, LINK_RE, SOLICITATION_RE
from ml.campaign_detector import extract_skeleton, skeleton_jaccard


def test_intent_rules_wallet():
    text = "Send 0.5 ETH to 0x71C84183204990235b275490fDB58414C240CA06 now!"
    res = match_intent_rules(text)
    assert res["has_intent_rule_hit"] is True
    assert "crypto_wallet" in res["matched_patterns"]


def test_intent_rules_telegram():
    text = "Claim free bonus at t.me/official_bonus_2026 limited time!"
    res = match_intent_rules(text)
    assert res["has_intent_rule_hit"] is True
    assert "external_or_shortener_link" in res["matched_patterns"]


def test_intent_rules_clean_text():
    text = "GG guys that was an awesome play, clip it!"
    res = match_intent_rules(text)
    assert res["has_intent_rule_hit"] is False
    assert len(res["matched_patterns"]) == 0


def test_skeleton_extraction():
    t1 = "Send 10 btc to 0x71C84183204990235b275490fDB58414C240CA06 via https://t.me/drop"
    skel = extract_skeleton(t1)
    assert "WALLET" in skel
    assert "LINK" in skel
    assert "NUM" in skel


def test_skeleton_jaccard():
    s1 = "send num coin to wallet"
    s2 = "send num coin to wallet"
    assert skeleton_jaccard(s1, s2) == 1.0

    s3 = "hello how are you"
    assert skeleton_jaccard(s1, s3) == 0.0
