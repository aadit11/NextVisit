"""Fill missing restaurant coordinates from the street address.

The Census Bureau batch geocoder accepts a US street address and returns a
longitude and latitude. OpenStreetMap is used one restaurant at a time
elsewhere; it is not used for this bulk pass.
"""

import csv
import io
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import polars as pl

from nextvisit.places import _CITY_BOX, _directory

GEOCODE_DIR = Path("data/geocodes")
_BATCH_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
_ONE_URL = "https://geocoding.geo.census.gov/geocoder/locations/address"
_BATCH_SIZE = 5_000
_DIRECTIONS = frozenset({"N", "S", "E", "W", "NE", "NW", "SE", "SW"})
_TRAILING = {"AV": "AVE", "PK": "PKWY", "WY": "WAY"}
_BOSTON_NEIGHBORHOODS = frozenset(
    {
        "ALLSTON",
        "BACK BAY",
        "BEACON HILL",
        "BRIGHTON",
        "CHARLESTOWN",
        "CHINATOWN",
        "DORCHESTER",
        "EAST BOSTON",
        "FENWAY",
        "HYDE PARK",
        "JAMAICA PLAIN",
        "MATTAPAN",
        "MISSION HILL",
        "NORTH END",
        "ROSLINDALE",
        "ROXBURY",
        "SOUTH BOSTON",
        "SOUTH END",
        "WEST END",
        "WEST ROXBURY",
    }
)
_UNIT = re.compile(
    r"(?:#|\b(?:STE|SUITE|APT|APARTMENT|UNIT|BLDG|BUILDING|FL|FLOOR|RM|ROOM|TRLR|SPC|DEPT)\b).*$",
    re.IGNORECASE,
)
_RANGE = re.compile(r"^(\d+)\s*-\s*\d+\b")
_REPEATED_WORD = re.compile(r"\b([A-Za-z]+)\s+\1\b", re.IGNORECASE)
_STATES = {
    "new_york": "NY",
    "chicago": "IL",
    "king_county": "WA",
    "los_angeles": "CA",
    "boston": "MA",
    "san_francisco": "CA",
    "austin": "TX",
}
_BOROUGHS = {
    "MANHATTAN": "New York",
    "BROOKLYN": "Brooklyn",
    "BRONX": "Bronx",
    "QUEENS": "Queens",
    "STATEN ISLAND": "Staten Island",
}
_SUFFIXES = frozenset(
    {
        "ST",
        "STREET",
        "AVE",
        "AVENUE",
        "RD",
        "ROAD",
        "BLVD",
        "DR",
        "DRIVE",
        "LN",
        "LANE",
        "WAY",
        "PL",
        "PLACE",
        "CT",
        "COURT",
        "HWY",
        "HIGHWAY",
        "PKWY",
        "CIR",
        "CIRCLE",
        "TER",
        "TERRACE",
        "NE",
        "NW",
        "SE",
        "SW",
        "EB",
        "WB",
        "N",
        "S",
        "E",
        "W",
        "STE",
        "SUITE",
        "BLDG",
        "APT",
        "UNIT",
        "FL",
        "FLOOR",
    }
)


def parse_address(address: str, *, default_state: str) -> tuple[str, str, str, str] | None:
    """Split a stored address into street, city, state, and ZIP."""
    text = " ".join(address.replace("/", " ").split())
    while "(" in text and ")" in text:
        start, end = text.find("("), text.find(")")
        if end < start:
            break
        text = " ".join(f"{text[:start]} {text[end + 1:]}".split())
    parts = [part.strip(" ,") for part in text.split(",") if part.strip(" ,")]
    if not parts:
        return None
    state, zip_code, remainder = _state_and_zip(parts[-1])
    if len(parts) >= 3:
        street, city = parts[0], parts[1]
    elif len(parts) == 2:
        street, city = _split_street_city(parts[0])
        if remainder and not city:
            city = remainder
    else:
        street, city = _split_street_city(remainder or parts[0])
    street = " ".join(street.split())
    city = _BOROUGHS.get(city.upper(), city)
    state = state or default_state
    if len(street) < 2 or len(state) != 2:
        return None
    return street[:100], city, state, zip_code


def tidy_address(parsed: tuple[str, str, str, str]) -> tuple[str, str, str, str]:
    """Rewrite an address into the form the Census geocoder is more likely to match."""
    street, city, state, zip_code = parsed
    street = _RANGE.sub(r"\1", _UNIT.sub("", street))
    previous = None
    while previous != street:
        previous = street
        street = _REPEATED_WORD.sub(r"\1", street)
    tokens = street.split()
    if tokens and tokens[-1].upper() in _TRAILING:
        tokens[-1] = _TRAILING[tokens[-1].upper()]
    street = " ".join(tokens).strip(" ,")
    if state == "MA" and city.upper() in _BOSTON_NEIGHBORHOODS:
        city = "Boston"
    return street[:100], city, state, zip_code


