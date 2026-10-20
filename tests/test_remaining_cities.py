"""King County, Los Angeles, Boston, and San Francisco keep their own labels."""

from datetime import date

import polars as pl

from nextvisit.cities.king_county import normalize_rows as normalize_king_county
from nextvisit.cities.king_county import parse_violation
from nextvisit.cities.san_francisco import parse_violation_codes
from nextvisit.prepare.boston import build_examples as boston_examples
from nextvisit.prepare.boston import collapse_inspections as collapse_boston
from nextvisit.prepare.king_county import build_codebook as king_codebook
from nextvisit.prepare.king_county import build_examples as king_examples
from nextvisit.prepare.king_county import collapse_inspections as collapse_king
from nextvisit.prepare.los_angeles import build_examples as los_angeles_examples
from nextvisit.prepare.los_angeles import collapse_inspections as collapse_los_angeles
from nextvisit.prepare.san_francisco import build_codebook as san_francisco_codebook
from nextvisit.prepare.san_francisco import collapse_inspections as collapse_san_francisco


PACKED = (
    "113952, 113973 - Properly wash hands with hand soap., "
    "114067(f) - Provide soap and single-use towels., "
    "113999"
)


def test_king_county_red_is_serious_and_blue_is_not() -> None:
    inspections = collapse_king(_king_rows())
    assert inspections.height == 3
    serious = inspections.filter(pl.col("inspection_id") == "a-red").row(0, named=True)
    assert serious["positive"] is True
    assert serious["violation_codes"] == ["2120", "3400"]
    blue = inspections.filter(pl.col("inspection_id") == "b-blue").row(0, named=True)
    assert blue["positive"] is False
    assert inspections.filter(pl.col("inspection_id") == "old").height == 0
    assert inspections.filter(pl.col("inspection_id") == "return").height == 0


def test_king_county_phone_is_not_kept_and_wording_is_split() -> None:
    frame = normalize_king_county(
        [
            {
                "business_id": "PFE-1",
                "inspection_serial_num": "red",
                "name": "CAFE",
                "zip_code": "98105-1234",
                "inspection_date": "2024-05-01T00:00:00.000",
                "inspection_type": "Routine Inspection/Field Review",
                "inspection_score": "5.00",
                "risk_category": "3",
                "grade": "Excellent",
                "violation_type": "RED",
                "violation_description": "2120 - Proper cold holding temperatures",
                "phone": "2065550100",
            }
        ]
    )
    assert "phone" not in frame.columns
    assert frame["zip"][0] == "98105"
    assert parse_violation("2120 - Proper cold holding temperatures") == (
        "2120",
        "Proper cold holding temperatures",
    )
    titles = dict(
        zip(
            king_codebook(_king_rows())["violation_code"].to_list(),
            king_codebook(_king_rows())["violation_description"].to_list(),
            strict=True,
        )
    )
    assert titles["2120"] == "Proper cold holding temperatures"


def test_king_county_same_day_visit_is_not_a_feature() -> None:
    examples = king_examples(collapse_king(_king_rows()))
    assert examples.height == 1
    row = examples.row(0, named=True)
    assert row["business_id"] == "PFE-1"
    assert row["prior_inspection_count"] == 2
    assert row["previous_positive"] is False
    assert row["label"] == 0


def test_los_angeles_four_points_is_serious_and_the_three_cities_drop_out() -> None:
    inspections = collapse_los_angeles(_los_angeles_inspections(), _los_angeles_violations())
    assert inspections.height == 2
    serious = inspections.filter(pl.col("inspection_id") == "S1").row(0, named=True)
    assert serious["positive"] is True
    assert serious["violation_codes"] == ["F007", "F033"]
    minor = inspections.filter(pl.col("inspection_id") == "S2").row(0, named=True)
    assert minor["positive"] is False
    assert inspections.filter(pl.col("facility_id") == "pasadena").height == 0
    examples = los_angeles_examples(inspections)
    assert examples.height == 1
    assert examples["prior_inspection_count"][0] == 1
    assert examples["label"][0] == 0


def test_boston_fail_is_positive_and_a_closure_is_left_out() -> None:
    inspections = collapse_boston(_boston_rows())
    assert inspections.height == 2
    failed = inspections.filter(pl.col("inspection_id") == "2024-01-02T00:00:00").row(0, named=True)
    assert failed["positive"] is True
    assert failed["violation_codes"] == ["13-2"]
    assert inspections.filter(pl.col("result") == "HE_Closure").height == 0
    examples = boston_examples(inspections)
    assert examples.height == 1
    assert examples["label"][0] == 1
    assert examples["previous_positive"][0] is False


