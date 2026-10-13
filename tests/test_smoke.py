"""
tests/test_smoke.py

End-to-end smoke test of FastAPI WebSocket endpoint.
"""

import os
import sys
import json
import pytest
from fastapi.testclient import TestClient

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from backend.main import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "2.1.0"


def test_websocket_scoring_smoke():
    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        comment_payload = {
            "comment_id": "smoke_100",
            "text": "Hello stream! Anyone know his current rank?",
            "username": "tester_99",
            "timestamp": 1712000000000,
            "badges": [],
        }
        websocket.send_text(json.dumps(comment_payload))
        raw_resp = websocket.receive_text()
        data = json.loads(raw_resp)

        assert data["comment_id"] == "smoke_100"
        assert "trust_score" in data
        assert "verdict" in data
        assert "reasons" in data
        assert len(data["reasons"]) <= 3
