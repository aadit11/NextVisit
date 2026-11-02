"""King County food inspections. One source row is one violation, from 2021 on."""

import os
from datetime import date
from pathlib import Path

import httpx
import polars as pl

from nextvisit.addresses import format_address
from nextvisit.cities.base import CitySpec

SPEC = CitySpec(
    id="king_county",
    name="King County",
    label="Next inspection includes a serious violation",
    source_url="https://data.kingcounty.gov/resource/r878-4sxa.json",
    has_work_order=True,
    cuisine_in_source=False,
)

PAGE_SIZE = 10_000
RAW_PATH = Path("data/raw/king_county/inspections.parquet")
# The file's own classes are RED and BLUE. RED is the serious class.
SERIOUS_VIOLATION = "RED"
START = date(2021, 1, 1)

_SOURCE_COLUMNS = (
    "business_id",
    "inspection_serial_num",
    "name",
    "address",
    "city",
    "zip_code",
    "inspection_date",
    "inspection_type",
    "inspection_score",
    "risk_category",
    "grade",
    "violation_type",
    "violation_description",
)

SCHEMA = {
    "business_id": pl.String,
    "inspection_id": pl.String,
    "name": pl.String,
    "address": pl.String,
    "zip": pl.String,
    "inspection_date": pl.Date,
    "inspection_type": pl.String,
    "score": pl.Float64,
    "risk": pl.String,
    "grade": pl.String,
    "violation_type": pl.String,
    "violation_description": pl.String,
}


def parse_violation(text: str | None) -> tuple[str, str] | None:
    """Split '2120 - official wording' into the code and the wording."""
    if not text or " - " not in text:
        return None
    code, description = text.split(" - ", 1)
    code, description = code.strip(), description.strip()
    if not code or not description:
        return None
    return code, description


def normalize_rows(rows: list[dict[str, object]]) -> pl.DataFrame:
    """Rename source fields. Phone is never selected."""
    cleaned: list[dict[str, object]] = []
    for row in rows:
        cleaned.append(
            {
                "business_id": _text(row.get("business_id")),
                "inspection_id": _text(row.get("inspection_serial_num")),
                "name": _text(row.get("name")),
                "address": format_address(row.get("address"), row.get("city"), "WA", row.get("zip_code")),
                "zip": _zip(row.get("zip_code")),
                "inspection_date": _parse_date(row.get("inspection_date")),
                "inspection_type": _text(row.get("inspection_type")),
                "score": _parse_float(row.get("inspection_score")),
                "risk": _text(row.get("risk_category")),
                "grade": _text(row.get("grade")),
                "violation_type": _text(row.get("violation_type")),
                "violation_description": _text(row.get("violation_description")),
            }
        )
    return pl.DataFrame(cleaned, schema=SCHEMA)


def download(path: Path = RAW_PATH) -> Path:
    """Page routine-and-other rows from 2021 and overwrite the raw parquet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frames: list[pl.DataFrame] = []
    offset = 0
    headers = {}
    token = os.environ.get("KING_COUNTY_APP_TOKEN")
    if token:
        headers["X-App-Token"] = token
    with httpx.Client(timeout=180, headers=headers) as client:
        while True:
            rows = _page(client, offset)
            if not rows:
                break
            frames.append(normalize_rows(rows))
            offset += len(rows)
            print(f"king_county: downloaded {offset} rows", flush=True)
            if len(rows) < PAGE_SIZE:
                break
    if not frames:
        raise RuntimeError("King County download returned no rows.")
    pl.concat(frames).write_parquet(path)
    return path


def _page(client: httpx.Client, offset: int) -> list[dict[str, object]]:
    response = client.get(
        SPEC.source_url,
        params={
            "$select": ",".join(_SOURCE_COLUMNS),
            "$where": "inspection_date >= '2021-01-01T00:00:00.000'",
            "$order": "inspection_serial_num",
            "$limit": str(PAGE_SIZE),
            "$offset": str(offset),
        },
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("King County download returned an unexpected payload.")
    return payload


def _text(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _zip(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    digits = "".join(character for character in text if character.isdigit())
    return digits[:5] or None


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    return date.fromisoformat(value[:10])


def _parse_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
