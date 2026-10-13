# Scam Shield — System Architecture & Component Guide

> Technical guide to the 35% build architecture for Scam Shield: real-time YouTube live-chat campaign detection engine.

---

## 1. System Overview

```
[YouTube Live Chat Stream / Replay Server]
                    │
                    ▼
          [Chrome Extension MV3]
         (content.js ──► background.js)
                    │
            WebSocket Connection (/ws)
                    ▼
          [FastAPI Backend Server]
              (backend/main.py)
                    │
                    ▼
          [Scam Shield Fusion Engine]
                (ml/fusion.py)
   ┌────────────────┼────────────────┐
   │                │                │
   ▼                ▼                ▼
[Text Intent]  [Campaign Detector]  [Platform Badges]
(ml/text_intent) (ml/campaign_detector) (Member/Mod)
   │                │                │
   └────────────────┼────────────────┘
                    │  11 Multi-Signal Features
                    ▼
     [Learned Logistic Regression Fusion]
           (ml/learned_fusion.py)
                    │
                    ▼
     [Verdict & Top 3 Concrete Explanations]
    { trust_score, verdict, unverifiable, reasons }
```

---

## 2. Directory Structure

```
IDP/
├── backend/
│   ├── main.py                 # FastAPI application & WebSocket scoring endpoint
│   └── requirements.txt        # Production dependencies (spaCy removed, chat-downloader added)
├── ml/
│   ├── campaign_detector.py    # Vectorized similarity graph, synchrony, topic drift
│   ├── learned_fusion.py       # Logistic regression fusion trained on Dev split
│   ├── text_intent.py          # Char n-gram TF-IDF + Logistic Regression baseline
│   ├── text_scorer.py          # Contextual text scoring facade with LRU cache
│   ├── intent_rules.py         # Lean regex-based solicitation and link matching (~50 lines)
│   ├── behavioral_profiler.py  # In-session per-user behavioral tracker
│   ├── session_state.py        # Per-connection session state & user profiles
│   ├── _text_intent_model.pkl  # Trained text model bundle
│   └── _fusion_model.pkl       # Trained fusion model bundle (FPR <= 1% operating point)
├── eval/
│   ├── run_eval.py             # Rigorous evaluation harness across baselines B1-B4
│   ├── FROZEN.md               # Cryptographic SHA-256 hashes of test & attack splits
│   ├── FAILURES.md             # Concrete failure analysis & documented edge cases (L3/L4)
│   └── results/                # Visual plots (robustness_curve.png, ablation_bars.png, etc.)
├── attacks/
│   ├── attack_generator.py     # Stealth ladder generator (L0-L4, L3-single) with disk cache
│   ├── inject.py               # Injects adversarial campaigns into authentic sessions
│   ├── prompts/                # Adversarial prompts isolated from detector code
│   └── cache/                  # Disk cache for 100% offline reproducibility
├── demo/
│   ├── replay_server.py        # Dedicated demo server with adjustable speeds (1x, 5x, 20x)
│   ├── index.html              # Interactive inspector dashboard (dark mode, glassmorphic)
│   ├── app.js                  # Client logic, live metrics strip, side-by-side toggle
│   ├── style.css               # Styling
│   └── DEMO.md                 # 5-minute presentation script & pre-flight checklist
├── extension/
│   ├── manifest.json           # Manifest V3 configuration
│   ├── content.js              # DOM MutationObserver, 3-state badge renderer, popover
│   ├── background.js           # Service worker managing WebSocket connection
│   ├── popup.html              # Minimal status popup (active toggle, scanned counters)
│   ├── popup.js                # Popup logic
│   └── popup.css               # Popup styling
├── scripts/
│   ├── collect_sessions.py     # Live chat collector via chat-downloader with salted hashing
│   ├── label_tool.py           # Cluster-assisted labeling tool with Cohen's kappa
│   ├── bootstrap_sessions.py   # Baseline dev/test session generator
│   ├── prepare_stealth_benchmark.py # Generates frozen injected test suites
│   ├── train_text_model.py     # Trains and benchmarks text intent model
│   └── train_fusion_model.py   # Trains learned fusion model on Dev split
└── tests/
    ├── test_features.py        # Unit tests for intent rules and skeleton extraction
    ├── test_pipeline.py        # Deterministic session scoring tests
    └── test_smoke.py           # End-to-end FastAPI WebSocket smoke tests
```

---

## 3. Data Flow & Feature Representation

Each incoming comment event undergoes the following pipeline in `ml/fusion.py`:

1. **Text Intent (`ml/text_scorer.py` + `ml/text_intent.py`):**
   - Computes char n-gram (2–5) TF-IDF features and outputs scam intent probability $P_{\text{scam}}$.
   - Evaluates high-precision regexes (`ml/intent_rules.py`) for external links, handles, crypto wallets, and DM solicitation.
2. **Campaign Clustering (`ml/campaign_detector.py`):**
   - Retrieves or computes a 384-dimensional dense embedding using `all-MiniLM-L6-v2`.
   - Performs a batched matrix dot product against the sliding time window ($N \le 350$, $t \le 60\text{s}$).
   - Computes:
     - `cluster_account_count`: Distinct accounts in the semantic cluster ($\cos \ge 0.80$).
     - `cluster_cohesion`: Mean cosine similarity of cluster members.
     - `rate_normalized_synchrony`: Cluster message rate normalized by overall background chat velocity.
     - `off_topic_distance`: Cosine distance between message embedding and the running organic stream centroid.
     - `skeleton_reuse_ratio`: Token Jaccard overlap of skeleton templates.
     - `is_organic_hype_pattern`: Discriminates short-text community hype bursts from malicious campaigns.
3. **Learned Fusion (`ml/learned_fusion.py`):**
   - Feeds the standardized 11-dimensional feature vector into a Logistic Regression model fitted strictly on Dev sessions.
   - Evaluates against the operating threshold $\tau_{\text{campaign}} = 0.9220$ (selected on Dev to guarantee FPR on genuine $\le 1.0\%$).
   - Returns continuous trust score, 3-state verdict (`clear`, `suspicious`, `likely_campaign`), and handles the `unverifiable` abstention flag.
   - Exports feature contributions directly as the source for top 3 human-readable explanations.