def geocode_missing() -> dict[str, tuple[int, int]]:
    """Geocode every restaurant whose coordinate is missing or outside its city."""
    counts: dict[str, tuple[int, int]] = {}
    for city_id in _STATES:
        counts[city_id] = _geocode_city(city_id)
        _directory.cache_clear()
    return counts


def _geocode_city(city_id: str) -> tuple[int, int]:
    missing = _missing(city_id)
    if not missing:
        print(f"{city_id}: nothing to geocode", flush=True)
        return 0, 0
    by_address: dict[tuple[str, str, str, str], list[str]] = {}
    skipped = 0
    for restaurant_id, address in missing:
        parsed = parse_address(address, default_state=_STATES[city_id])
        if parsed is None:
            skipped += 1
            continue
        by_address.setdefault(tidy_address(parsed), []).append(restaurant_id)
    print(
        f"{city_id}: {len(missing)} missing, {len(by_address)} distinct addresses, {skipped} unreadable",
        flush=True,
    )
    found: dict[str, tuple[float, float]] = {}
    addresses = list(by_address)
    for start in range(0, len(addresses), _BATCH_SIZE):
        chunk = addresses[start : start + _BATCH_SIZE]
        try:
            located, ties = _census_batch(chunk)
        except RuntimeError as exc:
            print(f"{city_id}: batch {start // _BATCH_SIZE + 1} failed: {exc}", flush=True)
            continue
        resolved = _resolve_ties(chunk, ties, city_id)
        located.update(resolved)
        for index, point in located.items():
            for restaurant_id in by_address[chunk[index]]:
                found[restaurant_id] = point
        _write(city_id, found)
        print(
            f"{city_id}: batch {start // _BATCH_SIZE + 1} matched {len(located)} of {len(chunk)}"
            f" ({len(resolved)} of {len(ties)} ties)",
            flush=True,
        )
    print(f"{city_id}: {len(found)} restaurants geocoded", flush=True)
    return len(missing), len(found)


def _missing(city_id: str) -> list[tuple[str, str]]:
    south, north, west, east = _CITY_BOX[city_id]
    frame = _directory(city_id)
    usable = (
        pl.col("latitude").is_between(south, north) & pl.col("longitude").is_between(west, east)
    ).fill_null(False)
    missing = frame.filter(~usable & pl.col("address").is_not_null())
    return [
        (str(row["restaurant_id"]), str(row["address"]))
        for row in missing.select(["restaurant_id", "address"]).iter_rows(named=True)
        if str(row["address"]).strip()
    ]


def _census_batch(
    addresses: list[tuple[str, str, str, str]],
) -> tuple[dict[int, tuple[float, float]], list[int]]:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for index, (street, city, state, zip_code) in enumerate(addresses):
        writer.writerow([index, street, city, state, zip_code])
    payload = buffer.getvalue()
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            response = httpx.post(
                _BATCH_URL,
                data={"benchmark": "Public_AR_Current", "vintage": "Current_Current"},
                files={"addressFile": ("addresses.csv", payload, "text/csv")},
                headers={"User-Agent": "Nextvisit/0.1 (local restaurant inspection viewer)"},
                timeout=300,
            )
            response.raise_for_status()
            return _read_matches(response.text)
        except (httpx.HTTPError, csv.Error, ValueError) as exc:
            last_error = exc
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("Census geocoder failed after retries.") from last_error


def _read_matches(body: str) -> tuple[dict[int, tuple[float, float]], list[int]]:
    found: dict[int, tuple[float, float]] = {}
    ties: list[int] = []
    for row in csv.reader(io.StringIO(body)):
        if len(row) < 3 or row[2] not in {"Match", "Tie"}:
            continue
        try:
            index = int(row[0])
        except ValueError:
            continue
        point = _point(row)
        if point is None:
            if row[2] == "Tie":
                ties.append(index)
            continue
        matched = row[4] if len(row) > 4 else ""
        if not _direction_ok(row[1], matched):
            continue
        found[index] = point
    return found, ties


