# Scam Shield — Architecture & File Guide

> **Who this file is for:** Anyone joining the project, a reviewer, or the developer
> needing a quick reference to understand what every file does, what pattern it follows,
> and how data flows through the system.

---

## Project at a Glance

```
IDP/
+-- backend/          FastAPI ML server (Python)
+-- ml/               All machine learning modules
+-- extension/        Chrome Extension (JS + CSS)
+-- scripts/          Utility scripts (data, testing)
+-- data/             Raw + processed datasets
+-- install.py        One-shot dependency installer
+-- README.md         Quick-start guide
+-- ARCHITECTURE.md   This file
```

**Runtime flow:**
```
YouTube live chat DOM
  ? content.js (MutationObserver)
    ? background.js (WebSocket)
      ? backend/main.py (FastAPI)
        ? ml/fusion.py (5-signal ensemble)
          ? badge + popover rendered in chat
```

---

## BACKEND — `backend/`

### `backend/main.py`
**Role:** The central server. Entry point for the entire ML pipeline.

**Architecture pattern:** Async event-driven server with per-connection state isolation.

**What it does:**
- Starts a FastAPI application with full async WebSocket support
- Every browser tab that connects gets its own `SessionState` object (isolated)
- On each comment, calls `clean_window()` to trim old entries, then `get_trust_score()` wrapped in an 8-second timeout so the WebSocket never freezes
- Fans scored results back to the extension via the same WebSocket

**Endpoints:**

| Endpoint | Method | What it does |
|---|---|---|
| `/ws` | WebSocket | Main scoring pipeline. Receives comment JSON, returns scored result JSON |
| `/` | GET | Health check |
| `/stats` | GET | Aggregate stats across all active sessions |
| `/feedback` | POST | Accepts false-positive reports from the extension |
| `/feedback/export` | GET | Downloads all collected feedback as JSONL |
| `/replay` | POST | Runs a CSV through the full scoring pipeline offline |

**WebSocket message protocol:**

Incoming (extension ? server):
```json
{ "comment_id": "abc123", "text": "Buy BTC now!", "username": "bot_001", "timestamp": 1695000000000 }
```

Control messages:
```json
{ "type": "SET_SENSITIVITY", "value": 3 }
{ "type": "GET_STATS" }
```

Outgoing (server ? extension):
```json
{
  "comment_id": "abc123",
  "trust_score": 0.08,
  "tier": "scam",
  "tier_label": "?? Scam / Bot",
  "verdict": "?? Scam / Bot — Highly likely automated or scam content.",
  "reasons": [ { "text": "...", "type": "flag", "signal": "coordination" } ],
  "signal_breakdown": { "linguistic": 0.6, "text": 0.1, "coordination": 0.0, "behavioral": 0.3, "network": 1.0 }
}
```

**CORS:** Controlled via `ALLOWED_ORIGINS` environment variable. Defaults to `*` in development.

---

## ML ENGINE — `ml/`

### `ml/session_state.py`
**Role:** The shared memory store for a single user session (one WebSocket connection = one session).

**Architecture pattern:** Dataclass-based value object passed by reference through every signal module.

**Contains:**
- `rolling_window: List[dict]` — All recent comments in the last 60 seconds. Used by Coordination + Network signals.
- `user_profiles: Dict[str, UserProfile]` — Per-username behavioral history for the session.
- `graph_edges: Dict[frozenset, float]` — Persistent weighted edges for the Network graph signal.
- `total_scanned / total_flagged / total_scam` — Session counters for the popup dashboard.
- `sensitivity: int` — 1–5 slider value from the user's popup.

**`UserProfile` nested class:**
Tracks per-user state: all message timestamps (for velocity), all message texts (for TTR + self-similarity), flagged count.

Methods:
- `get_velocity(window_seconds)` — Messages per N seconds
- `get_type_token_ratio()` — Unique words / total words across all session messages
- `is_first_message()` — True if this is the user's 1st message this session
- `get_sensitivity_threshold()` — Maps 1–5 to score threshold (0.25–0.65)
- `get_coordination_weight()` — Maps 1–5 to coordination weight (0.20–0.50)

---

### `ml/fusion.py`
**Role:** The brain. Orchestrates all 5 signals and combines them into one final trust score.

