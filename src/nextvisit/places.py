"""One row per restaurant: street, last inspection, and the filters a diner uses."""

import math
from functools import lru_cache
from pathlib import Path

import polars as pl

from nextvisit.accounts import stats_for
from nextvisit.cities import get_city
from nextvisit.cities.austin import RAW_PATH as AUSTIN_RAW
from nextvisit.cities.boston import RAW_PATH as BOSTON_RAW
from nextvisit.cities.chicago import RAW_PATH as CHICAGO_RAW
from nextvisit.cities.king_county import RAW_PATH as KING_COUNTY_RAW
from nextvisit.cities.los_angeles import INSPECTIONS_PATH as LOS_ANGELES_RAW
from nextvisit.cities.new_york import RAW_PATH as NEW_YORK_RAW
from nextvisit.cities.san_francisco import RAW_PATH as SAN_FRANCISCO_RAW
from nextvisit.osm import cached_cuisines
from nextvisit.peers import grade_rank, peer_standing
from nextvisit.prepare.austin import INSPECTIONS_PATH as AUSTIN_VISITS
from nextvisit.prepare.boston import INSPECTIONS_PATH as BOSTON_VISITS
from nextvisit.prepare.chicago import INSPECTIONS_PATH as CHICAGO_VISITS
from nextvisit.prepare.collapse import INSPECTIONS_PATH as NEW_YORK_VISITS
from nextvisit.prepare.king_county import INSPECTIONS_PATH as KING_COUNTY_VISITS
from nextvisit.prepare.los_angeles import PROCESSED_INSPECTIONS_PATH as LOS_ANGELES_VISITS
from nextvisit.prepare.san_francisco import INSPECTIONS_PATH as SAN_FRANCISCO_VISITS

NAME_LIMIT = 8
FILTER_LIMIT = 24
CLEANER_SCORE_LIMIT = 30
CLEANER_LIST_LIMIT = 3

# South, north, west, east. Points outside the city, including 0,0 placeholders, stay off the map.
_CITY_BOX = {
    "new_york": (40.40, 41.00, -74.30, -73.65),
    "chicago": (41.60, 42.10, -88.00, -87.50),
    "king_county": (47.00, 47.80, -122.60, -121.00),
    "los_angeles": (33.20, 34.90, -119.00, -117.60),
    "boston": (41.95, 42.50, -71.30, -70.70),
    "san_francisco": (37.55, 37.90, -122.55, -122.10),
    "austin": (30.00, 30.70, -98.20, -97.20),
}

# raw path, id, area, processed path, grade column, cuisine column
_SOURCES = {
    "new_york": (NEW_YORK_RAW, "camis", "borough", NEW_YORK_VISITS, "grade", "cuisine"),
    "chicago": (CHICAGO_RAW, "license", "zip", CHICAGO_VISITS, "results", None),
    "king_county": (KING_COUNTY_RAW, "business_id", "zip", KING_COUNTY_VISITS, "grade", None),
    "los_angeles": (LOS_ANGELES_RAW, "facility_id", "zip", LOS_ANGELES_VISITS, "grade", None),
    "boston": (BOSTON_RAW, "license", "zip", BOSTON_VISITS, "result", None),
    "san_francisco": (SAN_FRANCISCO_RAW, "permit_number", "neighborhood", SAN_FRANCISCO_VISITS, "status", None),
    "austin": (AUSTIN_RAW, "facility_id", "zip", AUSTIN_VISITS, None, None),
}


def search_restaurants(
    city_id: str,
    query: str,
    *,
    area: str = "",
    cuisine: str = "",
    grade: str = "",
    clean: bool = False,
) -> list[dict[str, object]]:
    get_city(city_id)
    if city_id not in _SOURCES:
        raise NotImplementedError(f"Name search for {city_id} is not implemented yet.")
    needle = query.strip().casefold()
    area_text = area.strip()
    cuisine_text = cuisine.strip()
    grade_text = grade.strip()
    if len(needle) < 2 and not any((area_text, cuisine_text, grade_text, clean)):
        return []
    frame = _with_cached_cuisine(_directory(city_id), city_id)
    matched = apply_filters(
        frame,
        needle=needle if len(needle) >= 2 else "",
        area=area_text,
        cuisine=cuisine_text,
        grade=grade_text,
        clean=clean,
        limit=NAME_LIMIT if len(needle) >= 2 else FILTER_LIMIT,
    )
    rows = [_public_row(row) for row in matched.iter_rows(named=True)]
    ratings = stats_for(city_id, [str(row["restaurant_id"]) for row in rows])
    for row in rows:
        average, count = ratings.get(str(row["restaurant_id"]), (None, 0))
        row["average_stars"] = average
        row["review_count"] = count
    return rows


