"""Join each city's published street address onto the raw parquet already on disk.

The inspection rows stay as they are. Only an address column is added, using the
latest non-empty line for that restaurant.
"""

import sys
import time
from io import BytesIO
from pathlib import Path

import httpx
import polars as pl

from nextvisit.addresses import address_part, format_address, street_line
from nextvisit.cities.austin import RAW_PATH as AUSTIN_RAW
from nextvisit.cities.austin import SPEC as AUSTIN_SPEC
from nextvisit.cities.boston import RAW_PATH as BOSTON_RAW
from nextvisit.cities.boston import RESOURCE_ID as BOSTON_RESOURCE
from nextvisit.cities.boston import SPEC as BOSTON_SPEC
from nextvisit.cities.chicago import RAW_PATH as CHICAGO_RAW
from nextvisit.cities.chicago import SPEC as CHICAGO_SPEC
from nextvisit.cities.king_county import RAW_PATH as KING_COUNTY_RAW
from nextvisit.cities.king_county import SPEC as KING_COUNTY_SPEC
from nextvisit.cities.los_angeles import INSPECTIONS_PATH as LOS_ANGELES_RAW
from nextvisit.cities.los_angeles import INSPECTIONS_URL as LOS_ANGELES_URL
from nextvisit.cities.los_angeles import normalize_inspections
from nextvisit.cities.new_york import RAW_PATH as NEW_YORK_RAW
from nextvisit.cities.new_york import SPEC as NEW_YORK_SPEC
from nextvisit.cities.san_francisco import RAW_PATH as SAN_FRANCISCO_RAW
from nextvisit.cities.san_francisco import SPEC as SAN_FRANCISCO_SPEC
from nextvisit.download import load_env


def attach_new_york() -> None:
    rows = _soda(
        NEW_YORK_SPEC.source_url,
        "camis,building,street,boro,zipcode,inspection_date",
        ":id",
        token_env="NYC_APP_TOKEN",
    )
    _attach(
        NEW_YORK_RAW,
        "camis",
        [
            {
                "camis": _text(row.get("camis")),
                "inspection_date": _day(row.get("inspection_date")),
                "address": format_address(
                    street_line(row.get("building"), row.get("street")),
                    row.get("boro"),
                    "NY",
                    row.get("zipcode"),
                ),
            }
            for row in rows
        ],
    )


def attach_chicago() -> None:
    rows = _soda(
        CHICAGO_SPEC.source_url,
        "license_,address,city,state,zip,inspection_date",
        "inspection_id",
        token_env="CHICAGO_APP_TOKEN",
    )
    _attach(
        CHICAGO_RAW,
        "license",
        [
            {
                "license": _text(row.get("license_")),
                "inspection_date": _day(row.get("inspection_date")),
                "address": format_address(row.get("address"), row.get("city"), row.get("state"), row.get("zip")),
            }
            for row in rows
        ],
    )


def attach_king_county() -> None:
    rows = _soda(
        KING_COUNTY_SPEC.source_url,
        "business_id,address,city,zip_code,inspection_date",
        "inspection_serial_num",
        token_env="KING_COUNTY_APP_TOKEN",
        where="inspection_date >= '2021-01-01T00:00:00.000'",
    )
    _attach(
        KING_COUNTY_RAW,
        "business_id",
        [
            {
                "business_id": _text(row.get("business_id")),
                "inspection_date": _day(row.get("inspection_date")),
                "address": format_address(row.get("address"), row.get("city"), "WA", row.get("zip_code")),
            }
            for row in rows
        ],
    )


def attach_los_angeles() -> None:
    with httpx.Client(timeout=180, follow_redirects=True) as client:
        response = client.get(LOS_ANGELES_URL)
        response.raise_for_status()
        frame = pl.read_csv(BytesIO(response.content), infer_schema_length=0, encoding="utf8-lossy")
    addresses = normalize_inspections(frame).select(["facility_id", "inspection_date", "address"])
    _attach(LOS_ANGELES_RAW, "facility_id", addresses)


def attach_boston() -> None:
    rows: list[dict[str, object]] = []
    offset = 0
    page_size = 10_000
    with httpx.Client(timeout=180) as client:
        while True:
            response = _request(
                lambda: client.post(
                    BOSTON_SPEC.source_url,
                    json={
                        "resource_id": BOSTON_RESOURCE,
                        "limit": page_size,
                        "offset": offset,
                        "fields": ["licenseno", "address", "city", "state", "zip", "resultdttm"],
                        "sort": "_id",
                    },
                )
            )
            payload = response.json()
            page = payload.get("result", {}).get("records")
            if not isinstance(page, list):
                raise RuntimeError("Boston address download returned an unexpected payload.")
            if not page:
                break
            rows.extend(page)
            offset += len(page)
            print(f"boston addresses: {offset}", flush=True)
            if len(page) < page_size:
                break
    _attach(
        BOSTON_RAW,
        "license",
        [
            {
                "license": _text(row.get("licenseno")),
                "inspection_date": _day(row.get("resultdttm")),
                "address": format_address(row.get("address"), row.get("city"), row.get("state"), row.get("zip")),
            }
            for row in rows
        ],
    )


