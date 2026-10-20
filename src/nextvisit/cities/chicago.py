"""Chicago food inspection extract. One source row is already one inspection."""

import os
import re
from datetime import date
from pathlib import Path

import httpx
import polars as pl

from nextvisit.addresses import format_address
from nextvisit.cities.base import CitySpec

SPEC = CitySpec(
    id="chicago",
    name="Chicago",
    label="Next inspection result is Fail",
    source_url="https://data.cityofchicago.org/resource/4ijn-s7e5.json",
    has_work_order=True,
    cuisine_in_source=False,
)

PAGE_SIZE = 10_000
RAW_PATH = Path("data/raw/chicago/inspections.parquet")

_SOURCE_COLUMNS = (
    "inspection_id",
    "license_",
    "dba_name",
    "address",
    "city",
    "state",
    "facility_type",
    "risk",
    "zip",
    "inspection_date",
    "inspection_type",
    "results",
    "violations",
    "latitude",
    "longitude",
)

SCHEMA = {
    "inspection_id": pl.String,
    "license": pl.String,
    "name": pl.String,
    "address": pl.String,
    "facility_type": pl.String,
    "risk": pl.String,
    "zip": pl.String,
    "inspection_date": pl.Date,
    "inspection_type": pl.String,
    "results": pl.String,
    "violations": pl.String,
    "latitude": pl.Float64,
    "longitude": pl.Float64,
}

_VIOLATION = re.compile(r"^(\d+)\.\s*(.*)$", re.DOTALL)


def parse_violations(text: str | None) -> list[tuple[str, str, str]]:
    """Split packed text into violation number, official title, and comment."""
    if not text:
        return []
    parsed: list[tuple[str, str, str]] = []
    for part in text.split(" | "):
        match = _VIOLATION.match(part.strip())
        if match is None:
            continue
        code, rest = match.group(1), match.group(2).strip()
        title, _, comment = rest.partition(" - Comments:")
        parsed.append((code, title.strip(), comment.strip()))
    return parsed


def normalize_rows(rows: list[dict[str, object]]) -> pl.DataFrame:
    """Rename source fields. Phone is never selected."""
    cleaned: list[dict[str, object]] = []
    for row in rows:
        cleaned.append(
            {
                "inspection_id": _text(row.get("inspection_id")),
                "license": _text(row.get("license_")),
                "name": _text(row.get("dba_name")),
                "address": format_address(row.get("address"), row.get("city"), row.get("state"), row.get("zip")),
                "facility_type": _text(row.get("facility_type")),
                "risk": _text(row.get("risk")),
                "zip": _text(row.get("zip")),
                "inspection_date": _parse_date(row.get("inspection_date")),
                "inspection_type": _text(row.get("inspection_type")),
                "results": _text(row.get("results")),
                "violations": _text(row.get("violations")),
                "latitude": _parse_float(row.get("latitude")),
                "longitude": _parse_float(row.get("longitude")),
            }
        )
    return pl.DataFrame(cleaned, schema=SCHEMA)


def download(path: Path = RAW_PATH) -> Path:
    """Page the SODA endpoint and overwrite the raw parquet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frames: list[pl.DataFrame] = []
    offset = 0
    headers = {}
    token = os.environ.get("CHICAGO_APP_TOKEN")
    if token:
        headers["X-App-Token"] = token
    with httpx.Client(timeout=180, headers=headers) as client:
        while True:
            rows = _page(client, offset)
            if not rows:
                break
            frames.append(normalize_rows(rows))
            offset += len(rows)
            print(f"chicago: downloaded {offset} rows", flush=True)
            if len(rows) < PAGE_SIZE:
                break
    if not frames:
        raise RuntimeError("Chicago download returned no rows.")
    pl.concat(frames).write_parquet(path)
    return path


def _page(client: httpx.Client, offset: int) -> list[dict[str, object]]:
    response = client.get(
        SPEC.source_url,
        params={
            "$select": ",".join(_SOURCE_COLUMNS),
            "$order": "inspection_id",
            "$limit": str(PAGE_SIZE),
            "$offset": str(offset),
        },
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("Chicago download returned an unexpected payload.")
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
