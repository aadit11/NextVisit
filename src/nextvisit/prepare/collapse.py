"""Turn violation rows into one row per cycle inspection."""

from datetime import date
from pathlib import Path

import polars as pl

from nextvisit.cities.new_york import RAW_PATH

UNINSPECTED = date(1900, 1, 1)
INSPECTIONS_PATH = Path("data/processed/new_york/inspections.parquet")
CODEBOOK_PATH = Path("data/processed/new_york/codebook.parquet")


def cycle_rows(rows: pl.DataFrame) -> pl.DataFrame:
    """Keep cycle inspections. Uninspected permits and other programs stay out."""
    inspection_type = pl.col("inspection_type").fill_null("")
    return rows.filter(
        inspection_type.str.starts_with("Cycle Inspection")
        & (pl.col("inspection_date") != UNINSPECTED)
    )


def collapse_inspections(rows: pl.DataFrame) -> pl.DataFrame:
    """One row per restaurant and date. Violation codes are kept as a list."""
    kept = cycle_rows(rows)
    return (
        kept.group_by(["camis", "inspection_date"])
        .agg(
            pl.col("name").drop_nulls().first(),
            pl.col("borough").drop_nulls().first(),
            pl.col("cuisine").drop_nulls().first(),
            pl.col("inspection_type").drop_nulls().first(),
            pl.col("score").drop_nulls().first(),
            pl.col("grade").drop_nulls().first(),
            pl.col("latitude").drop_nulls().first(),
            pl.col("longitude").drop_nulls().first(),
            pl.col("zipcode").drop_nulls().first(),
            (pl.col("critical_flag") == "Critical").any().alias("positive"),
            pl.col("violation_code")
            .drop_nulls()
            .unique(maintain_order=True)
            .alias("violation_codes"),
        )
        .sort(["camis", "inspection_date"])
    )


def build_codebook(rows: pl.DataFrame) -> pl.DataFrame:
    """One official description per violation code, from the rows we keep."""
    kept = cycle_rows(rows)
    return (
        kept.filter(pl.col("violation_code").is_not_null())
        .group_by("violation_code")
        .agg(pl.col("violation_description").drop_nulls().first())
        .sort("violation_code")
    )


def write_new_york(
    raw_path: Path = RAW_PATH,
    inspections_path: Path = INSPECTIONS_PATH,
    codebook_path: Path = CODEBOOK_PATH,
) -> tuple[Path, Path]:
    rows = pl.read_parquet(raw_path)
    inspections_path.parent.mkdir(parents=True, exist_ok=True)
    collapse_inspections(rows).write_parquet(inspections_path)
    build_codebook(rows).write_parquet(codebook_path)
    return inspections_path, codebook_path
