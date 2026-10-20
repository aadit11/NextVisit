"""Austin food-establishment inspection scores. The id is facility_id."""

import os
from datetime import date
from pathlib import Path

import httpx
import polars as pl

from nextvisit.addresses import address_part
from nextvisit.cities.base import CitySpec

SPEC = CitySpec(
    id="austin",
    name="Austin",
    label="Next routine inspection scores below 90",
    source_url="https://data.austintexas.gov/resource/ecmv-9xxi.json",
    has_work_order=False,
    cuisine_in_source=False,
)

PAGE_SIZE = 10_000
RAW_PATH = Path("data/raw/austin/inspections.parquet")

_SOURCE_COLUMNS = (
    "facility_id",
    "inspectionid",
    "restaurant_name",
    "address",
    "zip_code",
    "inspection_date",
    "process_description",
    "score",
    "lat",
    "lng",
)

SCHEMA = {
    "facility_id": pl.String,
    "inspection_id": pl.String,
    "name": pl.String,
    "address": pl.String,
    "zip": pl.String,
    "inspection_date": pl.Date,
    "inspection_type": pl.String,
    "score": pl.Float64,
    "latitude": pl.Float64,
    "longitude": pl.Float64,
}


def normalize_rows(rows: list[dict[str, object]]) -> pl.DataFrame:
    """Rename source fields. Phone is never selected. The address line is already complete."""
    cleaned: list[dict[str, object]] = []
    for row in rows:
        cleaned.append(
            {
                "facility_id": _text(row.get("facility_id")),
                "inspection_id": _text(row.get("inspectionid")),
                "name": _text(row.get("restaurant_name")),
                "address": address_part(row.get("address")),
                "zip": _zip(row.get("zip_code")),
                "inspection_date": _parse_date(row.get("inspection_date")),
                "inspection_type": _text(row.get("process_description")),
                "score": _parse_float(row.get("score")),
                "latitude": _parse_float(row.get("lat")),
                "longitude": _parse_float(row.get("lng")),
            }
        )
    return pl.DataFrame(cleaned, schema=SCHEMA)


def download(path: Path = RAW_PATH) -> Path:
    """Page the SODA endpoint and overwrite the raw parquet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frames: list[pl.DataFrame] = []
    offset = 0
    headers = {}
    token = os.environ.get("AUSTIN_APP_TOKEN")
    if token:
        headers["X-App-Token"] = token
    with httpx.Client(timeout=120, headers=headers) as client:
        while True:
            rows = _page(client, offset)
            if not rows:
                break
            frames.append(normalize_rows(rows))
            offset += len(rows)
            print(f"austin: downloaded {offset} rows", flush=True)
            if len(rows) < PAGE_SIZE:
                break
    if not frames:
        raise RuntimeError("Austin download returned no rows.")
    pl.concat(frames).write_parquet(path)
    return path


def _page(client: httpx.Client, offset: int) -> list[dict[str, object]]:
    response = client.get(
        SPEC.source_url,
        params={
            "$select": ",".join(_SOURCE_COLUMNS),
            "$order": "inspectionid",
            "$limit": str(PAGE_SIZE),
            "$offset": str(offset),
        },
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("Austin download returned an unexpected payload.")
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
