"""Chicago keeps canvass results, parses packed violations, and blocks same-day features."""

from datetime import date

import polars as pl

from fastapi.testclient import TestClient

from nextvisit.api.main import app
from nextvisit.cities.chicago import RAW_PATH, normalize_rows, parse_violations
from nextvisit.prepare.chicago import (
    INSPECTIONS_PATH,
    build_codebook,
    build_examples,
    collapse_inspections,
)

client = TestClient(app)


PACKED = (
    "16. FOOD-CONTACT SURFACES: CLEANED & SANITIZED - Comments: ICE MACHINE HAS SLIME. "
    "| 47. FOOD & NON-FOOD CONTACT SURFACES CLEANABLE - Comments: TORN GASKET. "
    "| 47. FOOD & NON-FOOD CONTACT SURFACES CLEANABLE - Comments: DIRTY CAN OPENER."
)


def test_packed_text_splits_number_title_and_comment() -> None:
    parsed = parse_violations(PACKED)
    assert parsed[0] == (
        "16",
        "FOOD-CONTACT SURFACES: CLEANED & SANITIZED",
        "ICE MACHINE HAS SLIME.",
    )
    assert [item[0] for item in parsed] == ["16", "47", "47"]


def test_phone_is_not_kept() -> None:
    frame = normalize_rows(
        [
            {
                "inspection_id": "1",
                "license_": "99",
                "dba_name": "CAFE",
                "facility_type": "Restaurant",
                "risk": "Risk 1 (High)",
                "zip": "60601",
                "inspection_date": "2024-06-01T00:00:00.000",
                "inspection_type": "Canvass",
                "results": "Fail",
                "violations": PACKED,
                "latitude": "41.8",
                "longitude": "-87.6",
                "phone": "3125550100",
            }
        ]
    )
    assert "phone" not in frame.columns
    assert frame["license"][0] == "99"
    assert str(frame["inspection_date"][0]) == "2024-06-01"


def test_canvass_fail_is_positive_and_other_programs_drop_out() -> None:
    inspections = collapse_inspections(_rows())
    assert inspections.height == 3
    fail = inspections.filter(pl.col("inspection_id") == "a").row(0, named=True)
    assert fail["positive"] is True
    assert fail["violation_codes"] == ["16", "47"]
    assert fail["violation_comments"][0] == "ICE MACHINE HAS SLIME."
    assert fail["violation_count"] == 3
    passed = inspections.filter(pl.col("inspection_id") == "b").row(0, named=True)
    assert passed["positive"] is False
    assert inspections.filter(pl.col("inspection_id") == "complaint").height == 0
    assert inspections.filter(pl.col("inspection_id") == "closed").height == 0


def test_codebook_keeps_the_official_title() -> None:
    codebook = build_codebook(_rows())
    titles = dict(zip(codebook["violation_code"].to_list(), codebook["violation_description"].to_list(), strict=True))
    assert titles["16"] == "FOOD-CONTACT SURFACES: CLEANED & SANITIZED"
    assert "ICE MACHINE" not in titles["16"]


def test_same_day_visit_is_not_a_feature() -> None:
    inspections = collapse_inspections(_rows())
    examples = build_examples(inspections)
    later = examples.filter(pl.col("license") == "1")
    assert later.height == 1
    assert str(later["target_date"][0]) == "2024-07-01"
    assert later["prior_inspection_count"][0] == 2
    assert later["previous_positive"][0] is False
    assert "cuisine" not in examples.columns


def test_a_chicago_license_returns_a_probability() -> None:
    license_id = pl.read_parquet(INSPECTIONS_PATH, columns=["license"])["license"][0]
    response = client.get(f"/cities/chicago/restaurants/{license_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["abstained"] is False
    assert body["restaurant_id"] == license_id
    assert body["cuisine"] is None
    assert body["label"] == "Next inspection result is Fail"
    assert 0.0 <= body["probability"] <= 1.0


def test_a_license_without_a_canvass_abstains() -> None:
    raw = pl.read_parquet(RAW_PATH, columns=["license"]).drop_nulls()
    kept = pl.read_parquet(INSPECTIONS_PATH, columns=["license"]).unique()
    license_id = raw.join(kept, on="license", how="anti")["license"][0]
    body = client.get(f"/cities/chicago/restaurants/{license_id}").json()
    assert body["abstained"] is True
    assert body["probability"] is None
    assert body["codes"] == []


def test_an_unknown_chicago_license_is_not_found() -> None:
    response = client.get("/cities/chicago/restaurants/not-a-real-license")
    assert response.status_code == 404


def _rows() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "inspection_id": ["a", "b", "c", "complaint", "closed"],
            "license": ["1", "1", "1", "2", "3"],
            "name": ["CAFE", "CAFE", "CAFE", "DINER", "GONE"],
            "facility_type": ["Restaurant"] * 5,
            "risk": ["Risk 1 (High)"] * 5,
            "zip": ["60601"] * 5,
            "inspection_date": [
                date(2024, 6, 1),
                date(2024, 6, 1),
                date(2024, 7, 1),
                date(2024, 6, 2),
                date(2024, 6, 3),
            ],
            "inspection_type": [
                "Canvass",
                "Canvass Re-Inspection",
                "Canvass",
                "Complaint",
                "Canvass",
            ],
            "results": ["Fail", "Pass", "Fail", "Fail", "Out of Business"],
            "violations": [PACKED, None, None, PACKED, None],
            "latitude": [41.0] * 5,
            "longitude": [-87.0] * 5,
        }
    )
