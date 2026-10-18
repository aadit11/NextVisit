"""Lookup API. Scoring waits on a saved model artifact per city."""

from fastapi import FastAPI, HTTPException

from nextvisit.cities import CITIES, get_city

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


@app.get("/cities/{city_id}/restaurants/{restaurant_id}")
def get_restaurant(city_id: str, restaurant_id: str) -> dict[str, object]:
    try:
        spec = get_city(city_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    raise HTTPException(
        status_code=501,
        detail=(
            f"No trained model for {spec.name} yet. "
            f"Restaurant {restaurant_id} was not scored."
        ),
    )