**Architecture pattern:** Weighted ensemble with hard overrides and calibrated output.

**Default signal weights (sensitivity=3, always sum to 1.0):**
```
coordination: 0.35   behavioral: 0.30   text: 0.18
linguistic:   0.12   network:    0.05
```

**Execution order inside `get_trust_score()`:**
1. Get/create UserProfile ? record_message()
2. Run Signal 3 (Coordination) — needs rolling_window BEFORE current message is appended
3. Run Signal 1 (Linguistic) — stateless text analysis
4. Run Signal 2 (Text Classifier) — stateless text analysis
5. Run Signal 4 (Behavioral) — reads UserProfile state
6. Run Signal 5 (Network) — reads session graph edges
7. Collect all signal scores and reasons
8. Check hard overrides (wallet address, self-repeat, clique)
9. Compute weighted ensemble score
10. Calibrate via IsotonicRegression
11. Determine tier (trusted/likely/suspicious/high_risk/scam)
12. Update session stats
13. Build explanation via ExplainabilityEngine
14. Append current comment to rolling_window
15. Return full result dict

**Hard overrides** (bypass the weighted average entirely):

| Condition | Score cap |
|---|---|
| Crypto wallet address found | 0.03 |
| Bot ring (clique = 4 + coordinated) | 0.02 |
| Extreme velocity + spam text | 0.05 |
| Self-repeat 2+ times | 0.10 |
| Self-repeat 1 time | 0.20 |

Every signal call is wrapped in `try/except` — if any signal crashes, it returns a neutral score (1.0) and the system continues.

---

### `ml/linguistic_analyzer.py` — Signal 1 (weight: 12%)
**Role:** NLP-based analysis of sentence structure and context.

**Architecture pattern:** Rule-based NLP pipeline using spaCy's dependency parser and named entity recognition.

**Key insight:** Does NOT flag on keywords alone — every signal is contextual.

| Signal | How | Example |
|---|---|---|
| @mention role | spaCy POS + surrounding tokens | `@friend nice!` ? safe. `send ETH to @CryptoBot` ? flag |
| URL context | ±80 char window for promo keywords | youtube.com ? safe. `earn BTC https://...` ? flag |
| ALL-CAPS ratio | Word count ratio + promo keyword check | Plain caps: 0.06 penalty. Caps + promo keywords: 0.15 penalty |
| Shannon entropy | Character frequency distribution | High entropy + >40 chars ? packing content = flag |
| Named entities | spaCy MONEY, PERCENT, ORG labels | `$500 guaranteed` or `Telegram group` ? penalize |
| Punctuation explosion | 3+ `!` or `?` in a row | Minor standalone signal |

**Non-English detection:** If >40% characters are non-ASCII, spaCy is skipped entirely. Regex checks still run.

---

### `ml/text_scorer.py` — Signal 2 (weight: 18%)
**Role:** Content classification using pre-trained transformers.

**Architecture pattern:** Lazy-loaded ML model with LRU cache (800 entries).

Two sub-models combined: `0.75 × zero_shot_score + 0.25 × tiny_clf_score`

**Regex pattern library** (always fires, no ML required):

| Pattern | Condition |
|---|---|
| External URL | If surrounded by promo keywords OR is a known shortener domain |
| @handle | If message contains promo action words |
| DM solicitation | If message contains offer/financial keywords |
| Crypto wallet address | Always flagged |
| Telegram / Discord link | Always flagged |
| Financial bait phrases | Always flagged (20+ phrases: airdrop, NFT giveaway, rug pull, etc.) |
| URL shorteners (bit.ly, tinyurl, linktr.ee...) | Always flagged |

---

### `ml/coordination_engine.py` — Signal 3 (weight: 35%)
**Role:** Detect synchronized, organized bot attacks.

**Architecture pattern:** Rolling-window multi-detector with sentence embeddings (all-MiniLM-L6-v2).

**Four sub-detectors:**

**Sub-detector 1 — Cross-user semantic similarity**
Encodes new message, compares cosine similarity (threshold: 0.83) against all OTHER users in 60s window.
2+ different accounts with similar content ? coordination flag.