def _resolve_ties(
    addresses: list[tuple[str, str, str, str]],
    indexes: list[int],
    city_id: str,
) -> dict[int, tuple[float, float]]:
    """A batch tie has no coordinate. The one-address lookup returns the candidates."""
    if not indexes:
        return {}
    south, north, west, east = _CITY_BOX[city_id]

    def one(index: int) -> tuple[int, tuple[float, float] | None]:
        street, city, state, zip_code = addresses[index]
        try:
            response = httpx.get(
                _ONE_URL,
                params={
                    "street": street,
                    "city": city,
                    "state": state,
                    "zip": zip_code,
                    "benchmark": "Public_AR_Current",
                    "format": "json",
                },
                headers={"User-Agent": "Nextvisit/0.1 (local restaurant inspection viewer)"},
                timeout=30,
            )
            response.raise_for_status()
            matches = response.json()["result"]["addressMatches"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return index, None
        points: list[tuple[float, float]] = []
        for match in matches:
            coordinates = match.get("coordinates") or {}
            try:
                latitude, longitude = float(coordinates["y"]), float(coordinates["x"])
            except (KeyError, TypeError, ValueError):
                continue
            matched = str(match.get("matchedAddress") or "")
            if not (south <= latitude <= north and west <= longitude <= east):
                continue
            if latitude == 0 or longitude == 0:
                continue
            if not _direction_ok(street, matched) or not _number_ok(street, matched):
                continue
            points.append((latitude, longitude))
        if not points or _spread(points) > 0.02:
            return index, None
        return index, points[0]

    found: dict[int, tuple[float, float]] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for index, point in pool.map(one, indexes):
            if point is not None:
                found[index] = point
    return found


def _point(row: list[str]) -> tuple[float, float] | None:
    if len(row) < 6 or "," not in row[5]:
        return None
    try:
        longitude_text, latitude_text = row[5].split(",")
        longitude, latitude = float(longitude_text), float(latitude_text)
    except (TypeError, ValueError):
        return None
    if -90 <= latitude <= 90 and -180 <= longitude <= 180 and latitude != 0 and longitude != 0:
        return latitude, longitude
    return None


def _direction(text: str) -> str:
    tokens = [token.strip(",") for token in text.upper().split()]
    for token in tokens[1:4]:
        if token in _DIRECTIONS:
            return token
    return ""


def _direction_ok(query: str, matched: str) -> bool:
    """Reject a match that flips the street from east to west, or north to south."""
    wanted = _direction(query)
    got = _direction(matched)
    return not wanted or not got or wanted == got


def _number_ok(query: str, matched: str) -> bool:
    wanted = _house_number(query)
    got = _house_number(matched)
    return not wanted or wanted == got


def _house_number(text: str) -> str:
    tokens = text.split()
    if not tokens:
        return ""
    digits: list[str] = []
    for char in tokens[0].strip(","):
        if not char.isdigit():
            break
        digits.append(char)
    return "".join(digits)


def _spread(points: list[tuple[float, float]]) -> float:
    latitudes = [point[0] for point in points]
    longitudes = [point[1] for point in points]
    return max(max(latitudes) - min(latitudes), max(longitudes) - min(longitudes))


def _write(city_id: str, found: dict[str, tuple[float, float]]) -> None:
    if not found:
        return
    GEOCODE_DIR.mkdir(parents=True, exist_ok=True)
    path = GEOCODE_DIR / f"{city_id}.parquet"
    fresh = pl.DataFrame(
        {
            "restaurant_id": list(found),
            "latitude": [point[0] for point in found.values()],
            "longitude": [point[1] for point in found.values()],
        },
        schema={"restaurant_id": pl.String, "latitude": pl.Float64, "longitude": pl.Float64},
    )
    if path.exists():
        kept = pl.read_parquet(path).join(fresh.select("restaurant_id"), on="restaurant_id", how="anti")
        fresh = pl.concat([kept, fresh], how="vertical")
    temporary = path.with_suffix(".tmp")
    fresh.write_parquet(temporary)
    temporary.replace(path)


def _state_and_zip(tail: str) -> tuple[str, str, str]:
    tokens = tail.split()
    zip_code = ""
    state = ""
    if tokens and tokens[-1][:5].isdigit() and len(tokens[-1]) >= 5:
        zip_code = tokens[-1][:5]
        tokens = tokens[:-1]
    if tokens and len(tokens[-1]) == 2 and tokens[-1].isalpha():
        state = tokens[-1].upper()
        tokens = tokens[:-1]
    return state, zip_code, " ".join(tokens)


def _split_street_city(text: str) -> tuple[str, str]:
    tokens = text.split()
    if len(tokens) >= 2 and tokens[-1].isalpha() and tokens[-1].upper() not in _SUFFIXES:
        return " ".join(tokens[:-1]), tokens[-1]
    return text, ""
