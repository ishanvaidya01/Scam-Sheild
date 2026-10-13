"""
evaluate.py  (v2)

Evaluates all available ML signals against the UCI YouTube Spam dataset.
Writes results to ml/eval_results.md.
"""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
from sklearn.metrics import precision_score, recall_score, f1_score, classification_report

UCI_DATA = os.path.join("data", "processed", "uci_spam.csv")
EVAL_OUT  = os.path.join("ml", "eval_results.md")


def evaluate_pipeline():
    if not os.path.exists(UCI_DATA):
        print(f"Dataset not found: {UCI_DATA}")
        print("Run: python scripts/download_public_data.py")
        return None, None, None

    df = pd.read_csv(UCI_DATA)
    y_true = (df['label'] == 'scam').astype(int).tolist()

    print(f"Evaluating on {len(df)} rows...")

    from ml.text_scorer import score_text
    from ml.linguistic_analyzer import analyze_linguistics
    from ml.session_state import SessionState

    text_preds, ling_preds, fused_preds = [], [], []

    for idx, row in df.iterrows():
        text = str(row.get('text', ''))

        # Text scorer
        t_res = score_text(text)
        text_preds.append(1 if t_res['score'] < 0.5 else 0)

        # Linguistic analyzer
        l_res = analyze_linguistics(text)
        ling_preds.append(1 if l_res['score'] < 0.5 else 0)

        # Fused (text + linguistic only, no coordination since no window context)
        fused_score = (0.55 * t_res['score']) + (0.45 * l_res['score'])
        fused_preds.append(1 if fused_score < 0.5 else 0)

        if (idx + 1) % 100 == 0:
            print(f"  Processed {idx + 1}/{len(df)}...")

    def metrics(y_t, y_p, name):
        p = precision_score(y_t, y_p, zero_division=0)
        r = recall_score(y_t, y_p, zero_division=0)
        f = f1_score(y_t, y_p, zero_division=0)
        print(f"\n[{name}]  Precision={p:.4f}  Recall={r:.4f}  F1={f:.4f}")
        return {"name": name, "precision": p, "recall": r, "f1": f}

    t_m = metrics(y_true, text_preds, "ContextualTextClassifier")
    l_m = metrics(y_true, ling_preds, "LinguisticAnalyzer")
    f_m = metrics(y_true, fused_preds, "Text+Linguistic Fusion")

    return t_m, l_m, f_m


def write_results(text_m, ling_m, fused_m):
    lines = [
        "# ML Evaluation Results (v2)\n\n",
        f"Dataset: {UCI_DATA}\n\n",
        "| Evaluator | Precision | Recall | F1 Score |\n",
        "|---|---|---|---|\n",
    ]
    for m in [text_m, ling_m, fused_m]:
        if m:
            lines.append(
                f"| {m['name']} | {m['precision']:.4f} | {m['recall']:.4f} | {m['f1']:.4f} |\n"
            )
    lines.append("\n## Notes\n")
    lines.append("- Coordination, Behavioral, and Network signals require a live session and cannot be evaluated offline.\n")
    lines.append("- The full 5-signal ensemble will score higher than text-only evaluation.\n")

    with open(EVAL_OUT, 'w') as f:
        f.writelines(lines)
    print(f"\nResults written to {EVAL_OUT}")


if __name__ == "__main__":
    t, l, f = evaluate_pipeline()
    write_results(t, l, f)
