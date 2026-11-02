"""San Francisco health inspection scores. Violation wording is packed in one field."""

import os
import re
from datetime import date
from pathlib import Path

import httpx
import polars as pl

from nextvisit.addresses import format_address
from nextvisit.cities.base import CitySpec

SPEC = CitySpec(
    id="san_francisco",
    name="San Francisco",
    label="Next inspection status is Conditional Pass or Closure",
    source_url="https://data.sfgov.org/resource/tvy3-wexg.json",
    cuisine_in_source=False,
)

PAGE_SIZE = 10_000
RAW_PATH = Path("data/raw/san_francisco/inspections.parquet")
POSITIVE_STATUSES = frozenset({"Conditional Pass", "Closure"})
SCORED_STATUSES = POSITIVE_STATUSES | {"Pass"}

_CODE = r"\d[\d.]*(?:\s*\([^)]*\))?"
_GROUP = re.compile(
    rf"(?P<codes>(?:{_CODE},\s*)*{_CODE})\s+-\s+(?P<desc>.*?)(?=,\s+\d|\Z)",
    re.DOTALL,
)

_SOURCE_COLUMNS = (
    "permit_number",
    "dba",
    "street_address",
    "permit_type",
    "inspection_date",
    "facility_rating_status",
    "violation_count",
    "violation_codes",
    "analysis_neighborhood",
    "latitude",
    "longitude",
)

SCHEMA = {
    "permit_number": pl.String,
    "name": pl.String,
    "address": pl.String,
    "permit_type": pl.String,
    "neighborhood": pl.String,
    "inspection_date": pl.Date,
    "status": pl.String,
    "violation_count": pl.Int64,
    "violation_codes": pl.String,
    "latitude": pl.Float64,
    "longitude": pl.Float64,
}


def parse_violation_codes(text: str | None) -> list[tuple[str, str | None]]:
    """Split packed codes. Wording is kept only for the group that states it."""
    if not text or not text.strip():
        return []
    parsed: list[tuple[str, str | None]] = []
    if " - " not in text:
        return [(_code(code), None) for code in text.split(",") if _code(code)]
    cursor = 0
    for match in _GROUP.finditer(text):
        description = " ".join(match.group("desc").split()) or None
        for code in match.group("codes").split(","):
            cleaned = _code(code)
            if cleaned:
                parsed.append((cleaned, description))
        cursor = match.end()
    remainder = text[cursor:].strip(" ,")
    if remainder and " - " not in remainder:
        for code in remainder.split(","):
            cleaned = _code(code)
            if cleaned:
                parsed.append((cleaned, None))
    return parsed


def normalize_rows(rows: list[dict[str, object]]) -> pl.DataFrame:
    """Rename source fields. Inspector name and notes are not selected."""
    cleaned: list[dict[str, object]] = []
    for row in rows:
        cleaned.append(
            {
                "permit_number": _text(row.get("permit_number")),
                "name": _text(row.get("dba")),
                "address": format_address(row.get("street_address"), "San Francisco", "CA"),
                "permit_type": _text(row.get("permit_type")),
                "neighborhood": _text(row.get("analysis_neighborhood")),
                "inspection_date": _parse_date(row.get("inspection_date")),
                "status": _text(row.get("facility_rating_status")),
                "violation_count": _parse_int(row.get("violation_count")),
                "violation_codes": _text(row.get("violation_codes")),
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
    token = os.environ.get("SAN_FRANCISCO_APP_TOKEN")
    if token:
        headers["X-App-Token"] = token
    with httpx.Client(timeout=180, headers=headers, follow_redirects=True) as client:
        while True:
            rows = _page(client, offset)
            if not rows:
                break
            frames.append(normalize_rows(rows))
            offset += len(rows)
            print(f"san_francisco: downloaded {offset} rows", flush=True)
            if len(rows) < PAGE_SIZE:
                break
    if not frames:
        raise RuntimeError("San Francisco download returned no rows.")
    pl.concat(frames).write_parquet(path)
    return path


def _page(client: httpx.Client, offset: int) -> list[dict[str, object]]:
    response = client.get(
        SPEC.source_url,
        params={
            "$select": ",".join(_SOURCE_COLUMNS),
            "$order": "permit_number,inspection_date",
            "$limit": str(PAGE_SIZE),
            "$offset": str(offset),
        },
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("San Francisco download returned an unexpected payload.")
    return payload


def _code(value: str) -> str:
    return " ".join(value.split())


def _text(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    day = value[:10].replace("/", "-")
    return date.fromisoformat(day)


def _parse_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(float(value))


def _parse_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
