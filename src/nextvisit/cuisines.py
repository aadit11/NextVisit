"""Match inspection restaurants to an OpenStreetMap cuisine.

Only New York publishes a cuisine. The other cities leave that column empty,
so the diner filter and the card eyebrow have nothing to show. This pass asks
OpenStreetMap for places that carry a cuisine tag inside the city box and
keeps a match when the name agrees and the point is nearby.
"""

import math
import re
import time
from pathlib import Path

import httpx
import polars as pl

from nextvisit.places import _CITY_BOX, _directory

CUISINE_DIR = Path("data/cuisines")
_OVERPASS = "https://overpass-api.de/api/interpreter"
_SKIP = frozenset({"yes", "no", "food", "restaurant"})
_MAX_KM = 0.4
_PREFIX_KM = 0.25
_PREFIX_CHARS = 6
_NAME_CUISINES: tuple[tuple[str, str], ...] = (
    (r"\b(mcdonald|wendy|whataburger|five guy|in n out|sonic|burger king)\b", "Burger"),
    (r"\b(subway|jersey mike|jimmy john|firehouse|arby|quizno)\b", "Sandwiches"),
    (r"\b(starbucks|dunkin)\b", "Coffee"),
    (r"\b(kfc|popeye|raising cane|wingstop|buffalo wild|chick fil a|el pollo)\b", "Chicken"),
    (r"\b(taco bell|qdoba|del taco|taco cabana|chipotle)\b", "Mexican"),
    (r"\bpanda express\b", "Chinese"),
    (r"\b(pizza hut|domino|papa john|little caesar)\b", "Pizza"),
    (r"\bolive garden\b", "Italian"),
    (r"\bpanera\b", "Bakery"),
    (r"\b(ihop|denny|waffle house)\b", "Breakfast"),
    (r"\bpizz", "Pizza"),
    (r"\bsushi\b", "Sushi"),
    (r"\bramen\b", "Ramen"),
    (r"\bpho\b", "Vietnamese"),
    (r"\bthai\b", "Thai"),
    (r"\b(mexican|taqueria|tortilleria|pupuseria|cantina|tacos?)\b", "Mexican"),
    (r"\b(chinese|china)\b", "Chinese"),
    (r"\b(japanese|hibachi|tokyo|osaka|kyoto)\b", "Japanese"),
    (r"\bkorean\b", "Korean"),
    (r"\bvietnamese\b", "Vietnamese"),
    (r"\bindian\b", "Indian"),
    (r"\b(greek|gyro)\b", "Greek"),
    (r"\bitalian\b", "Italian"),
    (r"\bfrench\b", "French"),
    (r"\bmediterranean\b", "Mediterranean"),
    (r"\b(bbq|barbecue|barbeque)\b", "Barbecue"),
    (r"\bseafood\b", "Seafood"),
    (r"\b(steakhouse|steak)\b", "Steak"),
    (r"\b(bakery|bagel)\b", "Bakery"),
    (r"\b(donuts?|doughnuts?)\b", "Donuts"),
    (r"\b(coffee|espresso)\b", "Coffee"),
    (r"\bcafes?\b", "Cafe"),
    (r"\b(hamburgers?|burgers?)\b", "Burger"),
    (r"\b(ice cream|gelato)\b", "Ice Cream"),
    (r"\b(sandwich|sandwiches)\b", "Sandwiches"),
    (r"\b(wings?|chickens?)\b", "Chicken"),
    (r"\b(diner|waffle|pancake|breakfast)\b", "Breakfast"),
    (r"\b(noodle|noodles)\b", "Noodles"),
    (r"\bpoke\b", "Poke"),
    (r"\b(deli|delicatessen)\b", "Deli"),
)
_DROPPED_WORDS = frozenset(
    {"restaurant", "restaurants", "cafe", "cafes", "llc", "inc", "co", "the", "and"}
)


def tidy_cuisine(value: object) -> str | None:
    """The diner filter lists one cuisine, so a tag like pizza;italian keeps Pizza."""
    if not isinstance(value, str):
        return None
    labels: list[str] = []
    for piece in re.split(r"[;,]", value):
        words = [
            "-".join(part.capitalize() for part in word.split("-"))
            for word in piece.replace("_", " ").split()
            if word
        ]
        label = " ".join(words)
        if label.casefold() in _SKIP or label in labels:
            continue
        if label:
            labels.append(label)
    return labels[0] if labels else None


def match_city(city_id: str, client: httpx.Client | None = None) -> tuple[int, int]:
    """Write cuisine matches for one city. Returns (restaurants, matches)."""
    frame = _directory(city_id)
    places = _load_or_fetch(city_id, client)
    rows = _match(frame, places)
    print(f"{city_id}: {len(places)} OpenStreetMap places carry a cuisine tag", flush=True)
    CUISINE_DIR.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows, schema={"restaurant_id": pl.String, "cuisine": pl.String}).write_parquet(
        CUISINE_DIR / f"{city_id}.parquet"
    )
    return frame.height, len(rows)


def _load_or_fetch(city_id: str, client: httpx.Client | None) -> list[dict[str, object]]:
    path = CUISINE_DIR / f"{city_id}_osm.parquet"
    if path.exists():
        return pl.read_parquet(path).to_dicts()
    places = _overpass_cuisines(city_id, client)
    if places:
        CUISINE_DIR.mkdir(parents=True, exist_ok=True)
        pl.DataFrame(places).write_parquet(path)
    return places


