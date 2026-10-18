"""Lookup API. New York scores from the saved model. Other cities are not trained."""

import os
from functools import lru_cache

import polars as pl
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from nextvisit.api.schemas import RestaurantOut
from nextvisit.cities import CITIES, get_city
from nextvisit.download import load_env
from nextvisit.model.predict import UnknownRestaurant, predict_austin, predict_chicago, predict_new_york
from nextvisit.prepare.chicago import CODEBOOK_PATH as CHICAGO_CODEBOOK_PATH
from nextvisit.prepare.collapse import CODEBOOK_PATH
from nextvisit.workorder.faithfulness import WorkOrderItem
from nextvisit.workorder.generate import closing_work_order

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


@app.get("/cities/{city_id}/restaurants/{restaurant_id}", response_model=RestaurantOut)
def get_restaurant(city_id: str, restaurant_id: str) -> RestaurantOut:
    try:
        spec = get_city(city_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if spec.id == "new_york":
        predict = predict_new_york
    elif spec.id == "chicago":
        predict = predict_chicago
    elif spec.id == "austin":
        predict = predict_austin
    else:
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
    if not get_city(city_id).has_work_order:
        payload["work_order"] = []
        return payload
    codes = payload["codes"]
    if payload["abstained"] or not isinstance(codes, list) or not codes:
        return payload
    try:
        codebook = _codebook(city_id)
    except OSError:
        payload["work_order"] = []
        payload["work_order_reason"] = f"{city_id} codebook is not on disk."
        return payload
    cuisine = payload["cuisine"]
    result = closing_work_order(
        city_id,
        cuisine=cuisine if isinstance(cuisine, str) else None,
        predicted_codes=[code for code in codes if isinstance(code, str)],
        codebook=codebook,
    )
    payload["work_order"] = [_item_payload(item) for item in result.items]
    payload["work_order_reason"] = result.reason
    return payload


def _item_payload(item: WorkOrderItem) -> dict[str, str]:
    return {
        "station": item.station,
        "violation_code": item.violation_code,
        "source_span": item.source_span,
        "step": item.step,
    }


_CODEBOOKS = {
    "new_york": CODEBOOK_PATH,
    "chicago": CHICAGO_CODEBOOK_PATH,
}


@lru_cache(maxsize=4)
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
