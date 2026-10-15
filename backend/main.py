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

from ml.fusion import get_trust_score
from ml.session_state import SessionState
from ml.coordination_engine import TIME_WINDOW_SECONDS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Scam Shield Engine",
    description="Live chat campaign and scam detection engine.",
    version="2.1.0",
)

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
    """Manages active WebSocket connections and their associated SessionState objects."""

    def __init__(self):
        self._sessions: Dict[WebSocket, SessionState] = {}

    async def connect(self, websocket: WebSocket) -> SessionState:
        await websocket.accept()
        session = SessionState()
        self._sessions[websocket] = session
        logger.info(f"New client connected. Total active: {len(self._sessions)}")
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
    Main scoring WebSocket. Accepts comment events and returns scored results.

    Message format (client → server):
      { "comment_id": str, "text": str, "username": str, "timestamp": int, "badges": list }

    Response format (server → client):
      {
        "comment_id": str,
        "trust_score": float,
        "verdict": "clear" | "suspicious" | "likely_campaign" | "unverifiable",
        "verdict_label": str,
        "unverifiable": bool,
        "reasons": [ { "text": str, "type": str, "signal": str } ],
        "signal_breakdown": dict,
        "session_stats": { "total_scanned": int, "total_flagged": int, "total_scam": int }
      }
    """
    session = await manager.connect(websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            # Control message
            if data.get("type") == "GET_STATS":
                await websocket.send_json({
                    "type": "STATS",
                    "data": {
                        "total_scanned": session.total_scanned,
                        "total_flagged": session.total_flagged,
                        "total_scam": session.total_scam,
                    }
                })
                continue

            # Comment scoring
            comment = data
            current_time = comment.get("timestamp", int(time.time() * 1000))
            clean_window(session, current_time)

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
                    "verdict": "suspicious",
                    "verdict_label": "Suspicious",
                    "unverifiable": True,
                    "reasons": [{"text": "Scoring exceeded time limit.", "type": "info", "signal": "timeout"}],
                    "signal_breakdown": {},
                    "session_stats": {
                        "total_scanned": session.total_scanned,
                        "total_flagged": session.total_flagged,
                        "total_scam": session.total_scam,
                    },
                }

            await websocket.send_json(score_result)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except json.JSONDecodeError:
        logger.warning("Received malformed JSON from client.")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        manager.disconnect(websocket)


# ── Replay endpoint ────────────────────────────────────────────────────────────

@app.post("/replay")
async def replay_data(
    background_tasks: BackgroundTasks,
    file_path: str = "data/processed/uci_spam.csv",
    speed: float = 1.0,
):
    """
    Reads a CSV or JSONL and streams scored results to all connected WebSocket clients.
    """
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    def run_replay():
        try:
            if file_path.endswith(".jsonl"):
                records = []
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            records.append(json.loads(line))
                df = pd.DataFrame(records)
            else:
                df = pd.read_csv(file_path)

            logger.info(f"Replaying {len(df)} rows from {file_path} at {speed}x speed...")
            replay_session = SessionState()

            for _, row in df.iterrows():
                comment = {
                    "comment_id": str(row.get("comment_id", row.get("msg_id", ""))),
                    "text": str(row.get("text", "")),
                    "username": str(row.get("username", row.get("author_hash", ""))),
                    "timestamp": int(row.get("timestamp", row.get("ts_ms", time.time() * 1000))),
                    "badges": row.get("badges", []) if isinstance(row.get("badges"), list) else [],
                }

                current_time = comment["timestamp"]
                clean_window(replay_session, current_time)
                score_result = get_trust_score(comment, replay_session)

                for ws in list(manager._sessions.keys()):
                    try:
                        asyncio.run_coroutine_threadsafe(
                            ws.send_json(score_result),
                            asyncio.get_event_loop(),
                        )
                    except Exception:
                        pass

                time.sleep(1.0 / max(speed, 0.1))

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
        "version": "2.1.0",
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)

