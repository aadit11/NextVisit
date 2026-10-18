"""Lookup API. New York scores from the saved model. Other cities are not trained."""

from functools import lru_cache

import polars as pl
from fastapi import FastAPI, HTTPException

from nextvisit.api.schemas import RestaurantOut
from nextvisit.cities import CITIES, get_city
from nextvisit.download import load_env
from nextvisit.model.predict import UnknownRestaurant, predict_new_york
from nextvisit.prepare.collapse import CODEBOOK_PATH
from nextvisit.workorder.faithfulness import WorkOrderItem
from nextvisit.workorder.generate import closing_work_order

load_env()

app = FastAPI(title="Nextvisit")


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
    if spec.id != "new_york":
        raise HTTPException(
            status_code=501,
            detail=f"No trained model for {spec.name} yet. Restaurant {restaurant_id} was not scored.",
        )
    try:
        payload = predict_new_york(restaurant_id)
    except UnknownRestaurant as exc:
        raise HTTPException(status_code=404, detail=f"No New York restaurant {restaurant_id}.") from exc
    return RestaurantOut.model_validate(_with_work_order(payload))


def _with_work_order(payload: dict[str, object]) -> dict[str, object]:
    payload["work_order_reason"] = None
    codes = payload["codes"]
    if payload["abstained"] or not isinstance(codes, list) or not codes:
        return payload
    try:
        codebook = _new_york_codebook()
    except OSError:
        payload["work_order"] = []
        payload["work_order_reason"] = "New York codebook is not on disk."
        return payload
    cuisine = payload["cuisine"]
    result = closing_work_order(
        "new_york",
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


@lru_cache(maxsize=1)
def _new_york_codebook() -> dict[str, str]:
    frame = pl.read_parquet(CODEBOOK_PATH)
    return {
        code: description
        for code, description in zip(
            frame["violation_code"].to_list(),
            frame["violation_description"].to_list(),
            strict=True,
        )
        if code and description
    }
