"""Hours and cuisine from OpenStreetMap when the city file does not publish them."""

import os
import sqlite3

import httpx

from nextvisit.accounts import connect, database_path

_EMPTY = {"cuisine": None, "hours": None, "latitude": None, "longitude": None}


def cached_cuisines(city_id: str) -> dict[str, str]:
    if not database_path().exists():
        return {}
    with connect() as connection:
        rows = connection.execute(
            "SELECT restaurant_id, cuisine FROM osm_cache WHERE city_id = ? AND cuisine IS NOT NULL",
            (city_id,),
        ).fetchall()
    return {row["restaurant_id"]: row["cuisine"] for row in rows}


def place_facts(
    city_id: str,
    restaurant_id: str,
    name: str | None,
    address: str | None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict[str, object]:
    """Return cached OpenStreetMap facts, fetching once when this place is new."""
    if "PYTEST_CURRENT_TEST" in os.environ:
        return dict(_EMPTY)
    cached = _read(city_id, restaurant_id)
    if cached is not None:
        return cached
    found = _fetch(name, address, latitude, longitude)
    if found is None:
        return dict(_EMPTY)
    _write(city_id, restaurant_id, found)
    return found


def _read(city_id: str, restaurant_id: str) -> dict[str, object] | None:
    if not database_path().exists():
        return None
    with connect() as connection:
        row = connection.execute(
            """
            SELECT cuisine, hours, latitude, longitude
            FROM osm_cache
            WHERE city_id = ? AND restaurant_id = ?
            """,
            (city_id, restaurant_id),
        ).fetchone()
    if row is None or all(row[name] is None for name in ("cuisine", "hours", "latitude", "longitude")):
        return None
    return _row(row)


def _write(city_id: str, restaurant_id: str, facts: dict[str, object]) -> None:
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO osm_cache (city_id, restaurant_id, cuisine, hours, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(city_id, restaurant_id) DO UPDATE SET
                cuisine = excluded.cuisine,
                hours = excluded.hours,
                latitude = excluded.latitude,
                longitude = excluded.longitude
            """,
            (
                city_id,
                restaurant_id,
                facts.get("cuisine"),
                facts.get("hours"),
                facts.get("latitude"),
                facts.get("longitude"),
            ),
        )


def _fetch(
    name: str | None,
    address: str | None,
    latitude: float | None,
    longitude: float | None,
) -> dict[str, object] | None:
    if latitude is not None and longitude is not None:
        nearby = _overpass(name, latitude, longitude)
        if nearby is not None:
            return nearby
    query = ", ".join(part for part in (name, address) if part)
    if len(query) < 3:
        return _miss(latitude, longitude)
    try:
        response = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query[:240], "format": "jsonv2", "limit": "1", "extratags": "1"},
            headers={"User-Agent": "Nextvisit/0.1 (local restaurant inspection viewer)"},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    if not isinstance(payload, list) or not payload:
        return _miss(latitude, longitude)
    hit = payload[0]
    if not isinstance(hit, dict):
        return _miss(latitude, longitude)
    tags = hit.get("extratags") if isinstance(hit.get("extratags"), dict) else {}
    return {
        "cuisine": _text(tags.get("cuisine")),
        "hours": _text(tags.get("opening_hours")),
        "latitude": _float(hit.get("lat")),
        "longitude": _float(hit.get("lon")),
    }


def _overpass(name: str | None, latitude: float, longitude: float) -> dict[str, object] | None:
    query = (
        f'[out:json][timeout:8];nwr(around:120,{latitude},{longitude})["name"];out tags center 20;'
    )
    try:
        response = httpx.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            headers={"User-Agent": "Nextvisit/0.1 (local restaurant inspection viewer)"},
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    elements = payload.get("elements") if isinstance(payload, dict) else None
    if not isinstance(elements, list):
        return _miss(latitude, longitude)
    wanted = (name or "").casefold()
    chosen: dict[str, object] | None = None
    for element in elements:
        if not isinstance(element, dict):
            continue
        tags = element.get("tags") if isinstance(element.get("tags"), dict) else {}
        label = _text(tags.get("name")) or ""
        if wanted and wanted not in label.casefold() and label.casefold() not in wanted:
            continue
        center = element.get("center") if isinstance(element.get("center"), dict) else {}
        chosen = {
            "cuisine": _text(tags.get("cuisine")),
            "hours": _text(tags.get("opening_hours")),
            "latitude": _float(element.get("lat") or center.get("lat")) or latitude,
            "longitude": _float(element.get("lon") or center.get("lon")) or longitude,
        }
        if chosen["hours"] or chosen["cuisine"]:
            return chosen
    return chosen if chosen is not None else _miss(latitude, longitude)


def _miss(latitude: float | None, longitude: float | None) -> dict[str, object]:
    return {"cuisine": "", "hours": "", "latitude": latitude, "longitude": longitude}


def _row(row: sqlite3.Row) -> dict[str, object]:
    return {
        "cuisine": _text(row["cuisine"]),
        "hours": _text(row["hours"]),
        "latitude": row["latitude"],
        "longitude": row["longitude"],
    }


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text or None


def _float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
