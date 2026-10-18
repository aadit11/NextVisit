"""New York lookup scores a real id and abstains when the permit was never inspected."""

import polars as pl
import pytest
from fastapi.testclient import TestClient

from nextvisit.api.main import app
from nextvisit.cities.new_york import RAW_PATH
from nextvisit.prepare.collapse import INSPECTIONS_PATH, UNINSPECTED
from nextvisit.workorder.faithfulness import WorkOrderItem
from nextvisit.workorder.generate import ClosingWorkOrder

client = TestClient(app)


def test_a_restaurant_with_history_returns_a_probability() -> None:
    camis = pl.read_parquet(INSPECTIONS_PATH, columns=["camis"])["camis"][0]
    response = client.get(f"/cities/new_york/restaurants/{camis}")
    assert response.status_code == 200
    body = response.json()
    assert body["abstained"] is False
    assert body["restaurant_id"] == camis
    assert body["name"]
    assert 0.0 <= body["probability"] <= 1.0
    assert body["codes"]
    assert body["label"].startswith("Next cycle inspection")


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
    assert body["restaurant_id"] == camis


def test_an_unknown_camis_is_not_found() -> None:
    response = client.get("/cities/new_york/restaurants/not-a-real-camis")
    assert response.status_code == 404


def test_untrained_city_is_not_implemented() -> None:
    response = client.get("/cities/chicago/restaurants/1")
    assert response.status_code == 501


def test_unset_work_order_settings_keep_the_score(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("WORKORDER_API_KEY", "WORKORDER_BASE_URL", "WORKORDER_MODEL"):
        monkeypatch.delenv(name, raising=False)
    camis = pl.read_parquet(INSPECTIONS_PATH, columns=["camis"])["camis"][0]
    response = client.get(f"/cities/new_york/restaurants/{camis}")
    body = response.json()
    assert response.status_code == 200
    assert body["abstained"] is False
    assert 0.0 <= body["probability"] <= 1.0
    assert body["codes"]
    assert body["work_order"] == []
    assert "unset" in body["work_order_reason"]


def test_lookup_returns_a_faithful_work_order(monkeypatch: pytest.MonkeyPatch) -> None:
    cuisine = "Japanese"
    span = "Cold food item held above 41 F"
    item = WorkOrderItem(
        station="cold_holding",
        violation_code="02G",
        source_span=span,
        step=f"{cuisine}: at close, check the display case. {span}.",
    )

    def fake_order(city_id: str, **kwargs: object) -> ClosingWorkOrder:
        assert city_id == "new_york"
        assert kwargs["cuisine"]
        assert kwargs["predicted_codes"]
        return ClosingWorkOrder([item])

    monkeypatch.setattr("nextvisit.api.main.closing_work_order", fake_order)
    camis = pl.read_parquet(INSPECTIONS_PATH, columns=["camis"])["camis"][0]
    body = client.get(f"/cities/new_york/restaurants/{camis}").json()
    assert body["work_order_reason"] is None
    assert body["probability"] is not None
    assert cuisine in body["work_order"][0]["step"]
    assert span in body["work_order"][0]["step"]
    assert span in body["work_order"][0]["source_span"]


def test_lookup_drops_an_unfaithful_work_order(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_order(city_id: str, **kwargs: object) -> ClosingWorkOrder:
        return ClosingWorkOrder([], "source_span for 02G is not in the official description.")

    monkeypatch.setattr("nextvisit.api.main.closing_work_order", fake_order)
    camis = pl.read_parquet(INSPECTIONS_PATH, columns=["camis"])["camis"][0]
    body = client.get(f"/cities/new_york/restaurants/{camis}").json()
    assert body["work_order"] == []
    assert body["codes"]
    assert body["probability"] is not None
    assert body["work_order_reason"] == "source_span for 02G is not in the official description."