def attach_san_francisco() -> None:
    rows = _soda(
        SAN_FRANCISCO_SPEC.source_url,
        "permit_number,street_address,inspection_date",
        "permit_number,inspection_date",
        token_env="SAN_FRANCISCO_APP_TOKEN",
        follow_redirects=True,
    )
    _attach(
        SAN_FRANCISCO_RAW,
        "permit_number",
        [
            {
                "permit_number": _text(row.get("permit_number")),
                "inspection_date": _day(row.get("inspection_date")),
                "address": format_address(row.get("street_address"), "San Francisco", "CA"),
            }
            for row in rows
        ],
    )


def attach_austin() -> None:
    rows = _soda(
        AUSTIN_SPEC.source_url,
        "facility_id,address,inspection_date",
        "inspectionid",
        token_env="AUSTIN_APP_TOKEN",
    )
    _attach(
        AUSTIN_RAW,
        "facility_id",
        [
            {
                "facility_id": _text(row.get("facility_id")),
                "inspection_date": _day(row.get("inspection_date")),
                "address": address_part(row.get("address")),
            }
            for row in rows
        ],
    )


def _soda(
    url: str,
    select: str,
    order: str,
    *,
    token_env: str,
    where: str | None = None,
    follow_redirects: bool = False,
) -> list[dict[str, object]]:
    import os

    headers = {}
    token = os.environ.get(token_env)
    if token:
        headers["X-App-Token"] = token
    rows: list[dict[str, object]] = []
    offset = 0
    page_size = 50_000
    with httpx.Client(timeout=180, headers=headers, follow_redirects=follow_redirects) as client:
        while True:
            params = {
                "$select": select,
                "$order": order,
                "$limit": str(page_size),
                "$offset": str(offset),
            }
            if where:
                params["$where"] = where
            response = _request(lambda: client.get(url, params=params))
            page = response.json()
            if not isinstance(page, list):
                raise RuntimeError(f"Unexpected address payload from {url}")
            if not page:
                break
            rows.extend(page)
            offset += len(page)
            print(f"{url.rsplit('/', 1)[-1]} addresses: {offset}", flush=True)
            if len(page) < page_size:
                break
    return rows


def _attach(path: Path, id_column: str, addresses: pl.DataFrame | list[dict[str, object]]) -> None:
    frame = addresses if isinstance(addresses, pl.DataFrame) else pl.DataFrame(addresses)
    raw = pl.read_parquet(path)
    if "address" in raw.columns:
        raw = raw.drop("address")
    latest = (
        frame.with_columns(pl.col(id_column).cast(pl.String))
        .drop_nulls([id_column, "address"])
        .sort("inspection_date", nulls_last=False)
        .unique(subset=[id_column], keep="last")
        .select([id_column, "address"])
        .rename({id_column: "_join_id"})
    )
    keyed = raw.with_columns(pl.col(id_column).cast(pl.String).alias("_join_id"))
    updated = keyed.join(latest, on="_join_id", how="left").drop("_join_id")
    if updated.height != raw.height:
        raise RuntimeError(f"{path.name} row count changed while attaching addresses.")
    filled = updated.filter(pl.col("address").is_not_null())[id_column].n_unique()
    total = raw[id_column].n_unique()
    temporary = path.with_suffix(".address.tmp")
    updated.write_parquet(temporary)
    temporary.replace(path)
    print(f"{path}: {filled} of {total} restaurants have an address", flush=True)


def _request(call) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            response = call()
            response.raise_for_status()
            return response
        except httpx.HTTPError as error:
            last_error = error
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("Address download failed after retries.") from last_error


def _text(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value).strip() or None


def _day(value: object) -> str:
    text = _text(value) or ""
    return text[:10]


_ATTACH = {
    "new_york": attach_new_york,
    "chicago": attach_chicago,
    "king_county": attach_king_county,
    "los_angeles": attach_los_angeles,
    "boston": attach_boston,
    "san_francisco": attach_san_francisco,
    "austin": attach_austin,
}


def main() -> None:
    load_env()
    chosen = sys.argv[1:] or list(_ATTACH)
    unknown = [city for city in chosen if city not in _ATTACH]
    if unknown:
        raise SystemExit("Unknown city: " + ", ".join(unknown))
    for city_id in chosen:
        _ATTACH[city_id]()


if __name__ == "__main__":
    main()
