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
from nextvisit.places import peer_comparison
from nextvisit.cities import CITIES, get_city
from nextvisit.brief.generate import generate_history
from nextvisit.brief.history import assemble
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
from nextvisit.workorder.faithfulness import WorkOrderItem
from nextvisit.workorder.generate import closing_work_order
from nextvisit.search import search_restaurants

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
            "has_work_order": spec.has_work_order,
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
    return [MapPlaceOut.model_validate(point) for point in points]


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
def get_restaurant(city_id: str, restaurant_id: str, include_work_order: bool = True) -> RestaurantOut:
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
    enriched = _with_work_order(payload, include_work_order=include_work_order)
    _attach_place(enriched)
    _attach_history(enriched)
    return RestaurantOut.model_validate(enriched)


def _with_work_order(payload: dict[str, object], *, include_work_order: bool = True) -> dict[str, object]:
    payload["work_order_reason"] = None
    city_id = str(payload["city"])
    raw_codes = payload.get("codes")
    codes = [code for code in raw_codes if isinstance(code, str)] if isinstance(raw_codes, list) else []
    codebook = _codebook_or_empty(city_id)
    if not get_city(city_id).has_work_order or not include_work_order:
        payload["work_order"] = []
    elif payload["abstained"] or not codes:
        pass
    elif not codebook and city_id in _CODEBOOKS:
        payload["work_order"] = []
        payload["work_order_reason"] = f"{city_id} codebook is not on disk."
    else:
        cuisine = payload["cuisine"]
        result = closing_work_order(
            city_id,
            cuisine=cuisine if isinstance(cuisine, str) else None,
            predicted_codes=codes,
            codebook=codebook,
        )
        payload["work_order"] = [_item_payload(item) for item in result.items]
        payload["work_order_reason"] = result.reason
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
    payload["brief"] = ""
    payload["brief_reason"] = None
    if len(facts.visits) < 2:
        payload["history"] = ""
        payload["history_reason"] = None
        return
    result = generate_history(city_id, facts)
    payload["history"] = result.text
    payload["history_reason"] = result.reason


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


def _item_payload(item: WorkOrderItem) -> dict[str, str]:
    return {
        "station": item.station,
        "violation_code": item.violation_code,
        "source_span": item.source_span,
        "step": item.step,
    }


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