def test_san_francisco_keeps_wording_and_a_bare_code() -> None:
    parsed = parse_violation_codes(PACKED)
    assert parsed[0] == ("113952", "Properly wash hands with hand soap.")
    assert parsed[1] == ("113973", "Properly wash hands with hand soap.")
    assert parsed[2] == ("114067(f)", "Provide soap and single-use towels.")
    assert parsed[3] == ("113999", None)
    inspections = collapse_san_francisco(_san_francisco_rows())
    conditional = inspections.filter(pl.col("status") == "Conditional Pass").row(0, named=True)
    assert conditional["positive"] is True
    assert conditional["violation_codes"] == ["113973", "113999"]
    passed = inspections.filter(pl.col("status") == "Pass").row(0, named=True)
    assert passed["positive"] is False
    assert inspections.filter(pl.col("permit_number") == "blank").height == 0
    assert inspections.filter(pl.col("permit_number") == "future").height == 0
    titles = dict(
        zip(
            san_francisco_codebook(_san_francisco_rows())["violation_code"].to_list(),
            san_francisco_codebook(_san_francisco_rows())["violation_description"].to_list(),
            strict=True,
        )
    )
    assert titles == {"113973": "Properly wash hands with hand soap."}


def _king_rows() -> pl.DataFrame:
    return normalize_king_county(
        [
            _king("PFE-1", "a-red", "2024-05-01", "RED", "2120 - Proper cold holding temperatures"),
            _king("PFE-1", "a-red", "2024-05-01", "BLUE", "3400 - Wiping cloths properly used"),
            _king("PFE-1", "b-blue", "2024-05-01", "BLUE", "3400 - Wiping cloths properly used"),
            _king("PFE-1", "c-later", "2024-07-01", None, None),
            _king("PFE-1", "old", "2020-05-01", "RED", "2120 - Proper cold holding temperatures"),
            _king("PFE-1", "return", "2024-08-01", "RED", "2120 - Proper cold holding temperatures", "Return Inspection"),
        ]
    )


def _king(business, inspection, day, kind, description, inspection_type="Routine Inspection/Field Review"):
    return {
        "business_id": business,
        "inspection_serial_num": inspection,
        "name": "CAFE",
        "zip_code": "98105",
        "inspection_date": f"{day}T00:00:00.000",
        "inspection_type": inspection_type,
        "inspection_score": "10",
        "risk_category": "3",
        "grade": "Excellent",
        "violation_type": kind,
        "violation_description": description,
    }


def _los_angeles_inspections() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "facility_id": ["A", "A", "pasadena", "owner"],
            "serial_number": ["S1", "S2", "S3", "S4"],
            "name": ["CAFE", "CAFE", "ROSE", "OWNER"],
            "pe_description": ["RESTAURANT", "RESTAURANT", "RESTAURANT", "RESTAURANT"],
            "city": ["LOS ANGELES", "LOS ANGELES", "Pasadena", "LOS ANGELES"],
            "zip": ["90012", "90012", "91101", "90012"],
            "service": ["ROUTINE INSPECTION", "ROUTINE INSPECTION", "ROUTINE INSPECTION", "OWNER INITIATED INSPECTION"],
            "inspection_date": [date(2024, 1, 1), date(2024, 6, 1), date(2024, 1, 1), date(2024, 1, 1)],
            "score": [90.0, 96.0, 80.0, 100.0],
            "grade": ["A", "A", "B", "A"],
        }
    )


def _los_angeles_violations() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "serial_number": ["S1", "S1", "S2", "S3"],
            "status": ["OUT OF COMPLIANCE"] * 4,
            "violation_code": ["F007", "F033", "F033", "F007"],
            "violation_description": ["# 07. HOT HOLDING", "# 33. SURFACES", "# 33. SURFACES", "# 07. HOT HOLDING"],
            "points": [4.0, 1.0, 2.0, 4.0],
        }
    )


def _boston_rows() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "license": ["1", "1", "1", "1"],
            "inspection_id": [
                "2024-01-01T00:00:00",
                "2024-01-02T00:00:00",
                "2024-01-02T00:00:00",
                "2024-01-03T00:00:00",
            ],
            "name": ["CAFE"] * 4,
            "license_description": ["Eating & Drinking"] * 4,
            "zip": ["02108"] * 4,
            "inspection_date": [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 2), date(2024, 1, 3)],
            "result": ["HE_Pass", "HE_Fail", "HE_Fail", "HE_Closure"],
            "violation_code": [None, "13-2", "13-2", "99"],
            "violation_description": [None, "Hair restraint", "Hair restraint", "Closed"],
        }
    )


def _san_francisco_rows() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "permit_number": ["1", "1", "blank", "future"],
            "name": ["CAFE", "CAFE", "NO STATUS", "LATER"],
            "permit_type": ["H24"] * 4,
            "neighborhood": ["Mission"] * 4,
            "inspection_date": [date(2024, 1, 1), date(2024, 6, 1), date(2024, 1, 1), date(2031, 5, 16)],
            "status": ["Pass", "Conditional Pass", None, "Pass"],
            "violation_count": [0, 2, 0, 0],
            "violation_codes": [None, "113973 - Properly wash hands with hand soap., 113999", None, None],
            "latitude": [37.7, 37.7, 37.7, 37.7],
            "longitude": [-122.4, -122.4, -122.4, -122.4],
        }
    )
