"""Austin keeps routine scores and does not list violation codes."""

from datetime import date

import polars as pl
from fastapi.testclient import TestClient

from nextvisit.api.main import app
from nextvisit.cities.austin import RAW_PATH, normalize_rows
from nextvisit.prepare.austin import INSPECTIONS_PATH, build_examples, collapse_inspections

client = TestClient(app)


def test_phone_is_dropped_and_the_street_address_is_kept() -> None:
    frame = normalize_rows(
        [
            {
                "facility_id": "12019345",
                "inspectionid": "1530609",
                "restaurant_name": "Chi'Lantro Mueller",
                "zip_code": "78723-3157",
                "inspection_date": "2026-09-24T00:00:00.000",
                "process_description": "Routine Inspection",
                "score": "89.000000",
                "lat": "30.3",
                "lng": "-97.7",
                "address": "1201 Barbara Jordan Blvd",
                "phone": "5125550100",
            }
        ]
    )
    assert "phone" not in frame.columns
    assert frame["address"][0] == "1201 Barbara Jordan Blvd"
    assert frame["zip"][0] == "78723"
    assert frame["score"][0] == 89.0
    assert str(frame["inspection_date"][0]) == "2026-09-24"


def test_a_score_below_90_is_positive_and_follow_ups_drop_out() -> None:
    inspections = collapse_inspections(_rows())
    assert inspections.height == 3
    low = inspections.filter(pl.col("inspection_id") == "low").row(0, named=True)
    assert low["positive"] is True
    line = inspections.filter(pl.col("inspection_id") == "line").row(0, named=True)
    assert line["positive"] is False
    assert inspections.filter(pl.col("inspection_id") == "follow").height == 0


def test_same_day_visit_is_not_a_feature() -> None:
    examples = build_examples(collapse_inspections(_rows()))
    later = examples.filter(pl.col("facility_id") == "1")
    assert later.height == 1
    assert str(later["target_date"][0]) == "2024-08-01"
    assert later["prior_inspection_count"][0] == 2
    assert later["previous_score"][0] == 80.0
    assert later["previous_positive"][0] is True
    assert later["label"][0] == 0


def test_austin_lookup_returns_a_probability_and_no_codes() -> None:
    facility_id = pl.read_parquet(INSPECTIONS_PATH, columns=["facility_id"])["facility_id"][0]
    response = client.get(f"/cities/austin/restaurants/{facility_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["abstained"] is False
    assert body["restaurant_id"] == facility_id
    assert body["label"] == "Next routine inspection scores below 90"
    assert 0.0 <= body["probability"] <= 1.0
    assert body["codes"] == []


def test_an_unknown_austin_facility_is_not_found() -> None:
    response = client.get("/cities/austin/restaurants/not-a-real-facility")
    assert response.status_code == 404


def test_a_facility_without_a_routine_score_abstains() -> None:
    raw = pl.read_parquet(RAW_PATH, columns=["facility_id"]).drop_nulls()
    kept = pl.read_parquet(INSPECTIONS_PATH, columns=["facility_id"]).unique()
    missing = raw.join(kept, on="facility_id", how="anti")
    if missing.height == 0:
        return
    facility_id = missing["facility_id"][0]
    body = client.get(f"/cities/austin/restaurants/{facility_id}").json()
    assert body["abstained"] is True
    assert body["probability"] is None
    assert body["codes"] == []


def _rows() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "facility_id": ["1", "1", "1", "2", "3"],
            "inspection_id": ["low", "line", "later", "follow", "blank"],
            "name": ["A", "A", "A", "B", "C"],
            "zip": ["78701", "78701", "78701", "78702", "78703"],
            "inspection_date": [
                date(2024, 6, 1),
                date(2024, 6, 1),
                date(2024, 8, 1),
                date(2024, 6, 2),
                date(2024, 6, 3),
            ],
            "inspection_type": [
                "Routine Inspection",
                "Routine Inspection",
                "Routine Inspection",
                "Follow-Up Inspection",
                "Routine Inspection",
            ],
            "score": [80.0, 90.0, 95.0, 70.0, None],
            "latitude": [30.0] * 5,
            "longitude": [-97.0] * 5,
        }
    )
