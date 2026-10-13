import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
import json
import time
import logging
import pandas as pd
from typing import Dict, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ml.fusion import get_trust_score
from ml.session_state import SessionState
from ml.coordination_engine import TIME_WINDOW_SECONDS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Scam Shield ML Engine",
    description=(
        "5-signal ensemble ML backend for real-time YouTube live chat "
        "bot and scam detection. Patent-pending architecture."
    ),
    version="2.0.0",
)

# Allow origins: in production set ALLOWED_ORIGINS env var
# e.g. ALLOWED_ORIGINS="chrome-extension://abc123,http://localhost:3000"
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "*")
_allowed_origins = [o.strip() for o in _raw_origins.split(",")] if _raw_origins != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Session Manager ────────────────────────────────────────────────────────────

class ConnectionManager:
    """
    Manages active WebSocket connections and their associated SessionState objects.

    Each connection gets its own SessionState which holds:
      - Rolling comment window (for coordination detection)
      - Per-user behavioral profiles
      - Cross-user network graph edges
      - Session statistics
    """

    def __init__(self):
        # Maps WebSocket → SessionState
        self._sessions: Dict[WebSocket, SessionState] = {}

    async def connect(self, websocket: WebSocket, sensitivity: int = 3) -> SessionState:
        await websocket.accept()
        session = SessionState(sensitivity=sensitivity)
        self._sessions[websocket] = session
        logger.info(f"New client connected. Sensitivity={sensitivity}. "
                    f"Total active: {len(self._sessions)}")
        return session

    def disconnect(self, websocket: WebSocket):
        if websocket in self._sessions:
            session = self._sessions.pop(websocket)
            logger.info(
                f"Client disconnected. Session stats — "
                f"scanned={session.total_scanned}, "
                f"flagged={session.total_flagged}, "
                f"scam={session.total_scam}"
            )

    def get_session(self, websocket: WebSocket) -> Optional[SessionState]:
        return self._sessions.get(websocket)

    async def broadcast(self, message: dict):
        dead = []
        for ws in list(self._sessions.keys()):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    @property
    def active_count(self) -> int:
        return len(self._sessions)

    def get_all_stats(self) -> list:
        stats = []
        for ws, session in self._sessions.items():
            stats.append({
                "total_scanned": session.total_scanned,
                "total_flagged": session.total_flagged,
                "total_scam": session.total_scam,
                "sensitivity": session.sensitivity,
                "session_age_seconds": (
                    int(time.time() * 1000) - session.started_at
                ) // 1000,
            })
        return stats


manager = ConnectionManager()


# ── Rolling window cleanup ─────────────────────────────────────────────────────

def clean_window(session: SessionState, current_time_ms: int):
    """Removes comments older than TIME_WINDOW_SECONDS from the rolling window."""
    cutoff = current_time_ms - (TIME_WINDOW_SECONDS * 1000)
    session.rolling_window = [
        c for c in session.rolling_window if c.get("timestamp", 0) >= cutoff
    ]