def map_points(city_id: str) -> list[dict[str, object]]:
    """Every restaurant in this city that has a coordinate inside the city."""
    get_city(city_id)
    if city_id not in _SOURCES:
        raise NotImplementedError(f"Map points for {city_id} are not implemented yet.")
    south, north, west, east = _CITY_BOX[city_id]
    frame = _directory(city_id).filter(
        pl.col("latitude").is_between(south, north) & pl.col("longitude").is_between(west, east)
    )
    return [
        {
            "restaurant_id": str(row["restaurant_id"]),
            "name": row["name"],
            "address": _text(row["address"]),
            "latitude": row["latitude"],
            "longitude": row["longitude"],
        }
        for row in frame.select(["restaurant_id", "name", "address", "latitude", "longitude"]).iter_rows(named=True)
    ]


def facets(city_id: str) -> dict[str, list[str]]:
    get_city(city_id)
    if city_id not in _SOURCES:
        raise NotImplementedError(f"Filters for {city_id} are not implemented yet.")
    frame = _with_cached_cuisine(_directory(city_id), city_id)
    return {
        "areas": _unique(frame, "area"),
        "cuisines": _unique(frame, "cuisine"),
        "grades": _unique(frame, "grade"),
    }


def one(city_id: str, restaurant_id: str) -> dict[str, object] | None:
    if city_id not in _SOURCES:
        return None
    frame = _with_cached_cuisine(_directory(city_id), city_id).filter(
        pl.col("restaurant_id") == restaurant_id
    )
    if frame.height == 0:
        return None
    return _public_row(frame.row(0, named=True))


def peer_comparison(
    city_id: str,
    restaurant_id: str,
    *,
    area: str | None,
    cuisine: str | None,
    grade: str | None,
) -> dict[str, object]:
    """Count the same cuisine in the same area and rank this last grade among them."""
    empty = {"peer_count": 0, "peer_graded_count": 0, "peer_standing": None}
    if city_id not in _SOURCES or not area or not cuisine:
        return empty
    frame = _with_cached_cuisine(_directory(city_id), city_id)
    group = frame.filter(
        pl.col("area").cast(pl.String).str.strip_chars() == area,
        pl.col("cuisine").is_not_null(),
        pl.col("cuisine").str.to_lowercase() == cuisine.casefold(),
    )
    others = group.filter(pl.col("restaurant_id") != restaurant_id)
    included = group.filter(pl.col("restaurant_id") == restaurant_id).height > 0
    own_rank = grade_rank(city_id, grade)
    other_ranks = [
        rank
        for value in others["grade"].to_list()
        if (rank := grade_rank(city_id, _text(value))) is not None
    ]
    graded_count = len(other_ranks) + (1 if own_rank is not None else 0)
    return {
        "peer_count": group.height if included else others.height + 1,
        "peer_graded_count": graded_count,
        "peer_standing": peer_standing(own_rank, other_ranks),
    }


def nearby_places(
    city_id: str,
    restaurant_id: str,
    *,
    area: str | None,
    cuisine: str | None,
    own_probability: float | None,
    origin_latitude: float | None = None,
    origin_longitude: float | None = None,
) -> dict[str, object]:
    """List a few real neighbors, with the distance from this restaurant.

    The city's model picks neighbors whose next inspection looks cleaner.
    When it finds none, the nearest places of the same cuisine that have
    coordinates fill the list. The count sentence stays either way.
    """
    empty: dict[str, object] = {"nearby_basis": None, "cleaner_peers": []}
    if city_id not in _SOURCES or not area or not cuisine:
        return empty
    frame = _with_cached_cuisine(_directory(city_id), city_id)
    others = frame.filter(
        pl.col("area").cast(pl.String).str.strip_chars() == area,
        pl.col("cuisine").is_not_null(),
        pl.col("cuisine").str.to_lowercase() == cuisine.casefold(),
        pl.col("restaurant_id") != restaurant_id,
        pl.col("name").is_not_null(),
    )
    origin_lat = _number(origin_latitude)
    origin_lng = _number(origin_longitude)
    candidates = [
        _with_distance(row, origin_lat, origin_lng)
        for row in others.select(
            ["restaurant_id", "name", "grade", "address", "latitude", "longitude"]
        ).to_dicts()
    ]
    if not candidates:
        return empty
    ranked = sorted(candidates, key=lambda row: _candidate_key(city_id, row))
    cleaner = _cleaner_than(city_id, ranked[:CLEANER_SCORE_LIMIT], own_probability)
    if cleaner:
        cleaner.sort(key=_distance_key)
        return {"nearby_basis": "cleaner", "cleaner_peers": [_public_peer(row) for row in cleaner[:CLEANER_LIST_LIMIT]]}
    nearest = [row for row in candidates if row["distance_miles"] is not None]
    nearest.sort(key=_distance_key)
    if not nearest:
        return empty
    return {"nearby_basis": "closest", "cleaner_peers": [_public_peer(row) for row in nearest[:CLEANER_LIST_LIMIT]]}


