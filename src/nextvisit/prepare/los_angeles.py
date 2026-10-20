"""Los Angeles County routine inspections. Serious means 4 or more points.

The violations file marks a major critical deduction as 4 points and a
closure violation as 11. One- and two-point rows are the lower deductions.
The 3-point row is the multiple-major surcharge, not a separate violation.
Pasadena, Long Beach, and Vernon are left out.
"""

import json
from itertools import groupby
from pathlib import Path

import polars as pl

from nextvisit.cities.los_angeles import (
    EXCLUDED_CITIES,
    INSPECTIONS_PATH,
    SERIOUS_POINTS,
    VIOLATIONS_PATH,
)
from nextvisit.prepare.features import assert_features_before_target
from nextvisit.prepare.split import choose_cutoff

PROCESSED_INSPECTIONS_PATH = Path("data/processed/los_angeles/inspections.parquet")
CODEBOOK_PATH = Path("data/processed/los_angeles/codebook.parquet")
EXAMPLES_PATH = Path("data/processed/los_angeles/examples.parquet")
CUTOFF_PATH = Path("artifacts/los_angeles/cutoff.json")

ROUTINE = "ROUTINE INSPECTION"
OUT_OF_COMPLIANCE = "OUT OF COMPLIANCE"

_INSPECTION_SCHEMA = {
    "facility_id": pl.String,
    "inspection_id": pl.String,
    "name": pl.String,
    "pe_description": pl.String,
    "zip": pl.String,
    "inspection_date": pl.Date,
    "score": pl.Float64,
    "grade": pl.String,
    "positive": pl.Boolean,
    "violation_codes": pl.List(pl.String),
    "violation_count": pl.Int64,
}


def scored_routine(inspections: pl.DataFrame) -> pl.DataFrame:
    """Keep routine visits outside Pasadena, Long Beach, and Vernon."""
    city = pl.col("city").fill_null("").str.to_lowercase()
    return inspections.filter(
        (pl.col("service") == ROUTINE)
        & pl.col("facility_id").is_not_null()
        & pl.col("serial_number").is_not_null()
        & pl.col("inspection_date").is_not_null()
        & ~city.is_in(list(EXCLUDED_CITIES))
    )


def collapse_inspections(inspections: pl.DataFrame, violations: pl.DataFrame) -> pl.DataFrame:
    """Join violations onto the routine inspection. Positive means points of 4 or more."""
    routine = scored_routine(inspections)
    cited = violations.filter(
        (pl.col("status") == OUT_OF_COMPLIANCE) & pl.col("violation_code").is_not_null()
    )
    codes = cited.group_by("serial_number").agg(
        pl.col("violation_code").unique(maintain_order=True).alias("violation_codes"),
        pl.len().alias("violation_count"),
    )
    serious = (
        cited.filter(pl.col("points") >= SERIOUS_POINTS)
        .group_by("serial_number")
        .agg(pl.len().alias("serious_count"))
    )
    joined = (
        routine.join(codes, on="serial_number", how="left")
        .join(serious, on="serial_number", how="left")
        .with_columns(
            pl.col("serious_count").fill_null(0).gt(0).alias("positive"),
            pl.col("violation_count").fill_null(0),
            pl.col("violation_codes").fill_null([]),
        )
        .rename({"serial_number": "inspection_id"})
    )
    return joined.select(list(_INSPECTION_SCHEMA)).cast(_INSPECTION_SCHEMA)


def build_codebook(violations: pl.DataFrame) -> pl.DataFrame:
    """One official description per violation code."""
    cited = violations.filter(
        (pl.col("status") == OUT_OF_COMPLIANCE)
        & pl.col("violation_code").is_not_null()
        & pl.col("violation_description").is_not_null()
    )
    if cited.height == 0:
        return pl.DataFrame(schema={"violation_code": pl.String, "violation_description": pl.String})
    return (
        cited.group_by(["violation_code", "violation_description"])
        .len()
        .sort(["violation_code", "len"], descending=[False, True])
        .unique(subset=["violation_code"], keep="first")
        .select(
            pl.col("violation_code"),
            pl.col("violation_description"),
        )
        .sort("violation_code")
    )


