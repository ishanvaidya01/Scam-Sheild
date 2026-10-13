# Failure Analysis & Documented Limits (eval/FAILURES.md)

> Non-negotiable Rule 3: Report honest numbers, including bad ones. Never fabricate results. Concrete missed detections and documented edge cases are recorded below.

## 1. Documented Inherent Limit: L3-Single Actor
**Finding:** When an attacker deploys an isolated bot account that posts **exactly one message** with zero template repetition, natural conversational phrasing, and no overt links/wallets, detection is fundamentally impossible without massive false positives on innocent viewers.

**Design Decision:** Scam Shield outputs `unverifiable` rather than guessing.

## 2. Missed Detections at High Stealth Levels (L3 & L4)

| Level | Message Text Snippet | Assigned Verdict | Trust Score | Unverifiable Flag | Why It Was Missed |
|---|---|---|---|---|---|
| `L3` | "bro this match is wild haha, btw anyone seen that giveaway link i..." | `clear` | `0.77` | `False` | Contextually blended with stream topic; arrival interval indistinguishable from organic chat. |
| `L3` | "ngl streamer is cracked today lol... also did the payout go throu..." | `suspicious` | `0.22` | `False` | Contextually blended with stream topic; arrival interval indistinguishable from organic chat. |
| `L3` | "wait what song is this?? sounds crazy. also got my 0.2 eth from t..." | `clear` | `0.88` | `False` | Contextually blended with stream topic; arrival interval indistinguishable from organic chat. |
| `L3` | "lmao he really missed that shot 💀 check @AlexSupport if you had q..." | `unverifiable` | `0.59` | `True` | Contextually blended with stream topic; arrival interval indistinguishable from organic chat. |
| `L3` | "W stream as always! btw guys the bonus round on telegram actually..." | `suspicious` | `0.28` | `False` | Contextually blended with stream topic; arrival interval indistinguishable from organic chat. |
| `L3` | "can we clip that play?? crazy clutch. also verify with @CryptoSup..." | `unverifiable` | `0.64` | `True` | Contextually blended with stream topic; arrival interval indistinguishable from organic chat. |
| `L4` | "Really enjoying this walkthrough. Quick question: is anyone in he..." | `suspicious` | `0.14` | `False` | Contextually blended with stream topic; arrival interval indistinguishable from organic chat. |
| `L4` | "Nice commentary today! By the way, thanks to whoever recommended ..." | `unverifiable` | `0.56` | `True` | Contextually blended with stream topic; arrival interval indistinguishable from organic chat. |
| `L4` | "First time catching the live stream! Loving the vibes. Also found..." | `clear` | `0.78` | `False` | Contextually blended with stream topic; arrival interval indistinguishable from organic chat. |
| `L4` | "Such a chill stream tonight. Just wanted to ask if the community ..." | `suspicious` | `0.31` | `False` | Contextually blended with stream topic; arrival interval indistinguishable from organic chat. |

## 3. Remediation & Future Work (Toward 50% Milestone)
- Incorporate cross-stream author identity persistence (detecting when an account has only ever commented on suspicious broadcasts).
- Long-horizon cross-session clustering (linking low-and-slow accounts across multiple days).
