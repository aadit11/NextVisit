"""Name search inside one city. The match uses that city's own name field."""

from functools import lru_cache

import polars as pl

from nextvisit.cities import get_city
from nextvisit.cities.austin import RAW_PATH as AUSTIN_RAW
from nextvisit.cities.boston import RAW_PATH as BOSTON_RAW
from nextvisit.cities.chicago import RAW_PATH as CHICAGO_RAW
from nextvisit.cities.king_county import RAW_PATH as KING_COUNTY_RAW
from nextvisit.cities.los_angeles import INSPECTIONS_PATH as LOS_ANGELES_RAW
from nextvisit.cities.new_york import RAW_PATH as NEW_YORK_RAW
from nextvisit.cities.san_francisco import RAW_PATH as SAN_FRANCISCO_RAW

LIMIT = 8

_SOURCES = {
    "new_york": (NEW_YORK_RAW, "camis", "borough"),
    "chicago": (CHICAGO_RAW, "license", "zip"),
    "king_county": (KING_COUNTY_RAW, "business_id", "zip"),
    "los_angeles": (LOS_ANGELES_RAW, "facility_id", "zip"),
    "boston": (BOSTON_RAW, "license", "zip"),
    "san_francisco": (SAN_FRANCISCO_RAW, "permit_number", "neighborhood"),
    "austin": (AUSTIN_RAW, "facility_id", "zip"),
}


def search_restaurants(city_id: str, query: str) -> list[dict[str, str | None]]:
    get_city(city_id)
    if city_id not in _SOURCES:
        raise NotImplementedError(f"Name search for {city_id} is not implemented yet.")
    needle = query.strip().casefold()
    if len(needle) < 2:
        return []
    matched = (
        _directory(city_id)
        .filter(pl.col("name_key").str.contains(needle, literal=True))
        .sort(["name", "restaurant_id"])
        .head(LIMIT)
    )
    return matched.select(["restaurant_id", "name", "area", "address"]).to_dicts()


@lru_cache(maxsize=8)
def _directory(city_id: str) -> pl.DataFrame:
    path, id_column, area_column = _SOURCES[city_id]
    names = pl.scan_parquet(path).collect_schema().names()
    columns = [id_column, "name", area_column, "inspection_date"]
    if "address" in names:
        columns.append("address")
    frame = pl.read_parquet(path, columns=columns)
    if "address" not in frame.columns:
        frame = frame.with_columns(pl.lit(None, dtype=pl.String).alias("address"))
    return (
        frame.drop_nulls([id_column, "name"])
        .sort("inspection_date")
        .group_by(id_column, maintain_order=True)
        .agg(
            pl.col("name").last(),
            pl.col(area_column).drop_nulls().last().alias("area"),
            pl.col("address").drop_nulls().last().alias("address"),
        )
        .rename({id_column: "restaurant_id"})
        .with_columns(pl.col("name").str.to_lowercase().alias("name_key"))
        .select(["restaurant_id", "name", "area", "address", "name_key"])
    )
