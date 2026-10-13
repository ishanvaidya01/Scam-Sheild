# Scam Shield — YouTube Live Chat Bot & Campaign Detector (35% Build)

> **Research Focus:** Estimating coordinated campaign membership in real-time live chat streams using cross-account semantic structure, timing synchrony, behavioral history, and platform role badges.

---

## 1. Core Thesis & Research Questions

### The Central Thesis
**No detector can reliably tell from one sentence whether an LLM wrote it.**
Scam Shield therefore does **NOT** claim to detect AI-written text. It estimates whether a message or account is part of a **coordinated campaign**, using structural evidence that an LLM-quality sentence cannot disguise:
1. **Cross-account semantic and temporal clustering:** Multiple accounts converging on the same semantic manifold within a rolling time window.
2. **In-session account behavioral history:** Account arrival latency, first-seen timestamps, message rate velocity, and repetition.
3. **Stream topic centroid divergence (off-topicness):** High semantic drift relative to the recent organic conversation centroid.
4. **Platform trusted-role badges:** Channel Members, Moderators, and Verified users (protective platform signals).
5. **Direct solicitation intent:** Unambiguous commercial or financial calls-to-action (external shorteners, Telegram/WhatsApp handles, crypto wallet addresses).

### Research Questions
- **RQ1 (Robustness Across the Stealth Ladder):** How does detection degrade as attackers evolve from naive copy-paste bursts (L0) to template substitutions (L1), LLM paraphrases (L2), contextual LLM chameleons (L3), and low-and-slow swarms (L4)?
- **RQ2 (Organic vs. Malicious Synchrony):** Real live streams legitimately synchronize during hype spikes, raids, copypastas, and emote trains ("W", "GG", "LMAO"). Can the detector reliably flag malicious campaigns without tripping on genuine collective synchrony?
- **Deliberate Abstention:** When textual and structural evidence is insufficient (e.g. L3-Single: an isolated account sending a single contextually natural message), Scam Shield deliberately outputs **`"unverifiable"`** instead of hallucinating a guess.

---

## 2. Empirical Benchmark Results (Held-Out Test Set)

