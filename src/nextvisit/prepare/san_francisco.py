"""San Francisco scored inspections. Conditional Pass and Closure are positive.

A code enters the codebook only when that inspection row states the official
wording. A code with no wording stays on the inspection and cannot support a
work-order span.
"""

import json
from itertools import groupby
from pathlib import Path

import polars as pl

from nextvisit.cities.san_francisco import POSITIVE_STATUSES, RAW_PATH, SCORED_STATUSES, parse_violation_codes
from nextvisit.prepare.features import assert_features_before_target
from nextvisit.prepare.split import choose_cutoff

INSPECTIONS_PATH = Path("data/processed/san_francisco/inspections.parquet")
CODEBOOK_PATH = Path("data/processed/san_francisco/codebook.parquet")
EXAMPLES_PATH = Path("data/processed/san_francisco/examples.parquet")
CUTOFF_PATH = Path("artifacts/san_francisco/cutoff.json")

_INSPECTION_SCHEMA = {
    "permit_number": pl.String,
    "inspection_id": pl.String,
    "name": pl.String,
    "permit_type": pl.String,
    "neighborhood": pl.String,
    "inspection_date": pl.Date,
    "status": pl.String,
    "positive": pl.Boolean,
    "violation_codes": pl.List(pl.String),
    "violation_count": pl.Int64,
}


def scored_visits(rows: pl.DataFrame) -> pl.DataFrame:
    """Keep Pass, Conditional Pass, and Closure rows with a permit and a date."""
    kept = rows.filter(
        pl.col("status").is_in(list(SCORED_STATUSES))
        & pl.col("permit_number").is_not_null()
        & pl.col("inspection_date").is_not_null()
    )
    return _without_stranded_date(kept)


def _without_stranded_date(rows: pl.DataFrame) -> pl.DataFrame:
    """Drop one source date that sits more than a year after every other visit."""
    dates = rows["inspection_date"].drop_nulls().unique().sort()
    if dates.len() < 2 or (dates[-1] - dates[-2]).days <= 366:
        return rows
    return rows.filter(pl.col("inspection_date") < dates[-1])


def collapse_inspections(rows: pl.DataFrame) -> pl.DataFrame:
    """One row per permit and date. Positive is Conditional Pass or Closure."""
    records: list[dict[str, object]] = []
    for row in scored_visits(rows).iter_rows(named=True):
        parsed = parse_violation_codes(row["violation_codes"])
        codes: list[str] = []
        for code, _description in parsed:
            if code not in codes:
                codes.append(code)
        count = row["violation_count"]
        records.append(
            {
                "permit_number": row["permit_number"],
                "inspection_id": f"{row['permit_number']}-{row['inspection_date'].isoformat()}",
                "name": row["name"],
                "permit_type": row["permit_type"],
                "neighborhood": row["neighborhood"],
                "inspection_date": row["inspection_date"],
                "status": row["status"],
                "positive": row["status"] in POSITIVE_STATUSES,
                "violation_codes": codes,
                "violation_count": int(count) if count is not None else len(parsed),
            }
        )
    return pl.DataFrame(records, schema=_INSPECTION_SCHEMA)


def build_codebook(rows: pl.DataFrame) -> pl.DataFrame:
    """Official wording from the inspection row. Codes without wording are omitted."""
    codes: list[str] = []
    titles: list[str] = []
    for row in scored_visits(rows).iter_rows(named=True):
        for code, description in parse_violation_codes(row["violation_codes"]):
            if not description:
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
    ordered = inspections.sort(["permit_number", "inspection_date", "inspection_id"])
    examples: list[dict[str, object]] = []
    for _permit, visit_group in groupby(ordered.to_dicts(), key=lambda row: row["permit_number"]):
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
                    "permit_number": target["permit_number"],
                    "target_date": target_date,
                    "label": int(target["positive"]),
                    "permit_type": previous["permit_type"],
                    "neighborhood": previous["neighborhood"],
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


def prepare_san_francisco(
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
                "city": "san_francisco",
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
    "permit_number": pl.String,
    "target_date": pl.Date,
    "label": pl.Int64,
    "permit_type": pl.String,
    "neighborhood": pl.String,
    "days_since_previous": pl.Int64,
    "previous_positive": pl.Boolean,
    "prior_inspection_count": pl.Int64,
    "prior_positive_count": pl.Int64,
    "prior_violation_count": pl.Int64,
    "previous_violation_count": pl.Int64,
    "days_since_last_positive": pl.Int64,
}
