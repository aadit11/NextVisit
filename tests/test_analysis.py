"""Feature groups, weak-result rules, and the clean-previous slice."""

import json
from pathlib import Path

import numpy as np
import polars as pl

from nextvisit.model.analysis import (
    groups_for,
    other_group_callout,
    previous_clean_slice,
    weak_paragraphs,
    without_group,
)
from nextvisit.model.train import (
    CHICAGO_CATEGORICAL,
    CHICAGO_NUMERIC,
    FeaturePreprocessor,
    KING_COUNTY_CATEGORICAL,
    KING_COUNTY_NUMERIC,
)
from nextvisit.report import collect_rows, render_analysis


def test_grade_stays_in_severity() -> None:
    groups = {group.id: group.columns for group in groups_for(KING_COUNTY_CATEGORICAL, KING_COUNTY_NUMERIC)}
    assert "previous_grade" in groups["severity"]
    assert "previous_score" in groups["severity"]
    assert "previous_grade" not in groups["place"]
    assert groups["place"] == ("risk", "zip")


def test_chicago_has_no_severity_group() -> None:
    ids = [group.id for group in groups_for(CHICAGO_CATEGORICAL, CHICAGO_NUMERIC)]
    assert "severity" not in ids
    place = next(group for group in groups_for(CHICAGO_CATEGORICAL, CHICAGO_NUMERIC) if group.id == "place")
    assert place.columns == ("facility_type", "risk", "zip")


def test_without_group_drops_only_that_group() -> None:
    group = next(group for group in groups_for(("cuisine",), ("previous_positive", "days_since_previous")) if group.id == "last_outcome")
    categorical, numeric = without_group(("cuisine",), ("previous_positive", "days_since_previous"), group)
    assert categorical == ("cuisine",)
    assert numeric == ("days_since_previous",)


def test_preprocessor_fits_when_a_group_drop_leaves_no_categories() -> None:
    frame = pl.DataFrame(
        {
            "previous_positive": [1.0, 0.0, 1.0],
            "days_since_previous": [10.0, 20.0, 30.0],
        }
    )
    preprocessor = FeaturePreprocessor()
    preprocessor.categorical = ()
    preprocessor.numeric = ("previous_positive", "days_since_previous")
    transformed = preprocessor.fit(frame).transform(frame)
    assert transformed.shape == (3, 2)


def test_previous_clean_slice_ignores_rows_that_were_already_serious() -> None:
    labels = np.array([1, 0, 1, 0])
    probabilities = np.array([0.2, 0.9, 0.1, 0.8])
    previous = np.array([True, False, True, False])
    payload = previous_clean_slice(labels, probabilities, previous)
    assert payload["rows"] == 2
    assert payload["serious_visits"] == 0
    assert payload["eligible"] is False


def test_slice_eligibility_needs_two_hundred_rows_and_thirty_serious_visits() -> None:
    short = previous_clean_slice(
        np.array([1] * 30 + [0] * 169),
        np.linspace(0.1, 0.9, 199),
        np.zeros(199, dtype=bool),
    )
    assert short["eligible"] is False
    enough = previous_clean_slice(
        np.array([1] * 30 + [0] * 170),
        np.linspace(0.1, 0.9, 200),
        np.zeros(200, dtype=bool),
    )
    assert enough["rows"] == 200
    assert enough["serious_visits"] == 30
    assert enough["eligible"] is True
    assert enough["pr_auc_gap"] == enough["lightgbm"]["pr_auc"] - enough["positive_rate"]


def test_weak_paragraphs_follow_the_three_rules() -> None:
    sticky = _models(top_gap=0.008, lightgbm_brier=0.08, baseline_brier=0.18, logistic_brier=0.09, pr_auc=0.95)
    notes = weak_paragraphs("New York", sticky, positive_rate=0.89)
    assert len(notes) == 1
    assert "Brier score" in notes[0]
    assert "0.080" in notes[0]

    tied = _models(top_gap=0.04, lightgbm_brier=0.211, baseline_brier=0.35, logistic_brier=0.210, pr_auc=0.52)
    notes = weak_paragraphs("Los Angeles County", tied, positive_rate=0.34)
    assert len(notes) == 1
    assert "does not improve calibration" in notes[0]

    rare = _models(top_gap=0.12, lightgbm_brier=0.03, baseline_brier=0.06, logistic_brier=0.04, pr_auc=0.07)
    notes = weak_paragraphs("San Francisco", rare, positive_rate=0.036)
    assert len(notes) == 1
    assert "test positive rate is 0.036" in notes[0]
    assert weak_paragraphs("San Francisco", rare, positive_rate=None) == []