def _cleaner_than(
    city_id: str,
    candidates: list[dict[str, object]],
    own_probability: float | None,
) -> list[dict[str, object]]:
    if not candidates or own_probability is None:
        return []
    try:
        own_score = float(own_probability)
    except (TypeError, ValueError):
        return []
    from nextvisit.model.predict import serious_probabilities

    try:
        scores = serious_probabilities(
            city_id,
            [str(row["restaurant_id"]) for row in candidates],
        )
    except (OSError, ValueError, TypeError, KeyError):
        return []
    cleaner: list[tuple[float, dict[str, object]]] = []
    for row in candidates:
        score = scores.get(str(row["restaurant_id"]))
        if score is None or score >= own_score:
            continue
        cleaner.append((score, row))
    cleaner.sort(key=lambda item: (item[0], str(item[1].get("name") or "")))
    return [row for _score, row in cleaner]


def _with_distance(
    row: dict[str, object],
    origin_latitude: float | None,
    origin_longitude: float | None,
) -> dict[str, object]:
    latitude = _number(row.get("latitude"))
    longitude = _number(row.get("longitude"))
    measured = dict(row)
    measured["latitude"] = latitude
    measured["longitude"] = longitude
    measured["distance_miles"] = _miles(origin_latitude, origin_longitude, latitude, longitude)
    return measured


def _public_peer(row: dict[str, object]) -> dict[str, object]:
    miles = row.get("distance_miles")
    return {
        "restaurant_id": str(row["restaurant_id"]),
        "name": str(row["name"]),
        "grade": _text(row.get("grade")),
        "address": _text(row.get("address")),
        "distance_miles": None if not isinstance(miles, float) else round(miles, 2),
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
    }


def _distance_key(row: dict[str, object]) -> tuple[int, float, str]:
    miles = row.get("distance_miles")
    if not isinstance(miles, float):
        return (1, 0.0, str(row.get("name") or ""))
    return (0, miles, str(row.get("name") or ""))


def _miles(
    origin_latitude: float | None,
    origin_longitude: float | None,
    latitude: float | None,
    longitude: float | None,
) -> float | None:
    if None in (origin_latitude, origin_longitude, latitude, longitude):
        return None
    radius = 3958.7613
    start_lat = math.radians(origin_latitude)
    end_lat = math.radians(latitude)
    lat_delta = math.radians(latitude - origin_latitude)
    lng_delta = math.radians(longitude - origin_longitude)
    chord = math.sin(lat_delta / 2) ** 2 + math.cos(start_lat) * math.cos(end_lat) * math.sin(lng_delta / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(chord))


def _candidate_key(city_id: str, row: dict[str, object]) -> tuple[int, str]:
    rank = grade_rank(city_id, _text(row.get("grade")))
    return (rank if rank is not None else 99, str(row.get("name") or ""))


def apply_filters(
    frame: pl.DataFrame,
    *,
    needle: str,
    area: str,
    cuisine: str,
    grade: str,
    clean: bool,
    limit: int,
) -> pl.DataFrame:
    if needle:
        frame = frame.filter(pl.col("name_key").str.contains(needle, literal=True))
    if area:
        frame = frame.filter(pl.col("area") == area)
    if cuisine:
        frame = frame.filter(pl.col("cuisine").str.to_lowercase() == cuisine.casefold())
    if grade:
        frame = frame.filter(pl.col("grade") == grade)
    if clean:
        frame = frame.filter(pl.col("serious") == False)  # noqa: E712
    return frame.sort(["name", "restaurant_id"]).head(limit)