**Sub-detector 2 — Lexical template detection**
Extracts structural "skeletons" by replacing variables with typed placeholders.
`"Send 0.5 BTC to @CryptoHelper"` ? `"send AMOUNT COIN to @HANDLE"`
Skeleton Jaccard overlap = 0.80 across other users ? template attack flag.

**Sub-detector 3 — Poisson burst test**
Models message arrival as Poisson process. p < 0.01 = statistically anomalous burst.

**Sub-detector 4 — Self-repetition (novel)**
Checks the SAME user's past messages (ignored by Sub-detector 1).
Three methods: exact match ? skeleton overlap (= 0.85) ? semantic similarity (= 0.90).
1 repeat ? +40% penalty. 2+ repeats ? +70% penalty + hard score cap.

---

### `ml/behavioral_profiler.py` — Signal 4 (weight: 30%)
**Role:** Track what this specific user has done in this session.

**Architecture pattern:** Stateful per-user feature extraction from UserProfile history.

| Feature | Bot threshold |
|---|---|
| Message velocity | = 7 msgs/min = flag, = 12 = severe |
| Self-similarity (Jaccard vs. own past messages) | = 0.70 similarity to 1+ past message |
| Type-Token Ratio across session | TTR < 0.25 with 3+ messages = template bot |
| First-message promotional risk | First message + promo keywords ? +0.20 penalty |
| Username structure | Digit ratio > 40% or high character entropy ? suspicious |
| Prior flags in session | = 2 prior flagged messages ? +0.20 escalation |

---

### `ml/network_analyzer.py` — Signal 5 (weight: 5%)
**Role:** Detect hidden bot rings using graph theory.

**Architecture pattern:** Live incremental graph using NetworkX. Edges persist for the full session.

**Graph:** Nodes = usernames. Edges = drawn when two users' messages have cosine similarity = 0.80.

| Detector | Finds | Penalty |
|---|---|---|
| Clique detection (nx.find_cliques) | 3+ fully interconnected users = bot ring | +0.50 |
| Hub detection | User connected to 4+ others = template distributor | +0.30 |
| Graph density | Session density > 0.60 with 5+ nodes = campaign | +0.15 |

---

### `ml/calibrator.py`
**Role:** Convert raw ensemble scores into well-calibrated probabilities using isotonic regression.

Two modes:
1. **Fitted mode** (when `_calibrator_model.pkl` exists): Uses sklearn IsotonicRegression trained on collected feedback.
2. **Fallback mode** (default): Applies logistic smoothing to push borderline scores toward extremes.

Updated by calling `calibrator.fit(raw_scores, true_labels)` with feedback export data.

---

### `ml/explainability.py`
**Role:** Convert raw signal outputs into human-readable, ordered reasons for the popover.

**What it builds:**
1. Collects all reason strings from all 5 signals
2. Tags each with its source signal
3. Adds coordination sub-signal explanations (burst p-value, template match)
4. Adds positive signals for clean messages (high TTR, normal velocity, no clique)
5. Caps total reasons at 8 for readability
6. Generates a one-line verdict: `"?? Scam / Bot — Highly likely automated..."`

---

### `ml/evaluate.py`
**Role:** Offline accuracy measurement against a labeled dataset.

Runs Text Classifier + Linguistic Analyzer on `data/processed/uci_spam.csv`.
Reports Precision, Recall, F1 per signal and fused. Writes to `ml/eval_results.md`.

**Run:** `python ml/evaluate.py`

---

## EXTENSION — `extension/`

### `extension/manifest.json`
Chrome Manifest V3 declaration. Key: `host_permissions: youtube.com only`, `permissions: storage`.

---

### `extension/background.js`
**Role:** Service worker. Manages the single persistent WebSocket connection to the backend.

**Architecture pattern:** Central message broker using Chrome Port API.

**Why single WebSocket:** All tabs share one session ? coordination detection works correctly across chat messages from different users.

**Startup:** Reads `backendHost` and `sensitivity` from `chrome.storage.local`, then opens WebSocket.

**Message routing:**
- Content script ? background: `NEW_COMMENT`, `FEEDBACK`, `SET_SENSITIVITY`, `GET_STATS`
- Backend ? all content scripts: `SCORE_RESULT` (fanned out to all ports)

Automatically reconnects with 2s delay if WebSocket closes.

