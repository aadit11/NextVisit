"""Lookup API. New York scores from the saved model. Other cities are not trained."""

import os
from functools import lru_cache

import polars as pl
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from nextvisit import accounts
from nextvisit.api.schemas import (
    AccountIn,
    AccountOut,
    FacetsOut,
    LoginIn,
    MapPlaceOut,
    RestaurantHit,
    RestaurantOut,
    ReviewIn,
    ReviewListOut,
)
from nextvisit.osm import place_facts
from nextvisit.places import facets as place_facets
from nextvisit.places import map_points as place_map_points
from nextvisit.places import one as place_one
from nextvisit.places import nearby_places, peer_comparison
from nextvisit.places import search_restaurants
from nextvisit.cities import CITIES, get_city
from nextvisit.brief.history import assemble, render_account, render_summary
from nextvisit.download import load_env
from nextvisit.model.predict import (
    UnknownRestaurant,
    predict_austin,
    predict_boston,
    predict_chicago,
    predict_king_county,
    predict_los_angeles,
    predict_new_york,
    predict_san_francisco,
)
from nextvisit.prepare.boston import CODEBOOK_PATH as BOSTON_CODEBOOK_PATH
from nextvisit.prepare.chicago import CODEBOOK_PATH as CHICAGO_CODEBOOK_PATH
from nextvisit.prepare.collapse import CODEBOOK_PATH
from nextvisit.prepare.king_county import CODEBOOK_PATH as KING_COUNTY_CODEBOOK_PATH
from nextvisit.prepare.los_angeles import CODEBOOK_PATH as LOS_ANGELES_CODEBOOK_PATH
from nextvisit.prepare.san_francisco import CODEBOOK_PATH as SAN_FRANCISCO_CODEBOOK_PATH

load_env()


def _allowed_origins() -> list[str]:
    raw = os.environ.get("NEXTVISIT_ALLOWED_ORIGINS", "*").strip()
    if not raw or raw == "*":
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(title="Nextvisit")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/cities")
def list_cities() -> list[dict[str, object]]:
    return [
        {
            "id": spec.id,
            "name": spec.name,
            "label": spec.label,
        }
        for spec in CITIES.values()
    ]


@app.post("/account/register", response_model=AccountOut)
def register_account(body: AccountIn) -> AccountOut:
    try:
        return AccountOut.model_validate(accounts.register(body.name, body.email, body.password))
    except ValueError as exc:
        status = 409 if "already exists" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@app.post("/account/login", response_model=AccountOut)
def login_account(body: LoginIn) -> AccountOut:
    try:
        return AccountOut.model_validate(accounts.login(body.email, body.password))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.get("/account/me", response_model=AccountOut)
def current_account(authorization: str | None = Header(default=None)) -> AccountOut:
    user = _user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Log in to continue.")
    return AccountOut(token=_bearer(authorization), name=str(user["name"]), email=str(user["email"]))


@app.get("/cities/{city_id}/facets", response_model=FacetsOut)
def city_facets(city_id: str) -> FacetsOut:
    spec = _spec_or_404(city_id)
    try:
        return FacetsOut.model_validate(place_facets(spec.id))
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=501, detail=f"No restaurant list for {spec.name} is on disk.") from exc


@app.get("/cities/{city_id}/map", response_model=list[MapPlaceOut])
def city_map(city_id: str) -> list[MapPlaceOut]:
    spec = _spec_or_404(city_id)
    try:
        points = place_map_points(spec.id)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=501, detail=f"No restaurant list for {spec.name} is on disk.") from exc
    return [
        MapPlaceOut.model_validate(
            {
                "restaurant_id": point["restaurant_id"],
                "name": point["name"],
                "latitude": round(float(point["latitude"]), 5),
                "longitude": round(float(point["longitude"]), 5),
            }
        )
        for point in points
    ]


@app.get("/cities/{city_id}/restaurants", response_model=list[RestaurantHit])
def find_restaurants(
    city_id: str,
    q: str = "",
    area: str = "",
    cuisine: str = "",
    grade: str = "",
    clean: bool = False,
) -> list[RestaurantHit]:
    spec = _spec_or_404(city_id)
    try:
        hits = search_restaurants(
            spec.id,
            q,
            area=area,
            cuisine=cuisine,
            grade=grade,
            clean=clean,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=501,
            detail=f"No restaurant list for {spec.name} is on disk.",
        ) from exc
    return [RestaurantHit.model_validate(hit) for hit in hits]


