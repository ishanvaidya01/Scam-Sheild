"""
demo/replay_server.py

Dedicated Replay Server for live demonstration of Scam Shield.
Serves the interactive dashboard and streams authentic live chat sessions
with injected stealth attacks at adjustable playback speeds (1x, 5x, 20x).
Supports side-by-side comparison (Text-Only B2 vs Full System B4).
"""

import os
import sys
import json
import time
import asyncio
import logging
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from ml.session_state import SessionState
from ml.text_scorer import score_text
from ml.campaign_detector import extract_campaign_features, clean_window
from ml.learned_fusion import get_learned_fusion_model

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("demo_replay")

app = FastAPI(title="Scam Shield Demo Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEMO_DIR = os.path.join(ROOT_DIR, "demo")
DATA_DIR = os.path.join(ROOT_DIR, "data")


def load_injected_session(stealth_level: str = "L2") -> List[Dict[str, Any]]:
    """Loads a frozen injected session for demonstration."""
    filename = f"session_eminem_test_{stealth_level}.jsonl"
    fpath = os.path.join(DATA_DIR, "injected", filename)
    if not os.path.exists(fpath):
        # Fallback to dev or raw session
        fpath = os.path.join(DATA_DIR, "sessions", "uci_eminem.jsonl")

    messages = []
    if os.path.exists(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    messages.append(json.loads(line))

    # Sort by timestamp
    messages.sort(key=lambda m: m.get("ts_ms", m.get("timestamp", 0)))
    return messages


@app.get("/")
def get_index():
    index_path = os.path.join(DEMO_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Demo index.html not found"}


@app.websocket("/ws/demo")
async def demo_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Demo client connected.")

    session_state = SessionState()
    fusion_model = get_learned_fusion_model()

    is_running = False
    speed = 1.0
    stealth_level = "L2"
    side_by_side = True

    # Running metrics
    stats = {
        "scanned": 0,
        "attacks_total": 0,
        "attacks_detected_b4": 0,
        "attacks_detected_b2": 0,
        "genuine_total": 0,
        "genuine_fp_b4": 0,
        "genuine_fp_b2": 0,
        "abstained": 0,
    }

    async def run_stream():
        nonlocal is_running, speed, stealth_level, stats, session_state
        messages = load_injected_session(stealth_level)
        logger.info(f"Loaded {len(messages)} messages for level {stealth_level}.")

        session_state = SessionState()
        stats = {k: 0 for k in stats}

        for idx, msg in enumerate(messages):
            if not is_running:
                break

            current_ts = msg.get("ts_ms", int(time.time() * 1000))
            text = msg.get("text", "")
            username = msg.get("author_hash", "anon")
            comment_id = msg.get("msg_id", f"msg_{idx}")
            gt = msg.get("ground_truth", "genuine")
            is_attack = (gt == "attack" or msg.get("label") == "scam_campaign")

            clean_window(session_state, current_ts)

            # User profile tracking
            prof = session_state.get_or_create_profile(username)
            prof.record_message(text, current_ts)

            # B2: Text-Only scoring
            b2_text_res = score_text(text)
            b2_scam_prob = b2_text_res.get("scam_prob", 0.0)
            b2_flagged = (b2_scam_prob >= 0.50)

            # B4: Full Campaign & Learned Fusion scoring
            camp_feat, cluster_meta = extract_campaign_features(msg, session_state)
            camp_feat["text_scam_prob"] = b2_scam_prob
            b4_output = fusion_model.score_features(camp_feat, cluster_meta)

            # Update rolling window
            session_state.rolling_window.append({
                "comment_id": comment_id,
                "text": text,
                "username": username,
                "timestamp": current_ts,
                "embedding": msg.get("embedding"),
                "skeleton": msg.get("skeleton"),
            })

            # Update running stats
            stats["scanned"] += 1
            if is_attack:
                stats["attacks_total"] += 1
                if b4_output["verdict"] == "likely_campaign":
                    stats["attacks_detected_b4"] += 1
                if b2_flagged:
                    stats["attacks_detected_b2"] += 1
            else:
                stats["genuine_total"] += 1
                if b4_output["verdict"] == "likely_campaign":
                    stats["genuine_fp_b4"] += 1
                if b2_flagged:
                    stats["genuine_fp_b2"] += 1

            if b4_output["unverifiable"]:
                stats["abstained"] += 1

            # Precision & Recall calculations
            rec_b4 = (stats["attacks_detected_b4"] / stats["attacks_total"]) if stats["attacks_total"] > 0 else 0.0
            rec_b2 = (stats["attacks_detected_b2"] / stats["attacks_total"]) if stats["attacks_total"] > 0 else 0.0
            flagged_b4 = stats["attacks_detected_b4"] + stats["genuine_fp_b4"]
            flagged_b2 = stats["attacks_detected_b2"] + stats["genuine_fp_b2"]
            prec_b4 = (stats["attacks_detected_b4"] / flagged_b4) if flagged_b4 > 0 else 1.0
            prec_b2 = (stats["attacks_detected_b2"] / flagged_b2) if flagged_b2 > 0 else 1.0

            # Payload to client
            payload = {
                "type": "MESSAGE_SCORED",
                "message": {
                    "msg_id": comment_id,
                    "text": text,
                    "author": username,
                    "timestamp": current_ts,
                    "ground_truth": gt,
                    "stealth_level": msg.get("stealth_level", "none"),
                },
                "b4": {
                    "trust_score": b4_output["trust_score"],
                    "verdict": b4_output["verdict"],
                    "verdict_label": b4_output["verdict_label"],
                    "unverifiable": b4_output["unverifiable"],
                    "reasons": b4_output["reasons"],
                    "features": {
                        "cluster_cohesion": round(camp_feat.get("cluster_cohesion", 0.0), 3),
                        "cluster_accounts": int(camp_feat.get("cluster_account_count", 1)),
                        "rate_synchrony": round(camp_feat.get("rate_normalized_synchrony", 0.0), 3),
                        "off_topic": round(camp_feat.get("off_topic_distance", 0.0), 3),
                    },
                },
                "b2": {
                    "scam_prob": round(b2_scam_prob, 3),
                    "is_flagged": b2_flagged,
                    "verdict": "Likely Campaign" if b2_flagged else "Clear",
                },
                "stats": {
                    "scanned": stats["scanned"],
                    "attacks_total": stats["attacks_total"],
                    "recall_b4": round(rec_b4, 3),
                    "recall_b2": round(rec_b2, 3),
                    "prec_b4": round(prec_b4, 3),
                    "prec_b2": round(prec_b2, 3),
                    "abstained": stats["abstained"],
                    "fp_b4": stats["genuine_fp_b4"],
                },
                "cluster_meta": cluster_meta,
            }

            try:
                await websocket.send_json(payload)
            except Exception:
                break

            # Sleep adjusted by playback speed
            delay = 0.5 / max(speed, 0.2)
            await asyncio.sleep(delay)

        is_running = False
        try:
            await websocket.send_json({"type": "STREAM_FINISHED"})
        except Exception:
            pass

    stream_task: Optional[asyncio.Task] = None

    try:
        while True:
            raw = await websocket.receive_text()
            cmd = json.loads(raw)
            c_type = cmd.get("type")

            if c_type == "START":
                speed = float(cmd.get("speed", 1.0))
                stealth_level = cmd.get("stealth_level", "L2")
                side_by_side = bool(cmd.get("side_by_side", True))
                is_running = True
                if stream_task and not stream_task.done():
                    stream_task.cancel()
                stream_task = asyncio.create_task(run_stream())

            elif c_type == "PAUSE":
                is_running = False

            elif c_type == "SET_SPEED":
                speed = float(cmd.get("speed", 1.0))

            elif c_type == "SET_LEVEL":
                stealth_level = cmd.get("stealth_level", "L2")
                is_running = True
                if stream_task and not stream_task.done():
                    stream_task.cancel()
                stream_task = asyncio.create_task(run_stream())

    except WebSocketDisconnect:
        is_running = False
        if stream_task and not stream_task.done():
            stream_task.cancel()
        logger.info("Demo client disconnected.")


# Mount static assets if demo directory exists
if os.path.exists(DEMO_DIR):
    app.mount("/static", StaticFiles(directory=DEMO_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    print("Starting Scam Shield Replay Server on http://localhost:8001...")
    uvicorn.run(app, host="127.0.0.1", port=8001)
