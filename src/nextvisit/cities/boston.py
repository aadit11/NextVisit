"""Boston food-establishment inspections. One source row is one violation."""

import re
from datetime import date
from pathlib import Path

import httpx
import polars as pl

from nextvisit.addresses import format_address
from nextvisit.cities.base import CitySpec

SPEC = CitySpec(
    id="boston",
    name="Boston",
    label="Next inspection result is a fail",
    source_url="https://data.boston.gov/api/3/action/datastore_search",
    has_work_order=True,
    cuisine_in_source=False,
)

RESOURCE_ID = "4582bec6-2b4f-4f9e-bc55-cbaa73117f4c"
PAGE_SIZE = 10_000
RAW_PATH = Path("data/raw/boston/inspections.parquet")
# Exact result strings from the file. HE_Filed and HE_Closure are not fails.
FAIL_RESULTS = frozenset({"Fail", "Failed", "HE_Fail", "HE_FailExt", "HE_FAILNOR"})
PASS_RESULTS = frozenset({"Pass", "PassViol", "HE_Pass", "NoViol"})

_FIELDS = (
    "businessname",
    "dbaname",
    "licenseno",
    "descript",
    "result",
    "resultdttm",
    "violation",
    "violdesc",
    "address",
    "city",
    "state",
    "zip",
    "location",
)

SCHEMA = {
    "license": pl.String,
    "inspection_id": pl.String,
    "name": pl.String,
    "address": pl.String,
    "license_description": pl.String,
    "zip": pl.String,
    "inspection_date": pl.Date,
    "result": pl.String,
    "violation_code": pl.String,
    "violation_description": pl.String,
    "latitude": pl.Float64,
    "longitude": pl.Float64,
}

_POINT = re.compile(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)")


def normalize_rows(rows: list[dict[str, object]]) -> pl.DataFrame:
    """Rename source fields. Owner names and inspector comments are not selected."""
    cleaned: list[dict[str, object]] = []
    for row in rows:
        inspected = _parse_date(row.get("resultdttm"))
        latitude, longitude = parse_location(row.get("location"))
        cleaned.append(
            {
                "license": _text(row.get("licenseno")),
                "inspection_id": _text(row.get("resultdttm")),
                "name": _text(row.get("businessname")) or _text(row.get("dbaname")),
                "address": format_address(row.get("address"), row.get("city"), row.get("state"), row.get("zip")),
                "license_description": _text(row.get("descript")),
                "zip": _zip(row.get("zip")),
                "inspection_date": inspected,
                "result": _text(row.get("result")),
                "violation_code": _text(row.get("violation")),
                "violation_description": _text(row.get("violdesc")),
                "latitude": latitude,
                "longitude": longitude,
            }
        )
    return pl.DataFrame(cleaned, schema=SCHEMA)


def download(path: Path = RAW_PATH) -> Path:
    """Page the Boston datastore and overwrite the raw parquet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frames: list[pl.DataFrame] = []
    offset = 0
    with httpx.Client(timeout=180) as client:
        while True:
            rows = _page(client, offset)
            if not rows:
                break
            frames.append(normalize_rows(rows))
            offset += len(rows)
            print(f"boston: downloaded {offset} rows", flush=True)
            if len(rows) < PAGE_SIZE:
                break
    if not frames:
        raise RuntimeError("Boston download returned no rows.")
    pl.concat(frames).write_parquet(path)
    return path


def _page(client: httpx.Client, offset: int) -> list[dict[str, object]]:
    response = client.post(
        SPEC.source_url,
        json={
            "resource_id": RESOURCE_ID,
            "limit": PAGE_SIZE,
            "offset": offset,
            "fields": list(_FIELDS),
            "sort": "_id",
        },
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError("Boston download returned an unexpected payload.")
    records = payload.get("result", {}).get("records")
    if not isinstance(records, list):
        raise RuntimeError("Boston download returned an unexpected payload.")
    return records


def parse_location(value: object) -> tuple[float | None, float | None]:
    """Read the published '(latitude, longitude)' field."""
    text = _text(value)
    if text is None:
        return None, None
    match = _POINT.search(text)
    if match is None:
        return None, None
    latitude, longitude = float(match.group(1)), float(match.group(2))
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None, None
    if latitude == 0 or longitude == 0:
        return None, None
    return latitude, longitude


def merge_coordinates(path: Path = RAW_PATH) -> None:
    """Add the published location onto the Boston file already on disk."""
    rows: list[dict[str, object]] = []
    offset = 0
    with httpx.Client(timeout=180) as client:
        while True:
            response = client.post(
                SPEC.source_url,
                json={
                    "resource_id": RESOURCE_ID,
                    "limit": PAGE_SIZE,
                    "offset": offset,
                    "fields": ["licenseno", "resultdttm", "location"],
                    "sort": "_id",
                },
            )
            response.raise_for_status()
            payload = response.json()
            page = payload.get("result", {}).get("records")
            if not isinstance(page, list):
                raise RuntimeError("Boston location download returned an unexpected payload.")
            if not page:
                break
            for row in page:
                latitude, longitude = parse_location(row.get("location"))
                rows.append(
                    {
                        "license": _text(row.get("licenseno")),
                        "inspection_date": _parse_date(row.get("resultdttm")),
                        "latitude": latitude,
                        "longitude": longitude,
                    }
                )
            offset += len(page)
            print(f"boston locations: {offset}", flush=True)
            if len(page) < PAGE_SIZE:
                break
    latest = (
        pl.DataFrame(rows)
        .drop_nulls(["license", "latitude", "longitude"])
        .sort("inspection_date", nulls_last=False)
        .unique(subset=["license"], keep="last")
        .select(["license", "latitude", "longitude"])
    )
    raw = pl.read_parquet(path)
    if "latitude" in raw.columns:
        raw = raw.drop(["latitude", "longitude"])
    updated = raw.with_columns(pl.col("license").cast(pl.String)).join(
        latest.with_columns(pl.col("license").cast(pl.String)),
        on="license",
        how="left",
    )
    if updated.height != raw.height:
        raise RuntimeError("Boston row count changed while attaching coordinates.")
    temporary = path.with_suffix(".coord.tmp")
    updated.write_parquet(temporary)
    temporary.replace(path)
    filled = updated.filter(pl.col("latitude").is_not_null())["license"].n_unique()
    total = raw["license"].n_unique()
    print(f"{path}: {filled} of {total} restaurants have coordinates", flush=True)


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
    if not isinstance(value, str) or len(value) < 10:
        return None
    return date.fromisoformat(value[:10])