@lru_cache(maxsize=8)
def _directory(city_id: str) -> pl.DataFrame:
    raw_path, id_column, area_column, visits_path, grade_column, cuisine_column = _SOURCES[city_id]
    names = pl.scan_parquet(raw_path).collect_schema().names()
    columns = [id_column, "name", area_column, "inspection_date"]
    for extra in ("address", "latitude", "longitude"):
        if extra in names:
            columns.append(extra)
    raw = pl.read_parquet(raw_path, columns=columns)
    if "address" not in raw.columns:
        raw = raw.with_columns(pl.lit(None, dtype=pl.String).alias("address"))
    for coord in ("latitude", "longitude"):
        if coord not in raw.columns:
            raw = raw.with_columns(pl.lit(None, dtype=pl.Float64).alias(coord))
    listed = (
        raw.drop_nulls([id_column, "name"])
        .with_columns(pl.col(id_column).cast(pl.String))
        .sort("inspection_date")
        .group_by(id_column, maintain_order=True)
        .agg(
            pl.col("name").last(),
            pl.col(area_column).drop_nulls().last().alias("area"),
            pl.col("address").drop_nulls().last().alias("address"),
            pl.col("latitude").drop_nulls().last().alias("latitude"),
            pl.col("longitude").drop_nulls().last().alias("longitude"),
            pl.col("inspection_date").last().cast(pl.String).alias("raw_date"),
        )
        .rename({id_column: "restaurant_id"})
    )
    visits = _latest_visits(visits_path, id_column, grade_column, cuisine_column)
    if visits is None:
        listed = listed.with_columns(
            pl.lit(None, dtype=pl.String).alias("cuisine"),
            pl.lit(None, dtype=pl.String).alias("grade"),
            pl.lit(None, dtype=pl.Float64).alias("score"),
            pl.lit(None, dtype=pl.Boolean).alias("serious"),
            pl.col("raw_date").alias("last_inspection_date"),
        )
    else:
        listed = listed.join(visits, on="restaurant_id", how="left").with_columns(
            pl.coalesce(["visit_date", "raw_date"]).alias("last_inspection_date"),
            pl.coalesce(["latitude", "visit_latitude"]).alias("latitude"),
            pl.coalesce(["longitude", "visit_longitude"]).alias("longitude"),
        )
    if city_id == "austin":
        listed = listed.with_columns(
            pl.when(pl.col("score").is_null())
            .then(None)
            .when(pl.col("score") >= 90)
            .then(pl.lit("90 or above"))
            .otherwise(pl.lit("Below 90"))
            .alias("grade")
        )
    listed = listed.with_columns(pl.col("name").str.to_lowercase().alias("name_key")).select(
        [
            "restaurant_id",
            "name",
            "area",
            "address",
            "cuisine",
            "grade",
            "score",
            "serious",
            "latitude",
            "longitude",
            "last_inspection_date",
            "name_key",
        ]
    )
    return _apply_cuisines(_apply_geocodes(listed, city_id), city_id)


def _apply_geocodes(frame: pl.DataFrame, city_id: str) -> pl.DataFrame:
    """Use a geocoded address when the inspection file has no point inside the city."""
    path = Path("data/geocodes") / f"{city_id}.parquet"
    if not path.exists():
        return frame
    extra = (
        pl.read_parquet(path)
        .select(["restaurant_id", "latitude", "longitude"])
        .rename({"latitude": "geo_latitude", "longitude": "geo_longitude"})
    )
    joined = frame.join(extra, on="restaurant_id", how="left")
    south, north, west, east = _CITY_BOX[city_id]
    usable = (
        pl.col("latitude").is_between(south, north) & pl.col("longitude").is_between(west, east)
    ).fill_null(False)
    return joined.with_columns(
        pl.when(usable).then(pl.col("latitude")).otherwise(pl.col("geo_latitude")).alias("latitude"),
        pl.when(usable).then(pl.col("longitude")).otherwise(pl.col("geo_longitude")).alias("longitude"),
    ).drop(["geo_latitude", "geo_longitude"])


def _apply_cuisines(frame: pl.DataFrame, city_id: str) -> pl.DataFrame:
    """Fill a blank cuisine from the OpenStreetMap name match."""
    path = Path("data/cuisines") / f"{city_id}.parquet"
    if not path.exists() or "cuisine" not in frame.columns:
        return frame
    extra = (
        pl.read_parquet(path)
        .select(["restaurant_id", "cuisine"])
        .rename({"cuisine": "matched_cuisine"})
    )
    joined = frame.join(extra, on="restaurant_id", how="left")
    blank = pl.col("cuisine").is_null() | (pl.col("cuisine").str.strip_chars() == "")
    return joined.with_columns(
        pl.when(blank).then(pl.col("matched_cuisine")).otherwise(pl.col("cuisine")).alias("cuisine")
    ).drop("matched_cuisine")


