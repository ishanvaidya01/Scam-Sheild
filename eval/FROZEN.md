# Frozen Test Split & Adversarial Benchmark Hashes

> Non-negotiable Rule 2: Dev/test splits are by SESSION (stream). The test split and the red-team attack set are frozen before any detector tuning; hashes are recorded below.

## 1. Frozen Raw & Labeled Session Datasets

| Session File | Split | SHA-256 Checksum |
|---|---|---|
| `organic_hype_dev.jsonl` | dev | `9702d5bfd31739ffec1fcf22110ba94bf0ea4dab2fa1861f07c73e9539e445bc` |
| `organic_hype_test.jsonl` | test | `0eeda8217bacbc04aa6a708f0e980db80dd2eec66805737276647b79d7bf0e60` |
| `uci_eminem.jsonl` | test | `b3f8e1b5752a536a1dc6afc29d93926f287ee44dcd2c46ca8ccf01e00f10f0a1` |
| `uci_katy_perry.jsonl` | dev | `0c304a5c92c24561ef9ff8d900bb491944985f938384dff1bc555bceb1e5dc25` |
| `uci_lmfao.jsonl` | dev | `0e429915562ca513432b40a92b9448b85066e0724447512c80ab1bf73642169c` |
| `uci_psy.jsonl` | dev | `7748ee67d4ac2fadb062e6ea1ff18022d48c40dda2857022a2cedecb2f66e814` |
| `uci_shakira.jsonl` | test | `05bfa5192c97e98eee6f72882c855b0ca42b948ef7f736d1391cdcbc01f5bdf9` |

## 2. Frozen Test Attack Injections (Stealth Ladder)

| Injected Dataset | Stealth Level | Attack Messages | Genuine Messages | SHA-256 Checksum |
|---|---|---|---|---|
| `session_eminem_test_L0.jsonl` | L0 | 10 | 448 | `4ee6f520d8f393c29d0f84d6fda8d25adf6ff73e66b0db300f2f54ff01b1d95e` |
| `session_eminem_test_L1.jsonl` | L1 | 15 | 448 | `83b0778670a2cb00216d03126c26602c746ea702f73d7cb8d4ef722c7b5763e4` |
| `session_eminem_test_L2.jsonl` | L2 | 8 | 448 | `14b41a806495773322a6c61f2fc5a48a44332724f9dc63d336adc29cb32795c9` |
| `session_eminem_test_L3.jsonl` | L3 | 6 | 448 | `8be2ff070855a4bb3d17efcedb710fc3449d9c95c323c9c32f4153309938d4fe` |
| `session_eminem_test_L4.jsonl` | L4 | 10 | 448 | `5dc09e6dfc01daf673a094eba76fb2409aaca56242b58589c565866304775d20` |
| `session_eminem_test_L3-single.jsonl` | L3-single | 1 | 448 | `56f9509a101106bcba56ee8a7cd6160c76df6221d4f08275c8ac2fb90fe28a2e` |

## 3. Dev Attack Injections (For Operating Point & Ablation Tuning)

| Injected Dataset | Stealth Level | Attack Messages | Genuine Messages | SHA-256 Checksum |
|---|---|---|---|---|
| `session_psy_dev_L0.jsonl` | L0 | 10 | 350 | `93529b26b809ca37a85b99c684719b6efbd8d95c15b13c8f3fd2b715ae1272a3` |
| `session_psy_dev_L1.jsonl` | L1 | 15 | 350 | `4847419b688a86f9ce5edd27e0e3d27596671d216c5edd53f89030b4064c98f7` |
| `session_psy_dev_L2.jsonl` | L2 | 8 | 350 | `42f12896eb03d1e1afc1f07e7400e526e660bd0312e9eb98feff0e3b30fca0e8` |
| `session_psy_dev_L3.jsonl` | L3 | 6 | 350 | `deac83bb174bef79fa86595a40c6c74eaa5b60588d0b185679a6a48d947c9dc0` |
| `session_psy_dev_L4.jsonl` | L4 | 10 | 350 | `2e65925809e17174167a7101bb8e1d81d035f9af73310be7ed7b6669a73ab7ab` |
| `session_psy_dev_L3-single.jsonl` | L3-single | 1 | 350 | `5b51aaa8ff2364ab0373f54e66ed612f369ca200415fa6edcb31d10c135a5b1e` |
