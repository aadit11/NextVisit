import numpy as np

from nextvisit.model.evaluate import top_decile_capture


def test_top_decile_keeps_the_highest_scores() -> None:
    labels = np.array([1, 0, 1, 0, 0, 0, 0, 0, 0, 0])
    scores = np.array([0.1, 0.9, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    assert top_decile_capture(labels, scores) == 0.0

    scores = np.array([0.9, 0.8, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    assert top_decile_capture(labels, scores) == 0.5
