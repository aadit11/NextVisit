"""New York lookup scores a real id and abstains when the permit was never inspected."""

import polars as pl
from fastapi.testclient import TestClient

from nextvisit.api.main import app
from nextvisit.cities.new_york import RAW_PATH
from nextvisit.prepare.collapse import INSPECTIONS_PATH, UNINSPECTED

client = TestClient(app)


def test_a_restaurant_with_history_returns_a_probability() -> None:
    visits = pl.read_parquet(INSPECTIONS_PATH, columns=["camis"]).group_by("camis").len()
    camis = visits.filter(pl.col("len") >= 2)["camis"][0]
    response = client.get(f"/cities/new_york/restaurants/{camis}")
    assert response.status_code == 200
    body = response.json()
    assert body["abstained"] is False
    assert body["restaurant_id"] == camis
    assert body["name"]
    assert 0.0 <= body["probability"] <= 1.0
    assert body["codes"]
    assert all(item["code"] for item in body["codes"])
    assert any(item["description"] for item in body["codes"])
    assert body["label"].startswith("Next cycle inspection")
    assert body["trend"] in {"cleaner", "steady", "worse"}
    assert body["recent_visit_count"] >= 2
    assert 0 <= body["recent_serious_count"] <= body["recent_visit_count"]


def test_an_uninspected_permit_abstains() -> None:
    raw = pl.read_parquet(RAW_PATH, columns=["camis", "inspection_date"])
    camis = (
        raw.group_by("camis")
        .agg((pl.col("inspection_date") == UNINSPECTED).all().alias("only_uninspected"))
        .filter(pl.col("only_uninspected"))["camis"][0]
    )
    response = client.get(f"/cities/new_york/restaurants/{camis}")
    assert response.status_code == 200
    body = response.json()
    assert body["abstained"] is True
    assert body["probability"] is None
    assert body["codes"] == []
    assert body["trend"] is None
    assert body["recent_visit_count"] == 0
    assert body["restaurant_id"] == camis


def test_an_unknown_camis_is_not_found() -> None:
    response = client.get("/cities/new_york/restaurants/not-a-real-camis")
    assert response.status_code == 404


def test_unknown_city_is_not_found() -> None:
    response = client.get("/cities/not_a_city/restaurants/1")
    assert response.status_code == 404

