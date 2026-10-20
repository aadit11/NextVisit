"""Boston inspections with a pass or fail result. The label is a fail."""

import json
from itertools import groupby
from pathlib import Path

import polars as pl

from nextvisit.cities.boston import FAIL_RESULTS, PASS_RESULTS, RAW_PATH
from nextvisit.prepare.features import assert_features_before_target
from nextvisit.prepare.split import choose_cutoff

INSPECTIONS_PATH = Path("data/processed/boston/inspections.parquet")
CODEBOOK_PATH = Path("data/processed/boston/codebook.parquet")
EXAMPLES_PATH = Path("data/processed/boston/examples.parquet")
CUTOFF_PATH = Path("artifacts/boston/cutoff.json")

SCORED_RESULTS = FAIL_RESULTS | PASS_RESULTS

_INSPECTION_SCHEMA = {
    "license": pl.String,
    "inspection_id": pl.String,
    "name": pl.String,
    "license_description": pl.String,
    "zip": pl.String,
    "inspection_date": pl.Date,
    "result": pl.String,
    "positive": pl.Boolean,
    "violation_codes": pl.List(pl.String),
    "violation_count": pl.Int64,
}


def scored_results(rows: pl.DataFrame) -> pl.DataFrame:
    """Keep pass and fail visits. Hearings, closures, and filings stay out."""
    return rows.filter(
        pl.col("result").is_in(list(SCORED_RESULTS))
        & pl.col("license").is_not_null()
        & pl.col("inspection_id").is_not_null()
        & pl.col("inspection_date").is_not_null()
    )


def collapse_inspections(rows: pl.DataFrame) -> pl.DataFrame:
    """One row per license and result time. Positive means the result is a fail."""
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in scored_results(rows).iter_rows(named=True):
        grouped.setdefault((row["license"], row["inspection_id"]), []).append(row)
    records: list[dict[str, object]] = []
    for (license_id, inspection_id), lines in grouped.items():
        first = lines[0]
        codes: list[str] = []
        for line in lines:
            code = line["violation_code"]
            if code and code not in codes:
                codes.append(code)
        records.append(
            {
                "license": license_id,
                "inspection_id": inspection_id,
                "name": first["name"],
                "license_description": first["license_description"],
                "zip": first["zip"],
                "inspection_date": first["inspection_date"],
                "result": first["result"],
                "positive": first["result"] in FAIL_RESULTS,
                "violation_codes": codes,
                "violation_count": sum(line["violation_code"] is not None for line in lines),
            }
        )
    return pl.DataFrame(records, schema=_INSPECTION_SCHEMA)


def build_codebook(rows: pl.DataFrame) -> pl.DataFrame:
    """One official description per violation code."""
    codes: list[str] = []
    titles: list[str] = []
    for row in scored_results(rows).iter_rows(named=True):
        code = row["violation_code"]
        description = row["violation_description"]
        if not code or not description:
            continue
        codes.append(code)
        titles.append(description)
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


def build_examples(inspections: pl.DataFrame) -> pl.DataFrame:
    """One row per later scored visit. Features use only earlier dates."""
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
                    "license_description": previous["license_description"],
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


def prepare_boston(
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
                "city": "boston",
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
    "license_description": pl.String,
    "zip": pl.String,
    "days_since_previous": pl.Int64,
    "previous_positive": pl.Boolean,
    "prior_inspection_count": pl.Int64,
    "prior_positive_count": pl.Int64,
    "prior_violation_count": pl.Int64,
    "previous_violation_count": pl.Int64,
    "days_since_last_positive": pl.Int64,
}
