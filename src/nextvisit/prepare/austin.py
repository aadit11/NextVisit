"""Austin routine inspections. The label is a score below 90.

Follow-up visits stay out of the model table. There is no violation text,
so this city has no codebook and no work order.
"""

import json
from itertools import groupby
from pathlib import Path

import polars as pl

from nextvisit.cities.austin import RAW_PATH
from nextvisit.prepare.features import assert_features_before_target
from nextvisit.prepare.split import choose_cutoff

INSPECTIONS_PATH = Path("data/processed/austin/inspections.parquet")
EXAMPLES_PATH = Path("data/processed/austin/examples.parquet")
CUTOFF_PATH = Path("artifacts/austin/cutoff.json")

ROUTINE = "Routine Inspection"
SCORE_LINE = 90

_INSPECTION_SCHEMA = {
    "facility_id": pl.String,
    "inspection_id": pl.String,
    "name": pl.String,
    "zip": pl.String,
    "inspection_date": pl.Date,
    "inspection_type": pl.String,
    "score": pl.Float64,
    "positive": pl.Boolean,
    "latitude": pl.Float64,
    "longitude": pl.Float64,
}


def routine_scores(rows: pl.DataFrame) -> pl.DataFrame:
    """Keep routine visits that have a facility id, a date, and a score."""
    return rows.filter(
        (pl.col("inspection_type") == ROUTINE)
        & pl.col("facility_id").is_not_null()
        & pl.col("inspection_date").is_not_null()
        & pl.col("score").is_not_null()
    )


def collapse_inspections(rows: pl.DataFrame) -> pl.DataFrame:
    """One row per routine inspection. Positive means the score is below 90."""
    kept = routine_scores(rows).with_columns(
        (pl.col("score") < SCORE_LINE).alias("positive")
    )
    return kept.select(list(_INSPECTION_SCHEMA)).cast(_INSPECTION_SCHEMA)


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
                    "zip": previous["zip"],
                    "days_since_previous": (target_date - previous["inspection_date"]).days,
                    "previous_positive": bool(previous["positive"]),
                    "previous_score": previous["score"],
                    "prior_inspection_count": len(history),
                    "prior_positive_count": sum(bool(visit["positive"]) for visit in history),
                    "days_since_last_positive": (
                        None if last_positive is None else (target_date - last_positive).days
                    ),
                }
            )
    return pl.DataFrame(examples, schema=_EXAMPLE_SCHEMA)


def prepare_austin(
    raw_path: Path = RAW_PATH,
    inspections_path: Path = INSPECTIONS_PATH,
    examples_path: Path = EXAMPLES_PATH,
    cutoff_path: Path = CUTOFF_PATH,
) -> tuple[Path, Path]:
    inspections = collapse_inspections(pl.read_parquet(raw_path))
    examples = build_examples(inspections)
    cutoff = choose_cutoff(examples["target_date"].to_list())
    examples = examples.with_columns(
        pl.when(pl.col("target_date") <= cutoff)
        .then(pl.lit("train"))
        .otherwise(pl.lit("test"))
        .alias("split")
    )
    inspections_path.parent.mkdir(parents=True, exist_ok=True)
    cutoff_path.parent.mkdir(parents=True, exist_ok=True)
    inspections.write_parquet(inspections_path)
    examples.write_parquet(examples_path)
    train_rows = examples.filter(pl.col("split") == "train").height
    cutoff_path.write_text(
        json.dumps(
            {
                "city": "austin",
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
    "zip": pl.String,
    "days_since_previous": pl.Int64,
    "previous_positive": pl.Boolean,
    "previous_score": pl.Float64,
    "prior_inspection_count": pl.Int64,
    "prior_positive_count": pl.Int64,
    "days_since_last_positive": pl.Int64,
}
