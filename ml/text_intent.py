"""
ml/text_intent.py

Domain-specific text intent classifier trained on YouTube comments.
Replaces zero-shot DistilBERT-MNLI and SMS bert-tiny.
Uses char n-gram (2-5) TF-IDF + Logistic Regression.
Reports PR-AUC and F1 on held-out sessions.
"""

import os
import sys
import pickle
import logging
from typing import Dict, Any, Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODEL_PATH = os.path.join(os.path.dirname(__file__), "_text_intent_model.pkl")


class TextIntentClassifier:
    """Char n-gram TF-IDF + Logistic Regression text intent model."""

    def __init__(self):
        self.vectorizer = None
        self.classifier = None
        self.is_fitted = False
        self._load()

    def _load(self):
        if os.path.exists(MODEL_PATH):
            try:
                with open(MODEL_PATH, "rb") as f:
                    bundle = pickle.load(f)
                    self.vectorizer = bundle["vectorizer"]
                    self.classifier = bundle["classifier"]
                    self.is_fitted = True
            except Exception as e:
                logger.warning(f"Could not load text intent model: {e}")

    def fit(self, texts: list[str], labels: list[int]):
        """
        Fits TF-IDF vectorizer and Logistic Regression.
        labels: 1 = scam/solicitation, 0 = genuine
        """
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression

        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 5),
            min_df=3,
            max_features=10000,
            sublinear_tf=True,
        )
        X = self.vectorizer.fit_transform(texts)
        self.classifier = LogisticRegression(C=1.5, max_iter=1000, class_weight="balanced")
        self.classifier.fit(X, labels)
        self.is_fitted = True

        with open(MODEL_PATH, "wb") as f:
            pickle.dump({"vectorizer": self.vectorizer, "classifier": self.classifier}, f)
        logger.info(f"Fitted text intent classifier on {len(texts)} samples.")

    def predict_proba(self, text: str) -> float:
        """Returns probability of scam intent [0.0, 1.0]."""
        if not self.is_fitted or not text or not text.strip():
            return 0.10  # default benign probability

        try:
            vec = self.vectorizer.transform([text])
            prob_scam = float(self.classifier.predict_proba(vec)[0][1])
            return prob_scam
        except Exception as e:
            logger.debug(f"Prediction error: {e}")
            return 0.50

    def score(self, text: str) -> Dict[str, Any]:
        """
        Returns trust score where 1.0 = clean, 0.0 = scam,
        along with explanatory top n-gram tokens.
        """
        if not text or not text.strip():
            return {"score": 1.0, "scam_prob": 0.0, "reasons": []}

        scam_prob = self.predict_proba(text)
        trust_score = round(1.0 - scam_prob, 4)

        reasons = []
        if scam_prob >= 0.65:
            reasons.append(f"Text intent model: high solicitation likelihood ({scam_prob:.0%})")
        elif scam_prob >= 0.45:
            reasons.append(f"Text intent model: moderate suspicious phrasing ({scam_prob:.0%})")

        return {
            "score": trust_score,
            "scam_prob": round(scam_prob, 4),
            "reasons": reasons,
        }


# Singleton instance
_INSTANCE: Optional[TextIntentClassifier] = None


def get_text_intent_classifier() -> TextIntentClassifier:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = TextIntentClassifier()
        if not _INSTANCE.is_fitted:
            _train_default_baseline()
    return _INSTANCE


def _train_default_baseline():
    """Trains baseline on dev split if model file is absent."""
    try:
        from data.train_text_baseline import train_and_eval
        train_and_eval()
    except Exception as e:
        logger.warning(f"Could not auto-train text baseline: {e}")