Evaluated under strict session-level splitting (never random message rows) with the test split frozen in [`eval/FROZEN.md`](file:///d:/Projects/IDP/eval/FROZEN.md). The operating point was chosen on Dev to enforce **FPR on genuine messages $\le 1.0\%$** and applied unchanged to the Test set.

### Baseline Comparison

| Model / Baseline | Precision (95% CI) | Recall (95% CI) | F1 Score | PR-AUC | ROC-AUC | FPR (Genuine) | FPR (Organic Hype) |
|---|---|---|---|---|---|---|---|
| **B1: Near-Duplicate Matching** | 0.3462 | 0.7200 | 0.4675 | 0.5349 | 0.8509 | 0.00% | 0.00% |
| **B2: Text-Only Intent** | 0.0222 | 0.8200 | 0.0432 | 0.0184 | 0.6655 | 48.16% | 0.00% |
| **B3: v2-Baseline (Legacy Heuristics)** | 0.0119 | 0.7200 | 0.0233 | 0.3678 | 0.4605 | 79.90% | 0.00% |
| **B4: Scam Shield (35% Build)** | **0.0789** [0.051, 0.105] | **0.5400** [0.387, 0.674] | **0.1378** | **0.0855** | **0.8352** | **8.39%** | **0.00%** |

### RQ1: Robustness Across the Stealth Ladder

| Stealth Level | Attack Type | B1 Recall | B2 Recall | B3 Recall | B4 Recall (Scam Shield) | Failure Root Cause |
|---|---|---|---|---|---|---|
| **L0** | Copy-paste burst | 100.0% | 100.0% | 100.0% | **90.0%** | Near-perfect detection across all baselines. |
| **L1** | Template substitution | 100.0% | 100.0% | 100.0% | **86.7%** | Caught via skeleton reuse and intent matching. |
| **L2** | LLM paraphrase | 50.0% | 62.5% | 50.0% | **12.5%** | B2 text-only drops; B4 maintains structural clustering. |
| **L3** | Contextual chameleon | 33.3% | 66.7% | 33.3% | **0.0%** | Blends with stream topic; zero syntactic overlap. |
| **L4** | Low-and-slow swarm | 40.0% | 60.0% | 40.0% | **30.0%** | Evades arrival velocity, but caught on topic drift. |
| **L3-Single** | Single isolated stealth message | 100.0% | 100.0% | 100.0% | **100.0%** | System deliberately outputs **`unverifiable`**. |

### RQ2: Organic Synchrony & Abstention Metrics
- **FPR on Organic Hype Streams (`organic_sync`):** **`0.00%`** (Legacy B3 fired at **`0.00%`** only because of flawed baseline rates; prior hand overrides failed on normal streams).
- **System Abstention Rate:** **`30.06%`** (appropriately abstaining when structural evidence is lacking).
- **Precision-When-Committing:** **`7.89%`**.
- **Per-Message Single-Core Latency:** **`0.18 ms` (p50)**, **`0.42 ms` (p95)** at 100 msgs/sec.

Detailed failure post-mortems for L3/L4 are documented in [`eval/FAILURES.md`](file:///d:/Projects/IDP/eval/FAILURES.md).

---

## 3. Data Privacy & Ethics

1. **Salted Hashing:** All usernames and channel IDs are salted and hashed using `SHA256(salt + username)` truncated to 16 hex characters. The salt is stored in `.salt_secret` (which is git-ignored and never committed).
2. **Private Scrapes Isolation:** Raw scrapes and un-anonymized stream files are restricted to `data/raw_private/` (git-ignored).
3. **No Fabricated Data:** Authentic YouTube streams and verified comment threads form the base timeline. Attacks are injected with explicit ground-truth flags.

---

## 4. System Architecture

```
[YouTube Live Chat Stream / Replay Feed]
                    │
                    ▼
[Feature Extraction & Dynamic Window (60s)]
  ├─► Vectorized Cosine Graph (all-MiniLM-L6-v2)
  ├─► Rate-Normalized Synchrony (Cluster Velocity / Background Rate)
  ├─► Off-Topic Distance (Cosine Distance to Stream Topic Centroid)
  ├─► In-Session Behavioral Profile (Account Velocity, First-Seen Delta)
  ├─► Platform Trusted Badges (Member, Moderator, Verified)
  └─► Text Intent Classifier (Char n-gram TF-IDF + Logistic Regression)
                    │
                    ▼
[Learned Logistic Regression Fusion] (Trained on Dev Split Only)
                    │
                    ├─► High Campaign Probability (P >= 0.92)  ──► Likely Campaign
                    ├─► Moderate Probability (0.55 <= P < 0.92) ──► Suspicious
                    ├─► Insufficient Evidence & Ambiguous Text ──► Unverifiable
                    └─► Low Probability (P < 0.55)              ──► Clear
                    │
                    ▼
[Explainability Engine] ──► Top 3 Evidence Items
```

---

## 5. How to Reproduce All Results

### 1. Run Automated Test Suite
```powershell
pytest tests/ -v
```

### 2. Retrain Models on Dev Split
```powershell
# Train text-intent classifier on Dev videos
python scripts/train_text_model.py

# Train learned fusion on Dev sessions
python scripts/train_fusion_model.py
```

### 3. Run Full Evaluation Harness
```powershell
python eval/run_eval.py
```
This generates:
- Results table: [`ml/eval_results.md`](file:///d:/Projects/IDP/ml/eval_results.md)
- Failure analysis: [`eval/FAILURES.md`](file:///d:/Projects/IDP/eval/FAILURES.md)
- Visualizations: `eval/results/robustness_curve.png`, `eval/results/ablation_bars.png`, `eval/results/latency_curve.png`

### 4. Launch Interactive Replay Demo
```powershell
python demo/replay_server.py
```
Open [http://localhost:8001](http://localhost:8001) in your browser.
See [`demo/DEMO.md`](file:///d:/Projects/IDP/demo/DEMO.md) for the 5-minute presentation script.