# ── WebSocket endpoint ─────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Main scoring WebSocket. Accepts comment events, runs the 5-signal ensemble,
    and returns scored results.

    Message format (client → server):
      { "comment_id": str, "text": str, "username": str, "timestamp": int (unix ms) }

    Optionally, send a control message to update sensitivity:
      { "type": "SET_SENSITIVITY", "value": int (1–5) }

    Response format (server → client):
      {
        "comment_id": str,
        "trust_score": float,
        "tier": str,
        "tier_label": str,
        "verdict": str,
        "reasons": [ { "text": str, "type": str, "signal": str } ],
        "signal_breakdown": { "linguistic": f, "text": f, ... },
        "session_stats": { "total_scanned": int, "total_flagged": int, "total_scam": int }
      }
    """
    session = await manager.connect(websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            # ── Control messages ───────────────────────────────────────────────
            if data.get("type") == "SET_SENSITIVITY":
                val = int(data.get("value", 3))
                session.sensitivity = max(1, min(5, val))
                await websocket.send_json({
                    "type": "SENSITIVITY_ACK",
                    "sensitivity": session.sensitivity
                })
                continue

            if data.get("type") == "GET_STATS":
                await websocket.send_json({
                    "type": "STATS",
                    "data": {
                        "total_scanned": session.total_scanned,
                        "total_flagged": session.total_flagged,
                        "total_scam": session.total_scam,
                        "sensitivity": session.sensitivity,
                    }
                })
                continue

            # ── Comment scoring — with timeout guard ──────────────────────────
            comment = data
            current_time = comment.get("timestamp", int(time.time() * 1000))

            # Trim old entries from rolling window
            clean_window(session, current_time)

            # Run 5-signal ensemble in thread pool with a hard timeout.
            # 8 seconds is generous for CPU inference; if it exceeds this
            # (e.g. first cold-start of large model), return a neutral result
            # so the WebSocket never hangs.
            try:
                score_result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, get_trust_score, comment, session
                    ),
                    timeout=8.0,
                )
            except asyncio.TimeoutError:
                logger.warning(f"Scoring timed out for comment {comment.get('comment_id', '?')}")
                score_result = {
                    "comment_id": comment.get("comment_id", ""),
                    "trust_score": 0.5,
                    "tier": "suspicious",
                    "tier_label": "Suspicious",
                    "verdict": "Analysis timed out — scored as suspicious by default.",
                    "reasons": [{"text": "Scoring exceeded time limit. Treated as suspicious.", "type": "info", "signal": "ensemble"}],
                    "signal_breakdown": {"linguistic": 0.5, "text": 0.5, "coordination": 0.5, "behavioral": 0.5, "network": 0.5},
                    "session_stats": {"total_scanned": session.total_scanned, "total_flagged": session.total_flagged, "total_scam": session.total_scam},
                }

            await websocket.send_json(score_result)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except json.JSONDecodeError:
        logger.warning("Received malformed JSON from client.")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        manager.disconnect(websocket)


# ── Feedback endpoint ──────────────────────────────────────────────────────────

class FeedbackPayload(BaseModel):
    comment_id: str
    text: str
    username: str
    reported_label: str  # "genuine" | "scam"
    trust_score: float


_feedback_log: list[dict] = []

@app.post("/feedback")
async def submit_feedback(payload: FeedbackPayload):
    """
    Receives false-positive/false-negative reports from the extension.
    Stores them for future calibrator retraining.

    POST body: { comment_id, text, username, reported_label, trust_score }
    """
    entry = payload.dict()
    entry["reported_at"] = int(time.time() * 1000)
    _feedback_log.append(entry)

    logger.info(
        f"Feedback received: comment_id={entry['comment_id']}, "
        f"label={entry['reported_label']}, score={entry['trust_score']:.3f}"
    )

    # If we have enough feedback, trigger a background recalibration
    if len(_feedback_log) >= 50:
        asyncio.get_event_loop().run_in_executor(None, _recalibrate)

    return {"status": "ok", "total_feedback": len(_feedback_log)}


def _recalibrate():
    """Background task: refit the calibrator from accumulated feedback."""
    try:
        from ml.calibrator import get_calibrator
        raw_scores = [e["trust_score"] for e in _feedback_log]
        true_labels = [1 if e["reported_label"] == "scam" else 0 for e in _feedback_log]
        calibrator = get_calibrator()
        calibrator.fit(raw_scores, true_labels)
        logger.info(f"Calibrator refitted on {len(_feedback_log)} feedback entries.")
    except Exception as e:
        logger.error(f"Recalibration failed: {e}")


# ── Replay endpoint ────────────────────────────────────────────────────────────

@app.post("/replay")
async def replay_csv(
    background_tasks: BackgroundTasks,
    file_path: str = "data/processed/uci_spam.csv",
    speed: float = 1.0,
):
    """
    Reads a CSV and streams scored results to all connected WebSocket clients.
    Useful for demo and evaluation.
    """
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    def run_replay():
        try:
            df = pd.read_csv(file_path)
            logger.info(f"Replaying {len(df)} rows from {file_path} at {speed}x speed...")

            # Create a temporary session for replay
            replay_session = SessionState(sensitivity=3)

            for _, row in df.iterrows():
                comment = {
                    "comment_id": str(row.get("comment_id", "")),
                    "text": str(row.get("text", "")),
                    "username": str(row.get("username", "")),
                    "timestamp": int(time.time() * 1000),
                }

                current_time = comment["timestamp"]
                clean_window(replay_session, current_time)

                score_result = get_trust_score(comment, replay_session)

                # Broadcast to all active connections
                for ws in list(manager._sessions.keys()):
                    try:
                        asyncio.run_coroutine_threadsafe(
                            ws.send_json(score_result),
                            asyncio.get_event_loop(),
                        )
                    except Exception:
                        pass

                time.sleep(1.0 / speed)

            logger.info("Replay finished.")
        except Exception as e:
            logger.error(f"Replay error: {e}", exc_info=True)

    background_tasks.add_task(run_replay)
    return {"status": "Replay started", "file": file_path, "speed": speed}


# ── Health / Stats endpoints ───────────────────────────────────────────────────

@app.get("/")
def health_check():
    return {
        "status": "ok",
        "version": "2.0.0",
        "active_connections": manager.active_count,
    }


@app.get("/stats")
def global_stats():
    """Returns aggregate stats across all active sessions."""
    all_stats = manager.get_all_stats()
    if not all_stats:
        return {"sessions": 0, "totals": {}}
    return {
        "sessions": len(all_stats),
        "totals": {
            "scanned": sum(s["total_scanned"] for s in all_stats),
            "flagged": sum(s["total_flagged"] for s in all_stats),
            "scam": sum(s["total_scam"] for s in all_stats),
        },
        "per_session": all_stats,
    }


@app.get("/feedback/export")
def export_feedback():
    """Returns the accumulated feedback log (for retraining / audit)."""
    return {"count": len(_feedback_log), "entries": _feedback_log}