def _overpass_cuisines(city_id: str, client: httpx.Client | None) -> list[dict[str, object]]:
    south, north, west, east = _CITY_BOX[city_id]
    own_client = client is None
    http = client or httpx.Client(timeout=120, headers={"User-Agent": "nextvisit/1.0"})
    found: list[dict[str, object]] = []
    try:
        for box in _tiles(south, north, west, east):
            try:
                found.extend(_query_box(http, box))
            except (httpx.HTTPError, RuntimeError) as error:
                print(f"{city_id}: skipped a map tile ({error})", flush=True)
            time.sleep(1)
    finally:
        if own_client:
            http.close()
    return found


def _tiles(
    south: float, north: float, west: float, east: float, step: float = 0.4
) -> list[tuple[float, float, float, float]]:
    """Split a city box into pieces small enough for one map query."""
    boxes: list[tuple[float, float, float, float]] = []
    lat = south
    while lat < north - 1e-9:
        next_lat = min(north, lat + step)
        lon = west
        while lon < east - 1e-9:
            next_lon = min(east, lon + step)
            boxes.append((lat, next_lat, lon, next_lon))
            lon = next_lon
        lat = next_lat
    return boxes


def _query_box(client: httpx.Client, box: tuple[float, float, float, float]) -> list[dict[str, object]]:
    south, north, west, east = box
    query = (
        f"[out:json][timeout:80];("
        f'node["cuisine"]({south},{west},{north},{east});'
        f'way["cuisine"]({south},{west},{north},{east});'
        f");out tags center;"
    )
    response = _post(client, query)
    places: list[dict[str, object]] = []
    for element in response.json().get("elements", []):
        tags = element.get("tags") or {}
        cuisine = tidy_cuisine(tags.get("cuisine"))
        name = tags.get("name")
        latitude = element.get("lat", (element.get("center") or {}).get("lat"))
        longitude = element.get("lon", (element.get("center") or {}).get("lon"))
        if cuisine and isinstance(name, str) and latitude is not None and longitude is not None:
            places.append(
                {
                    "name_key": _name_key(name),
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    "cuisine": cuisine,
                }
            )
    return places


def _match(frame: pl.DataFrame, places: list[dict[str, object]]) -> list[dict[str, str]]:
    by_name: dict[str, list[dict[str, object]]] = {}
    for place in places:
        by_name.setdefault(str(place["name_key"]), []).append(place)
    rows: list[dict[str, str]] = []
    for record in frame.select(["restaurant_id", "name", "latitude", "longitude"]).iter_rows(named=True):
        name = record.get("name")
        if not isinstance(name, str):
            continue
        key = _name_key(name)
        exact = by_name.get(key, [])
        if exact:
            chosen = _closest(record.get("latitude"), record.get("longitude"), exact, _MAX_KM)
        else:
            chosen = _closest(
                record.get("latitude"),
                record.get("longitude"),
                _prefix_candidates(key, by_name),
                _PREFIX_KM,
            )
        chosen = chosen or cuisine_from_name(name)
        if chosen is not None:
            rows.append(
                {
                    "restaurant_id": str(record["restaurant_id"]),
                    "cuisine": str(chosen).split(",")[0].strip(),
                }
            )
    return rows


def _closest(
    latitude: object,
    longitude: object,
    candidates: list[dict[str, object]],
    limit_km: float,
) -> str | None:
    if not candidates or not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        return None
    best: tuple[float, str] | None = None
    for place in candidates:
        distance = _km(float(latitude), float(longitude), float(place["latitude"]), float(place["longitude"]))
        if distance <= limit_km and (best is None or distance < best[0]):
            best = (distance, str(place["cuisine"]))
    return None if best is None else best[1]


def _post(client: httpx.Client, query: str) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = client.post(_OVERPASS, data={"data": query})
            if response.status_code in {429, 502, 504}:
                time.sleep(5 * (attempt + 1))
                continue
            response.raise_for_status()
            return response
        except httpx.HTTPError as error:
            last_error = error
            time.sleep(5 * (attempt + 1))
    if last_error is not None:
        raise last_error
    raise RuntimeError("OpenStreetMap did not return a cuisine list")


def cuisine_from_name(name: str) -> str | None:
    """Read a cuisine from a name when the words themselves say what it serves."""
    text = re.sub(r"[^a-z0-9]+", " ", name.casefold())
    key = re.sub(r"\s+\d+$", "", text).strip()
    for pattern, label in _NAME_CUISINES:
        if re.search(pattern, key):
            return label
    return None


def _prefix_candidates(key: str, by_name: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for other, places in by_name.items():
        shorter, longer = (other, key) if len(other) <= len(key) else (key, other)
        if len(shorter) < _PREFIX_CHARS or not longer.startswith(shorter + " "):
            continue
        found.extend(places)
    return found


def _name_key(name: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", name.casefold())
    text = re.sub(r"\s+\d+$", "", text).strip()
    words = [word for word in text.split() if word not in _DROPPED_WORDS]
    return " ".join(words)


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = (lat1 - lat2) * 111.0
    dlon = (lon1 - lon2) * 111.0 * math.cos(math.radians(lat1))
    return math.hypot(dlat, dlon)