def test_callout_names_a_group_other_than_the_last_visit() -> None:
    groups = [
        {"id": "last_outcome", "label": "Last outcome", "pr_auc_change": -0.05},
        {"id": "recency", "label": "Recency", "pr_auc_change": -0.012},
        {"id": "place", "label": "Place", "pr_auc_change": -0.001},
    ]
    text = other_group_callout("boston", "Boston", groups)
    assert text is not None
    assert "Recency" in text
    assert "Last outcome" not in text
    assert "Place" not in text
    quiet = other_group_callout("king_county", "King County", groups[:1] + [groups[2]])
    assert quiet is not None
    assert "no group other than the last outcome" in quiet
    assert other_group_callout("chicago", "Chicago", groups) is None


def test_analysis_section_names_the_largest_slice_gap(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    _city(artifacts, "new_york")
    _city(artifacts, "boston")
    _ablation(artifacts, "boston", change=-0.02)
    _slice(artifacts, "new_york", gap=0.01)
    _slice(artifacts, "boston", gap=0.2)
    text = render_analysis(collect_rows(artifacts, tmp_path / "missing"), artifacts, tmp_path / "missing")
    assert "The largest gap between LightGBM PR-AUC and the serious-visit rate is Boston" in text
    assert "Repeat last visit scores every one of those rows 0" in text
    assert "History counts (-0.020)" in text


def _models(
    top_gap: float,
    lightgbm_brier: float,
    baseline_brier: float,
    logistic_brier: float,
    pr_auc: float,
) -> dict[str, dict[str, float]]:
    return {
        "repeat_last_visit": {"pr_auc": 0.4, "brier": baseline_brier, "top_decile_capture": 0.1},
        "logistic_regression": {"pr_auc": 0.5, "brier": logistic_brier, "top_decile_capture": 0.1},
        "lightgbm": {"pr_auc": pr_auc, "brier": lightgbm_brier, "top_decile_capture": 0.1 + top_gap},
    }


def _city(artifacts: Path, city_id: str) -> None:
    city_dir = artifacts / city_id
    city_dir.mkdir(parents=True, exist_ok=True)
    (city_dir / "metrics.json").write_text(
        json.dumps(
            {
                "city": city_id,
                "test_rows": 10,
                "models": _models(0.2, 0.1, 0.2, 0.12, 0.6),
                "lightgbm_beats_baseline_pr_auc": True,
            }
        ),
        encoding="utf-8",
    )
    (city_dir / "cutoff.json").write_text(json.dumps({"cutoff": "2026-01-01"}), encoding="utf-8")


def _ablation(artifacts: Path, city_id: str, change: float) -> None:
    (artifacts / city_id / "ablation.json").write_text(
        json.dumps(
            {
                "city": city_id,
                "full": {"pr_auc": 0.7, "brier": 0.2, "top_decile_capture": 0.2},
                "groups": [
                    {
                        "id": "counts",
                        "label": "History counts",
                        "columns": ["prior_inspection_count"],
                        "metrics": {"pr_auc": 0.7 + change, "brier": 0.2, "top_decile_capture": 0.2},
                        "pr_auc_change": change,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _slice(artifacts: Path, city_id: str, gap: float) -> None:
    rate = 0.2
    (artifacts / city_id / "slices.json").write_text(
        json.dumps(
            {
                "city": city_id,
                "slice": "previous_clean",
                "available": True,
                "rows": 400,
                "serious_visits": 80,
                "positive_rate": rate,
                "lightgbm": {"pr_auc": rate + gap, "brier": 0.2, "top_decile_capture": 0.3},
                "eligible": True,
                "pr_auc_gap": gap,
            }
        ),
        encoding="utf-8",
    )
