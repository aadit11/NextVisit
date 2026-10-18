"""PR-AUC, Brier score, and top-decile capture for one city model and its baseline."""

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss

METRIC_NAMES = ("pr_auc", "brier", "top_decile_capture")


def baseline_probabilities(previous_positive: np.ndarray) -> np.ndarray:
    """The repeat-last-visit rule as a probability: 1 if the last visit was positive."""
    return np.asarray(previous_positive, dtype=float)


def top_decile_capture(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Share of all positive visits that fall in the highest 10 percent of scores."""
    labels = np.asarray(y_true)
    scores = np.asarray(y_prob)
    positives = float(labels.sum())
    if positives == 0 or len(labels) == 0:
        return 0.0
    keep = max(1, len(labels) // 10)
    order = np.argsort(-scores, kind="mergesort")
    return float(labels[order[:keep]].sum() / positives)


def score_probabilities(y_true: np.ndarray, y_prob: np.ndarray) -> dict[str, float]:
    return {
        "pr_auc": float(average_precision_score(y_true, y_prob)),
        "brier": float(brier_score_loss(y_true, y_prob)),
        "top_decile_capture": top_decile_capture(y_true, y_prob),
    }
