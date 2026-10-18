"""History features. Every feature date must be strictly before the target visit."""

import json
from datetime import date
from itertools import groupby
from pathlib import Path

import polars as pl

from nextvisit.prepare.collapse import INSPECTIONS_PATH
from nextvisit.prepare.split import choose_cutoff

EXAMPLES_PATH = Path("data/processed/new_york/examples.parquet")
CUTOFF_PATH = Path("artifacts/new_york/cutoff.json")


class LeakageError(ValueError):
    """A feature is dated on or after the visit being predicted."""


def assert_features_before_target(feature_dates: list[date], target_date: date) -> None:
    late = [day for day in feature_dates if day >= target_date]
    if late:
        raise LeakageError(f"Features dated on or after {target_date.isoformat()}: {late}")


def build_examples(inspections: pl.DataFrame) -> pl.DataFrame:
    """One row per later visit. Features come only from earlier visits."""
    ordered = inspections.sort(["camis", "inspection_date"])
    examples: list[dict[str, object]] = []
    for _camis, visit_group in groupby(ordered.to_dicts(), key=lambda row: row["camis"]):
        visits = list(visit_group)
        if len(visits) < 2:
            continue
        for index in range(1, len(visits)):
            history = visits[:index]
            target = visits[index]
            target_date = target["inspection_date"]
            assert_features_before_target(
                [visit["inspection_date"] for visit in history],
                target_date,
            )
            previous = history[-1]
            last_positive = next(
                (
                    visit["inspection_date"]
                    for visit in reversed(history)
                    if visit["positive"]
                ),
                None,
            )
            examples.append(
                {
                    "camis": target["camis"],
                    "target_date": target_date,
                    "label": int(target["positive"]),
                    "cuisine": previous["cuisine"],
                    "borough": previous["borough"],
                    "days_since_previous": (target_date - previous["inspection_date"]).days,
                    "previous_positive": bool(previous["positive"]),
                    "previous_score": previous["score"],
                    "previous_grade": previous["grade"],
                    "prior_inspection_count": len(history),
                    "prior_positive_count": sum(bool(visit["positive"]) for visit in history),
                    "prior_violation_count": sum(_code_count(visit) for visit in history),
                    "previous_violation_count": _code_count(previous),
                    "days_since_last_positive": (
                        None
                        if last_positive is None
                        else (target_date - last_positive).days
                    ),
                }
            )
    return pl.DataFrame(examples, schema=_EXAMPLE_SCHEMA)


def prepare_new_york(
    inspections_path: Path = INSPECTIONS_PATH,
    examples_path: Path = EXAMPLES_PATH,
    cutoff_path: Path = CUTOFF_PATH,
) -> tuple[Path, Path]:
    examples = build_examples(pl.read_parquet(inspections_path))
    cutoff = choose_cutoff(examples["target_date"].to_list())
    examples = examples.with_columns(
        pl.when(pl.col("target_date") <= cutoff)
        .then(pl.lit("train"))
        .otherwise(pl.lit("test"))
        .alias("split")
    )
    examples_path.parent.mkdir(parents=True, exist_ok=True)
    cutoff_path.parent.mkdir(parents=True, exist_ok=True)
    examples.write_parquet(examples_path)
    train_rows = examples.filter(pl.col("split") == "train").height
    cutoff_path.write_text(
        json.dumps(
            {
                "city": "new_york",
                "cutoff": cutoff.isoformat(),
                "rule": "Last target_date in the earliest 80 percent of examples. That date is train.",
                "train_rows": train_rows,
                "test_rows": examples.height - train_rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return examples_path, cutoff_path


def _code_count(visit: dict[str, object]) -> int:
    codes = visit["violation_codes"]
    if not codes:
        return 0
    return len(codes)


_EXAMPLE_SCHEMA = {
    "camis": pl.String,
    "target_date": pl.Date,
    "label": pl.Int64,
    "cuisine": pl.String,
    "borough": pl.String,
    "days_since_previous": pl.Int64,
    "previous_positive": pl.Boolean,
    "previous_score": pl.Float64,
    "previous_grade": pl.String,
    "prior_inspection_count": pl.Int64,
    "prior_positive_count": pl.Int64,
    "prior_violation_count": pl.Int64,
    "previous_violation_count": pl.Int64,
    "days_since_last_positive": pl.Int64,
}
