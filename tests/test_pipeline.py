"""
tests/test_pipeline.py

Pipeline tests verifying deterministic scoring and state transitions.
"""

import os
import sys
import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from ml.session_state import SessionState
from ml.fusion import get_trust_score


def test_clean_viewer_scoring():
    session = SessionState()
    comment = {
        "comment_id": "test_001",
        "text": "What a great stream! GGWP everyone",
        "username": "viewer_alice",
        "timestamp": 1712000000000,
        "badges": ["member"],
    }
    result = get_trust_score(comment, session)

    assert "trust_score" in result
    assert result["trust_score"] >= 0.70
    assert result["verdict"] in ("clear", "unverifiable")
    assert len(result["reasons"]) <= 3


def test_coordinated_scam_detection():
    session = SessionState()
    base_ts = 1712000000000

    # Simulate coordinated bot wave
    comments = [
        {"comment_id": f"bot_{i}", "text": "Claim 500 USDT bonus at t.me/official_drop_event", "username": f"bot_{i}", "timestamp": base_ts + (i * 1000)}
        for i in range(5)
    ]

    results = [get_trust_score(c, session) for c in comments]
    # The latter messages in the burst must have high campaign probability
    last_res = results[-1]
    assert last_res["campaign_prob"] >= 0.50 or last_res["verdict"] in ("likely_campaign", "suspicious")
    assert len(last_res["reasons"]) <= 3
