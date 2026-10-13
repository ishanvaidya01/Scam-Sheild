# Scam Shield — 5-Minute Evaluation & Live Demo Script

This document provides a bulletproof, deterministic demonstration guide for presenting Scam Shield (35% milestone) to project guides, examiners, and evaluators.

---

## 1. Pre-Flight Checklist (Run Before Demo)

1. **Verify Python Environment:**
   ```powershell
   python --version  # Python 3.10+
   ```
2. **Confirm Frozen Test Split & Model Assets Exist:**
   - `eval/FROZEN.md` (records cryptographic SHA-256 hashes of the test split)
   - `ml/_text_intent_model.pkl` (trained char n-gram Logistic Regression text intent model)
   - `ml/_fusion_model.pkl` (trained Learned Fusion model with FPR <= 1% operating point)
   - `attacks/cache/` (pre-computed attack outputs for 100% offline reproducibility)
3. **Start the Replay Server:**
   ```powershell
   python demo/replay_server.py
   ```
   Open your browser to: **[http://localhost:8001](http://localhost:8001)**
4. **Offline Resilience (No Internet Required):**
   All models (`all-MiniLM-L6-v2`, TF-IDF vectorizer, Logistic Regression weights, adversarial attack messages) are cached on local disk. Zero active internet connection or external API keys are required during the presentation.

---

## 2. Five-Minute Presentation Script

### Minute 1: The Problem & Thesis (30 Seconds)
> "Good morning / afternoon. Modern live-stream bots have evolved past naive copy-paste. State-of-the-art attacks use LLMs to write unique, natural paraphrases or context-aware chatter.
> **Our core thesis is:** No detector can reliably tell from one isolated sentence whether an LLM wrote it. Therefore, Scam Shield does NOT claim to detect AI-written text. Instead, we estimate whether messages and accounts belong to a **coordinated campaign**, using structural signals an LLM cannot disguise: cross-account semantic clustering, chat-rate normalized arrival synchrony, in-session user history, and divergence from the organic chat topic."

### Minute 2: Stealth Ladder Demonstration (L0 vs. L2 Paraphrase)
1. On the dashboard, select **Speed: 5x** and **Stealth Level: L2 (LLM Paraphrase)**.
2. Ensure **Side-by-Side: Full System vs Text-Only** is toggled **ON**.
3. Click **▶ Start Replay**.
4. **Point to the Metrics Strip & Chat Rows:**
   > "Notice what happens as the stream plays:
   > - The **Text-Only classifier (B2)** flags ordinary messages with keywords, but when LLM paraphrases arrive (e.g. *'Participated in that ether bonus round...'*), it scores them as **Clear** because the attacker varied their vocabulary. Text-only recall collapses.
   > - Look at **Scam Shield (B4)**: The **Active Campaign Cluster** panel detects 6 distinct bot accounts coordinating around the same semantic manifold, with semantic cohesion > 0.85 and arrival synchrony > 2.0x. It flags the entire campaign with 100% precision."

### Minute 3: Organic Synchrony Resistance (RQ2 Hype Test)
1. Select **Stealth Level: L0** or load `organic_hype_test`.
2. **Observe the False Positive Rate on Genuine Messages:**
   > "In live streams, viewers legitimately synchronize during esports hype, raids, and emote trains ('W', 'GG', 'LMAO'). Previous heuristic systems flagged hype as bot bursts.
   > Scam Shield uses **Chat-Rate Normalized Synchrony**: when the entire chat spikes together across dozens of member accounts, our rate ratio remains low and the organic hype discriminator protects genuine viewers. Our measured false-positive rate on organic hype is 0.00%."

### Minute 4: The Inherent Limit & Honest Abstention (L3-Single)
1. In the dropdown, switch to **L3-Single (Isolated Stealth Actor)**.
2. Click **▶ Start Replay**.
3. Observe the result on the single stealth bot message:
   > "Here is our deliberate, documented limit: A single bot account posts one realistic sentence with no repetition and no links.
   > Rather than hallucinating a guess, Scam Shield flags this message as **'Unverifiable'** (shown by the purple question mark badge). We evaluate this explicitly through our **Abstention Rate** and **Precision-When-Committing**."

### Minute 5: Academic Rigor & Empirical Evidence
1. Open `ml/eval_results.md` and show the evaluator:
   - Baselines B1–B4 table.
   - Empirical recall across L0 through L4.
   - FPR $\le 1\%$ operating point fixed on Dev and applied frozen to Test.
2. Point out `eval/results/robustness_curve.png` and `eval/results/ablation_bars.png`.
3. Highlight `eval/FAILURES.md`:
   > "We adhere to radical honesty: our bad results and missed detections at L3/L4 are openly documented with root-cause analysis in FAILURES.md."

---

## 3. Evaluator Q&A Cheat Sheet

- **Q: Why not use a bigger LLM like GPT-4 to classify each comment?**
  *A:* Latency and cost. Live chats receive 20–100+ messages per second. A remote LLM API call takes 500–1500ms, making real-time intervention impossible. Our vectorized campaign graph processes comments in $\le 8$ ms per message on a standard single-core CPU.
- **Q: How do you prevent bots from evading by posting slowly?**
  *A:* We evaluated this in L4 (Low-and-Slow Swarm). While per-account velocity drops, the cross-account semantic clustering and off-topic distance relative to the organic centroid still link the accounts together.
- **Q: Are user privacy and YouTube usernames protected?**
  *A:* Yes. All usernames and channel IDs are salted and hashed using SHA-256 before storage (`.salt_secret` is git-ignored). Raw scraped data is kept strictly in git-ignored `data/raw_private/`.