@app.get("/cities/{city_id}/restaurants/{restaurant_id}/reviews", response_model=ReviewListOut)
def list_reviews(
    city_id: str,
    restaurant_id: str,
    authorization: str | None = Header(default=None),
) -> ReviewListOut:
    spec = _spec_or_404(city_id)
    _known_restaurant(spec.id, restaurant_id, spec.name)
    user = _user(authorization)
    user_id = int(user["id"]) if user else None
    return ReviewListOut.model_validate(accounts.reviews_for(spec.id, restaurant_id, user_id))


@app.post("/cities/{city_id}/restaurants/{restaurant_id}/reviews", response_model=ReviewListOut)
def write_review(
    city_id: str,
    restaurant_id: str,
    body: ReviewIn,
    authorization: str | None = Header(default=None),
) -> ReviewListOut:
    spec = _spec_or_404(city_id)
    user = _user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Log in to write a review.")
    _known_restaurant(spec.id, restaurant_id, spec.name)
    try:
        accounts.save_review(spec.id, restaurant_id, int(user["id"]), body.stars, body.comment)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ReviewListOut.model_validate(accounts.reviews_for(spec.id, restaurant_id, int(user["id"])))


@app.get("/cities/{city_id}/restaurants/{restaurant_id}", response_model=RestaurantOut)
def get_restaurant(city_id: str, restaurant_id: str) -> RestaurantOut:
    try:
        spec = get_city(city_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    predict = _PREDICTORS.get(spec.id)
    if predict is None:
        raise HTTPException(
            status_code=501,
            detail=f"No trained model for {spec.name} yet. Restaurant {restaurant_id} was not scored.",
        )
    try:
        payload = predict(restaurant_id)
    except UnknownRestaurant as exc:
        raise HTTPException(
            status_code=404,
            detail=f"No {spec.name} restaurant {restaurant_id}.",
        ) from exc
    enriched = _attach_codes(payload)
    _attach_place(enriched)
    _attach_history(enriched)
    return RestaurantOut.model_validate(enriched)


def _attach_codes(payload: dict[str, object]) -> dict[str, object]:
    city_id = str(payload["city"])
    raw_codes = payload.get("codes")
    codes = [code for code in raw_codes if isinstance(code, str)] if isinstance(raw_codes, list) else []
    codebook = _codebook_or_empty(city_id)
    payload["codes"] = [
        {"code": code, "description": codebook.get(code)}
        for code in codes
    ]
    return payload


def _attach_place(payload: dict[str, object]) -> None:
    city_id = str(payload["city"])
    restaurant_id = str(payload["restaurant_id"])
    try:
        info = place_one(city_id, restaurant_id)
    except OSError:
        info = None
    if info:
        for key in ("address", "grade", "score", "last_inspection_date", "serious", "latitude", "longitude", "area"):
            if payload.get(key) in (None, "") and info.get(key) is not None:
                payload[key] = info[key]
        if not payload.get("cuisine") and info.get("cuisine"):
            payload["cuisine"] = info["cuisine"]
    average, count = accounts.stats_for(city_id, [restaurant_id]).get(restaurant_id, (None, 0))
    payload["average_stars"] = average
    payload["review_count"] = count
    name = payload.get("name") if isinstance(payload.get("name"), str) else None
    address = payload.get("address") if isinstance(payload.get("address"), str) else None
    latitude = payload.get("latitude") if isinstance(payload.get("latitude"), (int, float)) else None
    longitude = payload.get("longitude") if isinstance(payload.get("longitude"), (int, float)) else None
    facts = place_facts(city_id, restaurant_id, name, address, latitude, longitude)
    if not payload.get("cuisine") and facts.get("cuisine"):
        payload["cuisine"] = facts["cuisine"]
    payload["hours"] = facts.get("hours")
    if payload.get("latitude") is None and facts.get("latitude") is not None:
        payload["latitude"] = facts["latitude"]
        payload["longitude"] = facts["longitude"]
    area = payload.get("area") if isinstance(payload.get("area"), str) else None
    cuisine = payload.get("cuisine") if isinstance(payload.get("cuisine"), str) else None
    grade = payload.get("grade") if isinstance(payload.get("grade"), str) else None
    try:
        payload.update(
            peer_comparison(city_id, restaurant_id, area=area, cuisine=cuisine, grade=grade)
        )
    except OSError:
        payload["peer_count"] = 0
        payload["peer_graded_count"] = 0
        payload["peer_standing"] = None
    own = payload.get("probability") if payload.get("abstained") is False else None
    origin_lat = payload.get("latitude") if isinstance(payload.get("latitude"), (int, float)) else None
    origin_lng = payload.get("longitude") if isinstance(payload.get("longitude"), (int, float)) else None
    own_score = payload.get("score")
    own_serious = payload.get("serious")
    try:
        payload.update(
            nearby_places(
                city_id,
                restaurant_id,
                area=area,
                cuisine=cuisine,
                own_probability=own if isinstance(own, (int, float)) and not isinstance(own, bool) else None,
                origin_latitude=None if isinstance(origin_lat, bool) else origin_lat,
                origin_longitude=None if isinstance(origin_lng, bool) else origin_lng,
                own_grade=grade,
                own_score=None if isinstance(own_score, bool) or not isinstance(own_score, (int, float)) else float(own_score),
                own_serious=own_serious if isinstance(own_serious, bool) else None,
            )
        )
    except OSError:
        payload["nearby_basis"] = None
        payload["cleaner_peers"] = []


def _attach_history(payload: dict[str, object]) -> None:
    city_id = str(payload["city"])
    raw_visits = payload.get("visits")
    visits = [item for item in raw_visits if isinstance(item, dict)] if isinstance(raw_visits, list) else []
    facts = assemble(
        city_id,
        visits,
        _codebook_or_empty(city_id),
        score_trend=_text(payload.get("score_trend")),
    )
    payload["visits"] = [
        {
            "date": visit.date,
            "grade": visit.grade,
            "score": visit.score,
            "codes": [{"code": code, "description": text} for code, text in visit.codes],
        }
        for visit in facts.visits
    ]
    payload["earlier_inspections"] = facts.earlier_count
    payload["code_summary"] = render_summary(facts)
    payload["history"] = render_account(facts) if len(facts.visits) >= 2 else ""
    payload["history_reason"] = None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _spec_or_404(city_id: str):
    try:
        return get_city(city_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _known_restaurant(city_id: str, restaurant_id: str, city_name: str) -> None:
    try:
        found = place_one(city_id, restaurant_id)
    except OSError as exc:
        raise HTTPException(status_code=501, detail=f"No restaurant list for {city_name} is on disk.") from exc
    if found is None:
        raise HTTPException(status_code=404, detail=f"No {city_name} restaurant {restaurant_id}.")


def _bearer(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return token.strip()


def _user(authorization: str | None) -> dict[str, object] | None:
    token = _bearer(authorization)
    if not token:
        return None
    return accounts.user_from_token(token)


_PREDICTORS = {
    "new_york": predict_new_york,
    "chicago": predict_chicago,
    "king_county": predict_king_county,
    "los_angeles": predict_los_angeles,
    "boston": predict_boston,
    "san_francisco": predict_san_francisco,
    "austin": predict_austin,
}

_CODEBOOKS = {
    "new_york": CODEBOOK_PATH,
    "chicago": CHICAGO_CODEBOOK_PATH,
    "king_county": KING_COUNTY_CODEBOOK_PATH,
    "los_angeles": LOS_ANGELES_CODEBOOK_PATH,
    "boston": BOSTON_CODEBOOK_PATH,
    "san_francisco": SAN_FRANCISCO_CODEBOOK_PATH,
}


def _codebook_or_empty(city_id: str) -> dict[str, str]:
    if city_id not in _CODEBOOKS:
        return {}
    try:
        return _codebook(city_id)
    except OSError:
        return {}


@lru_cache(maxsize=8)
def _codebook(city_id: str) -> dict[str, str]:
    frame = pl.read_parquet(_CODEBOOKS[city_id])
    return {
        code: description
        for code, description in zip(
            frame["violation_code"].to_list(),
            frame["violation_description"].to_list(),
            strict=True,
        )
        if code and description
    }
