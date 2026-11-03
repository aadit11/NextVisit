"""Weak-result rules, feature groups, and the clean-previous slice.

The diner page does not read this module. scripts/analyze.py writes the numbers,
and the README is rendered from those files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import polars as pl

from nextvisit.model.evaluate import score_probabilities, top_decile_capture

TOP_DECILE_TIE = 0.02
RARE_POSITIVE_RATE = 0.10
RARE_PR_AUC = 0.10
SLICE_MIN_ROWS = 200
SLICE_MIN_SERIOUS = 30
CALLOUT_PR_AUC = 0.01
CALLOUT_CITIES = ("boston", "king_county")


@dataclass(frozen=True)
class FeatureGroup:
    id: str
    label: str
    columns: tuple[str, ...]


ALL_GROUPS = (
    FeatureGroup("last_outcome", "Last outcome", ("previous_positive",)),
    FeatureGroup("recency", "Recency", ("days_since_previous", "days_since_last_positive")),
    FeatureGroup(
        "counts",
        "History counts",
        (
            "prior_inspection_count",
            "prior_positive_count",
            "prior_violation_count",
            "previous_violation_count",
        ),
    ),
    FeatureGroup("severity", "Severity", ("previous_score", "previous_grade")),
    FeatureGroup(
        "place",
        "Place",
        (
            "cuisine",
            "borough",
            "facility_type",
            "risk",
            "zip",
            "pe_description",
            "license_description",
            "permit_type",
            "neighborhood",
        ),
    ),
)


def groups_for(categorical: tuple[str, ...], numeric: tuple[str, ...]) -> list[FeatureGroup]:
    """Groups that city actually trains on, with grade and score kept in severity."""
    used = set(categorical) | set(numeric)
    groups: list[FeatureGroup] = []
    for group in ALL_GROUPS:
        columns = tuple(column for column in group.columns if column in used)
        if columns:
            groups.append(FeatureGroup(group.id, group.label, columns))
    return groups


def without_group(
    categorical: tuple[str, ...],
    numeric: tuple[str, ...],
    group: FeatureGroup,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    dropped = set(group.columns)
    return (
        tuple(column for column in categorical if column not in dropped),
        tuple(column for column in numeric if column not in dropped),
    )


def test_positive_rate(examples_path: Path) -> float | None:
    if not examples_path.exists():
        return None
    frame = (
        pl.scan_parquet(examples_path)
        .filter(pl.col("split") == "test")
        .select(pl.col("label").mean().alias("rate"))
        .collect()
    )
    rate = frame["rate"][0]
    if rate is None:
        return None
    return float(rate)


def weak_paragraphs(
    city_name: str,
    models: dict[str, dict[str, float]],
    positive_rate: float | None,
) -> list[str]:
    """Sentences for a sticky label, a tree that does not calibrate better, or a rare event."""
    lightgbm = models.get("lightgbm")
    baseline = models.get("repeat_last_visit")
    if lightgbm is None or baseline is None:
        return []
    notes: list[str] = []
    top_gap = abs(lightgbm["top_decile_capture"] - baseline["top_decile_capture"])
    if top_gap <= TOP_DECILE_TIE and lightgbm["brier"] < baseline["brier"]:
        notes.append(
            f"{city_name}: LightGBM top-decile capture is {_fmt(lightgbm['top_decile_capture'])} "
            f"against {_fmt(baseline['top_decile_capture'])} for repeat last visit. "
            f"The label sticks, so the gain is the Brier score, {_fmt(lightgbm['brier'])} "
            f"against {_fmt(baseline['brier'])}."
        )
    logistic = models.get("logistic_regression")
    if logistic is not None and lightgbm["brier"] >= logistic["brier"]:
        notes.append(
            f"{city_name}: logistic regression Brier is {_fmt(logistic['brier'])} and "
            f"LightGBM Brier is {_fmt(lightgbm['brier'])}. "
            "The tree does not improve calibration over logistic regression."
        )
    if (
        positive_rate is not None
        and positive_rate < RARE_POSITIVE_RATE
        and lightgbm["pr_auc"] < RARE_PR_AUC
    ):
        notes.append(
            f"{city_name}: PR-AUC is {_fmt(lightgbm['pr_auc'])}. "
            f"The test positive rate is {_fmt(positive_rate)}. "
            f"Top-decile capture is {_fmt(lightgbm['top_decile_capture'])} against "
            f"{_fmt(baseline['top_decile_capture'])} for repeat last visit."
        )
    return notes


def previous_clean_slice(
    labels: np.ndarray,
    probabilities: np.ndarray,
    previous_positive: np.ndarray,
) -> dict[str, object]:
    """Score rows whose previous inspection was clean. The baseline is a constant 0 there."""
    mask = ~np.asarray(previous_positive, dtype=bool)
    y = np.asarray(labels)[mask].astype(int)
    probabilities = np.asarray(probabilities, dtype=float)[mask]
    rows = int(y.size)
    serious = int(y.sum()) if rows else 0
    rate = float(y.mean()) if rows else 0.0
    if rows == 0:
        metrics = {"pr_auc": 0.0, "brier": 0.0, "top_decile_capture": 0.0}
    elif serious == 0 or serious == rows:
        metrics = {
            "pr_auc": rate,
            "brier": float(np.mean((probabilities - y) ** 2)),
            "top_decile_capture": top_decile_capture(y, probabilities),
        }
    else:
        metrics = score_probabilities(y, probabilities)
    return {
        "slice": "previous_clean",
        "rows": rows,
        "serious_visits": serious,
        "positive_rate": rate,
        "lightgbm": metrics,
        "eligible": rows >= SLICE_MIN_ROWS and serious >= SLICE_MIN_SERIOUS,
        "pr_auc_gap": float(metrics["pr_auc"]) - rate,
    }


def other_group_callout(city_id: str, city_name: str, groups: list[dict[str, object]]) -> str | None:
    """Boston and King County: whether a group other than the last visit moves PR-AUC."""
    if city_id not in CALLOUT_CITIES:
        return None
    moved = [
        group
        for group in groups
        if group["id"] != "last_outcome" and abs(float(group["pr_auc_change"])) >= CALLOUT_PR_AUC
    ]
    threshold = f"{CALLOUT_PR_AUC:.3f}"
    if not moved:
        return (
            f"In {city_name}, no group other than the last outcome changes PR-AUC "
            f"by {threshold} or more."
        )
    bits = ", ".join(
        f"{group['label']} ({_change(float(group['pr_auc_change']))})" for group in moved
    )
    return (
        f"In {city_name}, removing a group other than the last outcome changes PR-AUC "
        f"by {threshold} or more: {bits}."
    )


def largest_gap(slices: list[dict[str, object]]) -> dict[str, object] | None:
    eligible = [item for item in slices if item.get("eligible")]
    if not eligible:
        return None
    return max(eligible, key=lambda item: float(item["pr_auc_gap"]))


def read_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _fmt(value: float) -> str:
    return f"{float(value):.3f}"


def _change(value: float) -> str:
    return f"{float(value):+.3f}"
