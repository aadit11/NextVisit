"""New York City DOHMH inspection extract."""

import os
from datetime import date
from pathlib import Path

import httpx
import polars as pl

from nextvisit.cities.base import CitySpec

SPEC = CitySpec(
    id="new_york",
    name="New York",
    label="Next cycle inspection includes a critical violation",
    source_url="https://data.cityofnewyork.us/resource/43nn-pn8j.json",
    has_work_order=True,
    cuisine_in_source=True,
)

PAGE_SIZE = 50_000
RAW_PATH = Path("data/raw/new_york/inspections.parquet")

_SOURCE_COLUMNS = (
    "camis",
    "dba",
    "boro",
    "cuisine_description",
    "inspection_date",
    "inspection_type",
    "violation_code",
    "violation_description",
    "critical_flag",
    "score",
    "grade",
    "latitude",
    "longitude",
    "zipcode",
)

SCHEMA = {
    "camis": pl.String,
    "name": pl.String,
    "borough": pl.String,
    "cuisine": pl.String,
    "inspection_date": pl.Date,
    "inspection_type": pl.String,
    "violation_code": pl.String,
    "violation_description": pl.String,
    "critical_flag": pl.String,
    "score": pl.Float64,
    "grade": pl.String,
    "latitude": pl.Float64,
    "longitude": pl.Float64,
    "zipcode": pl.String,
}


def normalize_rows(rows: list[dict[str, object]]) -> pl.DataFrame:
    """Rename source fields and drop phone before anything is written."""
    cleaned: list[dict[str, object]] = []
    for row in rows:
        cleaned.append(
            {
                "camis": _text(row.get("camis")),
                "name": _text(row.get("dba")),
                "borough": _text(row.get("boro")),
                "cuisine": _text(row.get("cuisine_description")),
                "inspection_date": _parse_date(row.get("inspection_date")),
                "inspection_type": _text(row.get("inspection_type")),
                "violation_code": _text(row.get("violation_code")),
                "violation_description": _text(row.get("violation_description")),
                "critical_flag": _text(row.get("critical_flag")),
                "score": _parse_float(row.get("score")),
                "grade": _text(row.get("grade")),
                "latitude": _parse_float(row.get("latitude")),
                "longitude": _parse_float(row.get("longitude")),
                "zipcode": _text(row.get("zipcode")),
            }
        )
    return pl.DataFrame(cleaned, schema=SCHEMA)


def download(path: Path = RAW_PATH) -> Path:
    """Page the SODA endpoint and overwrite the raw parquet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frames: list[pl.DataFrame] = []
    offset = 0
    headers = {}
    token = os.environ.get("NYC_APP_TOKEN")
    if token:
        headers["X-App-Token"] = token
    with httpx.Client(timeout=120, headers=headers) as client:
        while True:
            rows = _page(client, offset)
            if not rows:
                break
            frames.append(normalize_rows(rows))
            offset += len(rows)
            print(f"new_york: downloaded {offset} rows", flush=True)
            if len(rows) < PAGE_SIZE:
                break
    if not frames:
        raise RuntimeError("New York download returned no rows.")
    pl.concat(frames).write_parquet(path)
    return path


def _page(client: httpx.Client, offset: int) -> list[dict[str, object]]:
    response = client.get(
        SPEC.source_url,
        params={
            "$select": ",".join(_SOURCE_COLUMNS),
            "$order": ":id",
            "$limit": str(PAGE_SIZE),
            "$offset": str(offset),
        },
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("New York download returned an unexpected payload.")
    return payload


def _text(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    return date.fromisoformat(value[:10])


def _parse_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