---

### `extension/content.js`
**Role:** YouTube DOM observer. Detects every new comment, sends it to background, and renders trust badges.

**Architecture pattern:** MutationObserver + incremental, idempotent DOM manipulation.

**Flow:**
1. Watch `#chat-messages` and `yt-live-chat-item-list-renderer` for new comment nodes
2. Extract author name, message text, timestamp
3. Assign stable `data-ss-id` hash (skipping elements already badged)
4. Send `NEW_COMMENT` to background.js port
5. On `SCORE_RESULT`, find element by `data-ss-id` and insert `.trust-badge` span

**Popover:** Single floating div repositioned on badge click. Shows trust circle, signal bars, scrollable reasons, feedback button.

---

### `extension/styles.css`
Dark glassmorphism design (rgba + backdrop-filter). Per-tier color classes. Hidden scrollbars on popover via `scrollbar-width: none`. Animated signal bars.

---

### `extension/popup.html / popup.css / popup.js`
Extension popup (toolbar icon click). Shows: live stats (scanned/flagged/scam), shield toggle, sensitivity slider, 5-signal legend with hover tooltips. Stats refresh every 5 seconds via `GET_STATS`.

---

## SCRIPTS — `scripts/`

| File | Purpose | Run |
|---|---|---|
| `simulator.py` | Synthetic load tester — sends mix of clean + spam messages to test coordination | `python scripts/simulator.py` |
| `download_public_data.py` | Downloads UCI YouTube Spam dataset ? saves to `data/processed/uci_spam.csv` | `python scripts/download_public_data.py` |
| `label_data.py` | Interactive CLI to manually label collected comments for calibrator training | `python scripts/label_data.py` |
| `scrape_youtube_chat.py` | Playwright-based scraper — collects raw live chat to JSONL | `python scripts/scrape_youtube_chat.py <URL>` |

---

## Root Files

| File | Purpose |
|---|---|
| `install.py` | One-shot setup: installs pip requirements + downloads spaCy model |
| `README.md` | Quick-start guide, architecture overview, API reference |
| `ARCHITECTURE.md` | This file — full per-file guide |

---

## Full Data Flow

```
[YouTube Page Load]
        ¦
        ?
content.js attaches MutationObserver to chat container
        ¦
   New comment node detected
        ¦
        ?
Extract: { comment_id (stable hash), text, username, timestamp }
        ¦
        ?
background.js ? WebSocket ? backend/main.py
        ¦
        ?
clean_window(session, now)   ? removes comments older than 60s
asyncio.wait_for(get_trust_score(comment, session), timeout=8s)
        ¦
        ?
ml/fusion.py orchestrates:
  +-- Signal 1: linguistic_analyzer.py  (spaCy NLP)
  +-- Signal 2: text_scorer.py          (DistilBERT + regex patterns)
  +-- Signal 3: coordination_engine.py  (embeddings + Poisson burst + self-repeat)
  +-- Signal 4: behavioral_profiler.py  (per-user velocity, TTR, self-similarity)
  +-- Signal 5: network_analyzer.py     (NetworkX clique + hub detection)
        ¦
  Weighted ensemble ? hard overrides ? calibrate ? tier
        ¦
  explainability.py ? verdict + ordered tagged reasons
        ¦
        ?
backend/main.py sends result via WebSocket
        ¦
background.js fans out to all content script ports
        ¦
        ?
content.js:
  ? Insert .trust-badge span into comment DOM element
  ? Badge click ? render floating popover with full analysis
```

---

## Key Design Decisions

| Decision | Why |
|---|---|
| Single WebSocket per browser | Coordination + network signals need one shared session context across all messages |
| Session state in RAM | Zero-latency access. Trade-off: state resets on page reload |
| All signals in try/except | System must never crash during a live stream |
| Hard score overrides separate from weights | Certain signals (wallet, 3× repeat) are near-certain; should not be diluted by averaging |
| Lazy model loading | DistilBERT takes 2–4s to load; done once on first message, not at server startup |
| Configurable via storage/env | Backend host, sensitivity, CORS driven by storage/env — no code changes needed to deploy |
| Non-English spaCy skip | English spaCy model produces garbage entities for Hindi/Arabic — better to skip than mislead |
