"""Los Angeles County inspections and the violations joined on serial number."""

from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import httpx
import polars as pl

from nextvisit.addresses import format_address
from nextvisit.cities.base import CitySpec

SPEC = CitySpec(
    id="los_angeles",
    name="Los Angeles County",
    label="Next inspection includes a serious violation in the county points system",
    source_url="https://www.arcgis.com/sharing/rest/content/items/19b6607ac82c4512b10811870975dbdc/data",
    has_work_order=True,
    cuisine_in_source=False,
)

INSPECTIONS_URL = SPEC.source_url
VIOLATIONS_URL = "https://www.arcgis.com/sharing/rest/content/items/5eaea9f89b7549ee841da7617d3a9cba/data"
INSPECTIONS_PATH = Path("data/raw/los_angeles/inspections.parquet")
VIOLATIONS_PATH = Path("data/raw/los_angeles/violations.parquet")
# The file's major-critical deductions are 4 points, and closure violations are 11.
SERIOUS_POINTS = 4.0
EXCLUDED_CITIES = frozenset({"pasadena", "long beach", "vernon"})

_INSPECTION_SCHEMA = {
    "facility_id": pl.String,
    "serial_number": pl.String,
    "name": pl.String,
    "address": pl.String,
    "pe_description": pl.String,
    "city": pl.String,
    "zip": pl.String,
    "service": pl.String,
    "inspection_date": pl.Date,
    "score": pl.Float64,
    "grade": pl.String,
}

_VIOLATION_SCHEMA = {
    "serial_number": pl.String,
    "status": pl.String,
    "violation_code": pl.String,
    "violation_description": pl.String,
    "points": pl.Float64,
}


def normalize_inspections(frame: pl.DataFrame) -> pl.DataFrame:
    """Keep the facility and the inspection. Owner name and employee id are dropped."""
    renamed = frame.rename({name: name.strip().lower() for name in frame.columns})
    records = [
        {
            "facility_id": _text(row.get("facility id")),
            "serial_number": _text(row.get("serial number")),
            "name": _text(row.get("facility name")),
            "address": format_address(
                row.get("facility address"),
                row.get("facility city"),
                row.get("facility state"),
                row.get("facility zip"),
            ),
            "pe_description": _text(row.get("pe description")),
            "city": _text(row.get("facility city")),
            "zip": _zip(row.get("facility zip")),
            "service": _text(row.get("service description")),
            "inspection_date": _parse_date(row.get("activity date")),
            "score": _parse_float(row.get("score")),
            "grade": _text(row.get("grade")),
        }
        for row in renamed.iter_rows(named=True)
    ]
    return pl.DataFrame(records, schema=_INSPECTION_SCHEMA)


def normalize_violations(frame: pl.DataFrame) -> pl.DataFrame:
    """Keep the serial number, the code, the official wording, and the points."""
    renamed = frame.rename({name: name.strip().lower() for name in frame.columns})
    records = [
        {
            "serial_number": _text(row.get("serial number")),
            "status": _text(row.get("violation status")),
            "violation_code": _text(row.get("violation code")),
            "violation_description": _text(row.get("violation description")),
            "points": _parse_float(row.get("points")),
        }
        for row in renamed.iter_rows(named=True)
    ]
    return pl.DataFrame(records, schema=_VIOLATION_SCHEMA)


def download(
    inspections_path: Path = INSPECTIONS_PATH,
    violations_path: Path = VIOLATIONS_PATH,
) -> Path:
    """Download both county files and overwrite the raw parquets."""
    inspections_path.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=180, follow_redirects=True) as client:
        inspections = normalize_inspections(_csv(client, INSPECTIONS_URL))
        print(f"los_angeles: downloaded {inspections.height} inspections", flush=True)
        violations = normalize_violations(_csv(client, VIOLATIONS_URL))
        print(f"los_angeles: downloaded {violations.height} violations", flush=True)
    inspections.write_parquet(inspections_path)
    violations.write_parquet(violations_path)
    return inspections_path


def _csv(client: httpx.Client, url: str) -> pl.DataFrame:
    response = client.get(url)
    response.raise_for_status()
    return pl.read_csv(BytesIO(response.content), infer_schema_length=0, encoding="utf8-lossy")


def _text(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value).strip() or None


def _zip(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    digits = "".join(character for character in text if character.isdigit())
    return digits[:5] or None


def _parse_date(value: object) -> date | None:
    text = _text(value)
    if text is None:
        return None
    day = text[:10]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(day, fmt).date()
        except ValueError:
            continue
    return None


def _parse_float(value: object) -> float | None:
    text = _text(value)
    if text is None:
        return None
    return float(text)