def _latest_visits(
    path,
    id_column: str,
    grade_column: str | None,
    cuisine_column: str | None,
) -> pl.DataFrame | None:
    if not path.exists():
        return None
    names = set(pl.scan_parquet(path).collect_schema().names())
    if id_column not in names or "inspection_date" not in names:
        return None
    columns = [id_column, "inspection_date"]
    optional = [grade_column, cuisine_column, "score", "positive", "latitude", "longitude"]
    columns.extend(column for column in optional if column and column in names)
    frame = (
        pl.read_parquet(path, columns=columns)
        .drop_nulls(id_column)
        .with_columns(pl.col(id_column).cast(pl.String))
        .sort("inspection_date")
        .group_by(id_column, maintain_order=True)
        .agg(pl.all().last())
        .rename({id_column: "restaurant_id", "inspection_date": "visit_date"})
    )
    frame = frame.with_columns(pl.col("visit_date").cast(pl.String))
    if grade_column and grade_column in frame.columns and grade_column != "grade":
        frame = frame.rename({grade_column: "grade"})
    elif "grade" not in frame.columns:
        frame = frame.with_columns(pl.lit(None, dtype=pl.String).alias("grade"))
    if cuisine_column and cuisine_column in frame.columns:
        frame = frame.rename({cuisine_column: "visit_cuisine"})
    else:
        frame = frame.with_columns(pl.lit(None, dtype=pl.String).alias("visit_cuisine"))
    if "positive" in frame.columns:
        frame = frame.rename({"positive": "serious"})
    else:
        frame = frame.with_columns(pl.lit(None, dtype=pl.Boolean).alias("serious"))
    for column, dtype in (("score", pl.Float64), ("latitude", pl.Float64), ("longitude", pl.Float64)):
        if column not in frame.columns:
            frame = frame.with_columns(pl.lit(None, dtype=dtype).alias(column))
    renamed_coords = frame.rename({"latitude": "visit_latitude", "longitude": "visit_longitude"})
    return renamed_coords.select(
        [
            "restaurant_id",
            "visit_date",
            "grade",
            pl.col("visit_cuisine").alias("cuisine"),
            "score",
            "serious",
            "visit_latitude",
            "visit_longitude",
        ]
    )


def _with_cached_cuisine(frame: pl.DataFrame, city_id: str) -> pl.DataFrame:
    cached = cached_cuisines(city_id)
    if not cached:
        return frame
    extra = pl.DataFrame(
        {"restaurant_id": list(cached), "osm_cuisine": list(cached.values())},
        schema={"restaurant_id": pl.String, "osm_cuisine": pl.String},
    )
    joined = frame.join(extra, on="restaurant_id", how="left")
    return joined.with_columns(pl.coalesce(["cuisine", "osm_cuisine"]).alias("cuisine")).drop("osm_cuisine")


def _unique(frame: pl.DataFrame, column: str) -> list[str]:
    values = frame[column].drop_nulls().unique().to_list()
    return sorted(text for value in values if (text := _area(value)))


def _public_row(row: dict[str, object]) -> dict[str, object]:
    latitude, longitude = _coordinate_pair(
        row.get("latitude"),
        row.get("longitude"),
        row.get("visit_latitude"),
        row.get("visit_longitude"),
    )
    return {
        "restaurant_id": str(row["restaurant_id"]),
        "name": row.get("name"),
        "area": _area(row.get("area")),
        "address": _text(row.get("address")),
        "cuisine": _text(row.get("cuisine")),
        "grade": _text(row.get("grade")),
        "score": _number(row.get("score")),
        "serious": _bool(row.get("serious")),
        "latitude": latitude,
        "longitude": longitude,
        "last_inspection_date": _text(row.get("last_inspection_date")),
    }


def _coordinate_pair(
    latitude: object,
    longitude: object,
    visit_latitude: object,
    visit_longitude: object,
) -> tuple[float | None, float | None]:
    lat = _number(latitude) if _number(latitude) is not None else _number(visit_latitude)
    lng = _number(longitude) if _number(longitude) is not None else _number(visit_longitude)
    if lat is None or lng is None or lat == 0 or lng == 0:
        return None, None
    return lat, lng


def _area(value: object) -> str | None:
    text = _text(value)
    if text is not None and text.casefold() in {"0", "n/a", "na", "none"}:
        return None
    return text


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def _bool(value: object) -> bool | None:
    if value is None:
        return None
    return bool(value)
