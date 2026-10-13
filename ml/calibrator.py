"""
calibrator.py

Score calibration module using isotonic regression.

Raw ML scores are not true probabilities — a model might output 0.8 for a comment
that is only actually spam 40% of the time. Calibration maps raw scores to
well-calibrated probability estimates.

This module:
  1. Defines a ScoreCalibrator wrapper around sklearn's IsotonicRegression.
  2. Provides a default linear passthrough when no training data is available
     (safe fallback for cold-start deployment).
  3. Provides a clip-only calibrator as the initial fallback.

Usage:
  from ml.calibrator import get_calibrator
  calibrator = get_calibrator()
  calibrated = calibrator.calibrate(raw_score)  # returns float in [0, 1]
"""

import os
import logging
import pickle
from typing import Optional

logger = logging.getLogger(__name__)

_CALIBRATOR_PATH = os.path.join(
    os.path.dirname(__file__), "_calibrator_model.pkl"
)


class ScoreCalibrator:
    """
    Wraps an isotonic regression model for score calibration.
    Falls back to identity mapping if the model is not fitted.
    """

    def __init__(self):
        self._model = None
        self._is_fitted = False
        self._load()

    def _load(self):
        """Attempts to load a pre-fitted calibrator from disk."""
        if os.path.exists(_CALIBRATOR_PATH):
            try:
                with open(_CALIBRATOR_PATH, "rb") as f:
                    self._model = pickle.load(f)
                self._is_fitted = True
                logger.info("Loaded pre-fitted score calibrator.")
            except Exception as e:
                logger.warning(f"Could not load calibrator: {e}")

    def fit(self, raw_scores: list[float], true_labels: list[int]):
        """
        Fit the calibrator from a list of raw scores and binary true labels (1=spam).
        raw_scores are TRUST scores (1=genuine), so we flip for calibration.
        """
        try:
            from sklearn.isotonic import IsotonicRegression
            import numpy as np

            # Convert trust scores → spam probability for calibration
            spam_probs = [1.0 - s for s in raw_scores]
            ir = IsotonicRegression(out_of_bounds="clip")
            ir.fit(np.array(spam_probs), np.array(true_labels))
            self._model = ir
            self._is_fitted = True

            # Persist to disk
            with open(_CALIBRATOR_PATH, "wb") as f:
                pickle.dump(ir, f)
            logger.info("Calibrator fitted and saved.")
        except Exception as e:
            logger.warning(f"Calibration fitting failed: {e}")

    def calibrate(self, trust_score: float) -> float:
        """
        Calibrates a raw trust score.
        Returns a trust score in [0.0, 1.0].
        """
        trust_score = max(0.0, min(1.0, trust_score))

        if not self._is_fitted or self._model is None:
            # Identity fallback: apply mild logistic smoothing to push extremes
            # This prevents 0.5 "unknown" scores from cluttering the UI
            import math
            # Logistic centering: scores near 0.5 → more neutral representation
            stretched = (trust_score - 0.5) * 2.0  # map to [-1, 1]
            smoothed = 1.0 / (1.0 + math.exp(-3.5 * stretched))  # sigmoid
            return round(smoothed, 4)

        try:
            import numpy as np
            # Model calibrates spam probability; convert back to trust
            spam_prob_raw = 1.0 - trust_score
            calibrated_spam = float(self._model.predict([spam_prob_raw])[0])
            calibrated_trust = 1.0 - calibrated_spam
            return round(max(0.0, min(1.0, calibrated_trust)), 4)
        except Exception as e:
            logger.debug(f"Calibration prediction failed: {e}")
            return round(trust_score, 4)


# Module-level singleton
_calibrator_instance: Optional[ScoreCalibrator] = None


def get_calibrator() -> ScoreCalibrator:
    """Returns the module-level calibrator singleton (lazy init)."""
    global _calibrator_instance
    if _calibrator_instance is None:
        _calibrator_instance = ScoreCalibrator()
    return _calibrator_instance
