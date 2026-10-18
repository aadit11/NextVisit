"""Chicago canvass inspections, examples, and codebook.

The source is already one row per inspection. Canvass visits with a pass,
fail, or pass-with-conditions result stay in the model table. The label is
Fail. Violation numbers and the official title are parsed out of the packed
text; the inspector comment is kept beside them.
"""

import json
from itertools import groupby
from pathlib import Path

import polars as pl

from nextvisit.cities.chicago import RAW_PATH, parse_violations
from nextvisit.prepare.features import assert_features_before_target
from nextvisit.prepare.split import choose_cutoff

INSPECTIONS_PATH = Path("data/processed/chicago/inspections.parquet")
CODEBOOK_PATH = Path("data/processed/chicago/codebook.parquet")
EXAMPLES_PATH = Path("data/processed/chicago/examples.parquet")
CUTOFF_PATH = Path("artifacts/chicago/cutoff.json")

CANVASS_TYPES = frozenset({"Canvass", "Canvass Re-Inspection"})
SCORED_RESULTS = frozenset({"Pass", "Fail", "Pass w/ Conditions"})

_INSPECTION_SCHEMA = {
    "license": pl.String,
    "inspection_id": pl.String,
    "name": pl.String,
    "facility_type": pl.String,
    "risk": pl.String,
    "zip": pl.String,
    "inspection_date": pl.Date,
    "inspection_type": pl.String,
    "results": pl.String,
    "positive": pl.Boolean,
    "violation_codes": pl.List(pl.String),
    "violation_comments": pl.List(pl.String),
    "violation_count": pl.Int64,
    "latitude": pl.Float64,
    "longitude": pl.Float64,
}


def scored_canvass(rows: pl.DataFrame) -> pl.DataFrame:
    """Keep routine canvass visits that received a food-safety result."""
    return rows.filter(
        pl.col("inspection_type").is_in(list(CANVASS_TYPES))
        & pl.col("results").is_in(list(SCORED_RESULTS))
        & pl.col("license").is_not_null()
        & pl.col("inspection_date").is_not_null()
    )


def collapse_inspections(rows: pl.DataFrame) -> pl.DataFrame:
    """One processed row per kept inspection, with violation numbers parsed."""
    records: list[dict[str, object]] = []
    for row in scored_canvass(rows).iter_rows(named=True):
        parsed = parse_violations(row["violations"])
        codes: list[str] = []
        comments: list[str] = []
        for code, _title, comment in parsed:
            if code in codes:
                continue
            codes.append(code)
            comments.append(comment)
        records.append(
            {
                "license": row["license"],
                "inspection_id": row["inspection_id"],
                "name": row["name"],
                "facility_type": row["facility_type"],
                "risk": row["risk"],
                "zip": row["zip"],
                "inspection_date": row["inspection_date"],
                "inspection_type": row["inspection_type"],
                "results": row["results"],
                "positive": row["results"] == "Fail",
                "violation_codes": codes,
                "violation_comments": comments,
                "violation_count": len(parsed),
                "latitude": row["latitude"],
                "longitude": row["longitude"],
            }
        )
    return pl.DataFrame(records, schema=_INSPECTION_SCHEMA)


def build_codebook(rows: pl.DataFrame) -> pl.DataFrame:
    """One official title per violation number. Comments stay off this table."""
    codes: list[str] = []
    titles: list[str] = []
    for row in scored_canvass(rows).iter_rows(named=True):
        for code, title, _comment in parse_violations(row["violations"]):
            if not title:
                continue
            codes.append(code)
            titles.append(title)
    if not codes:
        return pl.DataFrame(
            schema={"violation_code": pl.String, "violation_description": pl.String}
        )
    return (
        pl.DataFrame({"violation_code": codes, "violation_description": titles})
        .group_by(["violation_code", "violation_description"])
        .len()
        .sort(["violation_code", "len"], descending=[False, True])
        .unique(subset=["violation_code"], keep="first")
        .select(["violation_code", "violation_description"])
        .sort("violation_code")
    )


def build_examples(inspections: pl.DataFrame) -> pl.DataFrame:
    """One row per later canvass visit. Features use only earlier dates."""
    ordered = inspections.sort(["license", "inspection_date", "inspection_id"])
    examples: list[dict[str, object]] = []
    for _license, visit_group in groupby(ordered.to_dicts(), key=lambda row: row["license"]):
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
                    "license": target["license"],
                    "target_date": target_date,
                    "label": int(target["positive"]),
                    "facility_type": previous["facility_type"],
                    "risk": previous["risk"],
                    "zip": previous["zip"],
                    "days_since_previous": (target_date - previous["inspection_date"]).days,
                    "previous_positive": bool(previous["positive"]),
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


def prepare_chicago(
    raw_path: Path = RAW_PATH,
    inspections_path: Path = INSPECTIONS_PATH,
    codebook_path: Path = CODEBOOK_PATH,
    examples_path: Path = EXAMPLES_PATH,
    cutoff_path: Path = CUTOFF_PATH,
) -> tuple[Path, Path]:
    rows = pl.read_parquet(raw_path)
    inspections = collapse_inspections(rows)
    codebook = build_codebook(rows)
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
    codebook.write_parquet(codebook_path)
    examples.write_parquet(examples_path)
    train_rows = examples.filter(pl.col("split") == "train").height
    cutoff_path.write_text(
        json.dumps(
            {
                "city": "chicago",
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
    "license": pl.String,
    "target_date": pl.Date,
    "label": pl.Int64,
    "facility_type": pl.String,
    "risk": pl.String,
    "zip": pl.String,
    "days_since_previous": pl.Int64,
    "previous_positive": pl.Boolean,
    "prior_inspection_count": pl.Int64,
    "prior_positive_count": pl.Int64,
    "prior_violation_count": pl.Int64,
    "previous_violation_count": pl.Int64,
    "days_since_last_positive": pl.Int64,
}
