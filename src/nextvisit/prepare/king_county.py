"""King County routine inspections. Serious means the file's RED class."""

import json
from itertools import groupby
from pathlib import Path

import polars as pl

from nextvisit.cities.king_county import RAW_PATH, SERIOUS_VIOLATION, START, parse_violation
from nextvisit.prepare.features import assert_features_before_target
from nextvisit.prepare.split import choose_cutoff

INSPECTIONS_PATH = Path("data/processed/king_county/inspections.parquet")
CODEBOOK_PATH = Path("data/processed/king_county/codebook.parquet")
EXAMPLES_PATH = Path("data/processed/king_county/examples.parquet")
CUTOFF_PATH = Path("artifacts/king_county/cutoff.json")

ROUTINE = "Routine Inspection/Field Review"

_INSPECTION_SCHEMA = {
    "business_id": pl.String,
    "inspection_id": pl.String,
    "name": pl.String,
    "zip": pl.String,
    "risk": pl.String,
    "grade": pl.String,
    "inspection_date": pl.Date,
    "score": pl.Float64,
    "positive": pl.Boolean,
    "violation_codes": pl.List(pl.String),
    "violation_count": pl.Int64,
}


def routine_rows(rows: pl.DataFrame) -> pl.DataFrame:
    """Keep routine visits from 2021 that have a business and an inspection id."""
    return rows.filter(
        (pl.col("inspection_type") == ROUTINE)
        & pl.col("business_id").is_not_null()
        & pl.col("inspection_id").is_not_null()
        & pl.col("inspection_date").is_not_null()
        & (pl.col("inspection_date") >= START)
    )


def collapse_inspections(rows: pl.DataFrame) -> pl.DataFrame:
    """One row per routine inspection. Positive when any violation is RED."""
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in routine_rows(rows).iter_rows(named=True):
        grouped.setdefault(row["inspection_id"], []).append(row)
    records: list[dict[str, object]] = []
    for inspection_id, lines in grouped.items():
        first = lines[0]
        codes: list[str] = []
        for line in lines:
            parsed = parse_violation(line["violation_description"])
            if parsed is None:
                continue
            code, _description = parsed
            if code not in codes:
                codes.append(code)
        records.append(
            {
                "business_id": first["business_id"],
                "inspection_id": inspection_id,
                "name": first["name"],
                "zip": first["zip"],
                "risk": first["risk"],
                "grade": first["grade"],
                "inspection_date": first["inspection_date"],
                "score": first["score"],
                "positive": any(line["violation_type"] == SERIOUS_VIOLATION for line in lines),
                "violation_codes": codes,
                "violation_count": sum(line["violation_type"] is not None for line in lines),
            }
        )
    return pl.DataFrame(records, schema=_INSPECTION_SCHEMA)


def build_codebook(rows: pl.DataFrame) -> pl.DataFrame:
    """One official wording per code. Comments are not part of this file."""
    codes: list[str] = []
    titles: list[str] = []
    for row in routine_rows(rows).iter_rows(named=True):
        parsed = parse_violation(row["violation_description"])
        if parsed is None:
            continue
        codes.append(parsed[0])
        titles.append(parsed[1])
    return _most_common(codes, titles)


def build_examples(inspections: pl.DataFrame) -> pl.DataFrame:
    """One row per later routine visit. Features use only earlier dates."""
    ordered = inspections.sort(["business_id", "inspection_date", "inspection_id"])
    examples: list[dict[str, object]] = []
    for _business, visit_group in groupby(ordered.to_dicts(), key=lambda row: row["business_id"]):
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
            examples.append(_example(target, history, previous))
    return pl.DataFrame(examples, schema=_EXAMPLE_SCHEMA)


def prepare_king_county(
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
    return _write(inspections, codebook, examples, inspections_path, codebook_path, examples_path, cutoff_path)


def _example(target: dict[str, object], history: list[dict[str, object]], previous: dict[str, object]) -> dict[str, object]:
    target_date = target["inspection_date"]
    last_positive = next(
        (visit["inspection_date"] for visit in reversed(history) if visit["positive"]),
        None,
    )
    return {
        "business_id": target["business_id"],
        "target_date": target_date,
        "label": int(target["positive"]),
        "risk": previous["risk"],
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


def _most_common(codes: list[str], titles: list[str]) -> pl.DataFrame:
    if not codes:
        return pl.DataFrame(schema={"violation_code": pl.String, "violation_description": pl.String})
    return (
        pl.DataFrame({"violation_code": codes, "violation_description": titles})
        .group_by(["violation_code", "violation_description"])
        .len()
        .sort(["violation_code", "len"], descending=[False, True])
        .unique(subset=["violation_code"], keep="first")
        .select(["violation_code", "violation_description"])
        .sort("violation_code")
    )


def _write(
    inspections: pl.DataFrame,
    codebook: pl.DataFrame,
    examples: pl.DataFrame,
    inspections_path: Path,
    codebook_path: Path,
    examples_path: Path,
    cutoff_path: Path,
) -> tuple[Path, Path]:
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
                "city": "king_county",
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
    "business_id": pl.String,
    "target_date": pl.Date,
    "label": pl.Int64,
    "risk": pl.String,
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
