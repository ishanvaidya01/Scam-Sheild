# Empirical Evaluation Results (Held-Out Test Set)

> **Evaluation Date:** 2026-10-13 21:15:43
> **Platform:** Windows 11 (Intel64 Family 6 Model 183 Stepping 1, GenuineIntel)
> **Protocol:** Session-level split (never random rows); FPR on genuine <= 1.0% chosen on Dev; Test split frozen in `eval/FROZEN.md`.

## 1. Baselines Comparison (TEST Sessions)

| Model / Baseline | Precision (95% CI) | Recall (95% CI) | F1 Score | PR-AUC | ROC-AUC | FPR (Genuine) | FPR (Organic Hype) |
|---|---|---|---|---|---|---|---|
| **B1: Near-Duplicate** | 0.3462 | 0.7200 | 0.4675 | 0.5349 | 0.8509 | 0.00% | 0.00% |
| **B2: Text-Only Intent** | 0.0222 | 0.8200 | 0.0432 | 0.0184 | 0.6655 | 48.16% | 0.00% |
| **B3: v2-Baseline (Legacy)** | 0.0119 | 0.7200 | 0.0233 | 0.3678 | 0.4605 | 79.90% | 0.00% |
| **B4: Scam Shield (35% Build)** | **0.0789** [0.051, 0.105] | **0.5400** [0.387, 0.674] | **0.1378** | **0.0855** | **0.8352** | **8.39%** | **0.00%** |

## 2. RQ1: Robustness Across Stealth Ladder

| Stealth Level | Description | B1 Recall | B2 Recall | B3 Recall | B4 Recall |
|---|---|---|---|---|---|
| **L0** | Copy-paste burst | 100.00% | 100.00% | 100.00% | **90.00%** |
| **L1** | Template substitution | 100.00% | 100.00% | 100.00% | **86.67%** |
| **L2** | LLM paraphrase | 50.00% | 62.50% | 50.00% | **12.50%** |
| **L3** | Contextual infiltration | 33.33% | 66.67% | 33.33% | **0.00%** |
| **L4** | Low-and-slow campaign | 40.00% | 60.00% | 40.00% | **30.00%** |
| **L3-single** | Single stealth message | 100.00% | 100.00% | 100.00% | **100.00%** |

## 3. RQ2: Organic vs Malicious Synchrony & Abstention

- **False Positive Rate on Organic Hype / Synchrony:** `0.00%` (B3 legacy fired at `0.00%` due to false 'never repeat' assumption).
- **System Abstention Rate:** `30.06%` (intentionally outputs `unverifiable` when structural context is absent).
- **Precision When Committing:** `7.89%`.

## 4. Latency Benchmarking (Single-Core CPU)

| Stream Velocity | p50 Latency | p95 Latency |
|---|---|---|
| 5 msg/sec | 0.18 ms | 0.27 ms |
| 20 msg/sec | 0.18 ms | 0.58 ms |
| 100 msg/sec | 0.19 ms | 0.42 ms |

## 5. Artifact Plots Generated

- `eval/results/robustness_curve.png`: Stealth ladder recall curve (B1 vs B2 vs B3 vs B4)
- `eval/results/ablation_bars.png`: Feature group ablation impact on PR-AUC
- `eval/results/latency_curve.png`: Per-message scoring latency scaling
