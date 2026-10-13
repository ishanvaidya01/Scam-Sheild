# Scam Shield — Real-time YouTube Bot/Scam Comment Detector (v2.0)

> **Patent-pending architecture** | 5-Signal Ensemble ML | Real-time WebSocket Pipeline

A production-grade Chrome extension + FastAPI backend that scores every live chat message
on YouTube in real-time using a **5-signal ensemble ML engine** with contextual explainability.

---

## Architecture

```
[Chrome Extension (Manifest V3)]
    │  WebSocket stream of comment events
    ▼
[FastAPI Backend — Async Pipeline]
    │
    ├─► [1] LinguisticAnalyzer     (spaCy NLP — context-aware @/URL analysis)
    ├─► [2] ContextualTextClassifier (Zero-shot DistilBERT — YouTube domain)
    ├─► [3] CoordinationEngine v2   (Semantic + Template + Poisson burst)
    ├─► [4] BehavioralProfiler      (Velocity, TTR, username structure, history)
    └─► [5] NetworkGraphAnalyzer    (Live NetworkX clique & hub detection)
          │
          ▼
    [FusionLayer — Adaptive Weighted Ensemble]
          │
          ▼
    [IsotonicRegression Calibrator] → true probabilities
          │
          ▼
    [ExplainabilityEngine] → human-readable tagged reasons
          │
          ▼
    Response: { trust_score, tier, verdict, reasons[], signal_breakdown{} }
```

### Why this design is novel (patent-differentiating)

| Signal | Novelty |
|---|---|
| **Linguistic** | Context-aware URL/@ analysis using POS tagging — `@user` in replies is NOT flagged |
| **Text Classifier** | Zero-shot classification with YouTube-specific candidate labels, not SMS spam model |
| **Coordination v2** | Lexical template skeleton extraction catches paraphrasing attacks; Poisson burst test for statistical anomaly detection |
| **Behavioral** | In-session per-user profiling (velocity, Type-Token Ratio, first-message risk) |
| **Network Graph** | Live NetworkX graph analysis of cross-user semantic connections — clique = bot ring |
| **Fusion** | Sensitivity-adaptive weights + isotonic calibration + hard overrides |
| **Feedback Loop** | False positive reporting → `/feedback` endpoint → automatic recalibration |

---

## Project Structure

```
/backend        FastAPI app (WebSocket + REST endpoints)
/ml             Core ML engine
  session_state.py        Per-connection state dataclass
  linguistic_analyzer.py  Signal 1: spaCy NLP
  text_scorer.py          Signal 2: Zero-shot classifier
  coordination_engine.py  Signal 3: Semantic + Template + Poisson
  behavioral_profiler.py  Signal 4: Per-user behavior
  network_analyzer.py     Signal 5: NetworkX graph
  fusion.py               Weighted ensemble + calibration
  explainability.py       Human-readable reason engine
  calibrator.py           Isotonic regression score calibration
  evaluate.py             Evaluation scripts
/extension      Chrome Extension (Manifest V3)
/data           Raw and processed datasets
/scripts        Data helpers, simulator, scraper
```

---

## 5-Tier Badge System

| Score | Tier | Badge | Meaning |
|---|---|---|---|
| 0.80–1.00 | Trusted    | ✅ Green  | Strong genuine signals |
| 0.60–0.79 | Likely     | 🔵 Teal   | Mostly genuine, minor signals |
| 0.40–0.59 | Suspicious | ⚡ Amber  | Notable suspicious signals |
| 0.20–0.39 | High Risk  | ⚠️ Orange | Multiple strong bot signals |
| 0.00–0.19 | Scam/Bot   | 🚫 Red   | Definitely automated/scam |

---

## Setup

### 1. Install Python dependencies
```bash
pip install -r backend/requirements.txt
python -m spacy download en_core_web_sm
```

### 2. Download dataset
```bash
python scripts/download_public_data.py
```

### 3. Run backend
```bash
cd backend && uvicorn main:app --reload
```

### 4. Load Chrome extension
- Go to `chrome://extensions/`
- Enable **Developer mode**
- Click **Load unpacked** → select the `extension/` directory

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `WS` | `/ws` | Main scoring WebSocket |
| `GET` | `/` | Health check |
| `GET` | `/stats` | Aggregate session statistics |
| `POST` | `/feedback` | Submit false positive/negative report |
| `POST` | `/replay` | Replay CSV through scoring engine |
| `GET` | `/feedback/export` | Export all collected feedback |

### WebSocket control messages
```json
{ "type": "SET_SENSITIVITY", "value": 3 }   // 1=lenient, 5=strict
{ "type": "GET_STATS" }                       // request session stats
```

---

## Evaluation

Run evaluation against the UCI YouTube Spam dataset:
```bash
python ml/evaluate.py
```

Current baseline: **F1=0.38** (v1 bert-tiny)
Target with v2: **F1 > 0.75**

---

## Synthetic Adversarial Chat Simulator

Waiting for a real coordinated bot attack to occur naturally on a YouTube live stream makes testing difficult. Scam Shield includes a **Synthetic Adversarial Chat Simulator** that generates realistic, controllable adversarial traffic and feeds it into the *exact same ML pipeline* that the Chrome extension uses.

### Why it exists
- Tests the system's ability to catch paraphrased template attacks, bursts, and bot-rings.
- Sends traffic purely over WebSocket without injecting ground truth into the ML model.
- Evaluates Accuracy, Precision, Recall, F1, and Latency under chaotic conditions.

### Available Scenarios (currently implemented)
- `crypto_ring`: Simulates a coordinated bot ring posting similar crypto scam templates while genuine users chatter.

*(More scenarios like `self_repeat`, `paraphrase_attack`, `burst_attack`, `bot_hub`, and `mixed_attack` are planned).*

### How to run it

Ensure the FastAPI backend is running first:
```bash
python -m uvicorn backend.main:app --host localhost --port 8000
```

Run a simulation scenario:
```bash
python scripts/simulator.py --scenario crypto_ring
```

The simulator prints the timeline in real-time and provides a detailed terminal dashboard with evaluation metrics once complete.
