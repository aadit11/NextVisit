"""Lookup API. New York scores from the saved model. Other cities are not trained."""

import os
from functools import lru_cache

import polars as pl
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from nextvisit.api.schemas import RestaurantHit, RestaurantOut
from nextvisit.cities import CITIES, get_city
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
    allow_methods=["GET"],
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


@app.get("/cities/{city_id}/restaurants", response_model=list[RestaurantHit])
def find_restaurants(city_id: str, q: str = "") -> list[RestaurantHit]:
    try:
        spec = get_city(city_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        hits = search_restaurants(spec.id, q)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=501,
            detail=f"No restaurant list for {spec.name} is on disk.",
        ) from exc
    return [RestaurantHit.model_validate(hit) for hit in hits]


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
    return RestaurantOut.model_validate(_with_work_order(payload))


def _with_work_order(payload: dict[str, object]) -> dict[str, object]:
    payload["work_order_reason"] = None
    city_id = str(payload["city"])
    raw_codes = payload.get("codes")
    codes = [code for code in raw_codes if isinstance(code, str)] if isinstance(raw_codes, list) else []
    codebook = _codebook_or_empty(city_id)
    if not get_city(city_id).has_work_order:
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