def build_examples(inspections: pl.DataFrame) -> pl.DataFrame:
    """One row per later routine visit. Features use only earlier dates."""
    ordered = inspections.sort(["facility_id", "inspection_date", "inspection_id"])
    examples: list[dict[str, object]] = []
    for _facility, visit_group in groupby(ordered.to_dicts(), key=lambda row: row["facility_id"]):
        visits = list(visit_group)
        for index, target in enumerate(visits):
            target_date = target["inspection_date"]
            history = [visit for visit in visits[:index] if visit["inspection_date"] < target_date]
            if not history:
                continue
            assert_features_before_target(
                [visit["inspection_date"] for visit in history],
                target_date,
            )
            previous = history[-1]
            last_positive = next(
                (visit["inspection_date"] for visit in reversed(history) if visit["positive"]),
                None,
            )
            examples.append(
                {
                    "facility_id": target["facility_id"],
                    "target_date": target_date,
                    "label": int(target["positive"]),
                    "pe_description": previous["pe_description"],
                    "zip": previous["zip"],
                    "previous_grade": previous["grade"],
                    "days_since_previous": (target_date - previous["inspection_date"]).days,
                    "previous_positive": bool(previous["positive"]),
                    "previous_score": previous["score"],
                    "prior_inspection_count": len(history),
                    "prior_positive_count": sum(bool(visit["positive"]) for visit in history),
                    "prior_violation_count": sum(int(visit["violation_count"]) for visit in history),
                    "previous_violation_count": int(previous["violation_count"]),
                    "days_since_last_positive": (
                        None if last_positive is None else (target_date - last_positive).days
                    ),
                }
            )
    return pl.DataFrame(examples, schema=_EXAMPLE_SCHEMA)


def prepare_los_angeles(
    inspections_path: Path = INSPECTIONS_PATH,
    violations_path: Path = VIOLATIONS_PATH,
    processed_path: Path = PROCESSED_INSPECTIONS_PATH,
    codebook_path: Path = CODEBOOK_PATH,
    examples_path: Path = EXAMPLES_PATH,
    cutoff_path: Path = CUTOFF_PATH,
) -> tuple[Path, Path]:
    inspections = collapse_inspections(pl.read_parquet(inspections_path), pl.read_parquet(violations_path))
    codebook = build_codebook(pl.read_parquet(violations_path))
    examples = build_examples(inspections)
    cutoff = choose_cutoff(examples["target_date"].to_list())
    examples = examples.with_columns(
        pl.when(pl.col("target_date") <= cutoff)
        .then(pl.lit("train"))
        .otherwise(pl.lit("test"))
        .alias("split")
    )
    processed_path.parent.mkdir(parents=True, exist_ok=True)
    cutoff_path.parent.mkdir(parents=True, exist_ok=True)
    inspections.write_parquet(processed_path)
    codebook.write_parquet(codebook_path)
    examples.write_parquet(examples_path)
    train_rows = examples.filter(pl.col("split") == "train").height
    cutoff_path.write_text(
        json.dumps(
            {
                "city": "los_angeles",
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


_EXAMPLE_SCHEMA = {
    "facility_id": pl.String,
    "target_date": pl.Date,
    "label": pl.Int64,
    "pe_description": pl.String,
    "zip": pl.String,
    "previous_grade": pl.String,
    "days_since_previous": pl.Int64,
    "previous_positive": pl.Boolean,
    "previous_score": pl.Float64,
    "prior_inspection_count": pl.Int64,
    "prior_positive_count": pl.Int64,
    "prior_violation_count": pl.Int64,
    "previous_violation_count": pl.Int64,
    "days_since_last_positive": pl.Int64,
}
