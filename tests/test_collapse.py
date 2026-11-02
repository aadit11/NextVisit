"""Each city adapter exposes one label and one source.

Collapse packs several violation rows into one inspection. It also leaves
uninspected permits and non-cycle programs out of that table.
"""

from datetime import date

import polars as pl

from nextvisit.cities import CITIES
from nextvisit.prepare.collapse import build_codebook, collapse_inspections


def _rows() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "camis": ["1", "1", "1", "2", "3"],
            "name": ["A", "A", "A", "B", "C"],
            "borough": ["Manhattan", "Manhattan", "Manhattan", "Bronx", "Queens"],
            "cuisine": ["Japanese", "Japanese", "Japanese", "Bakery", "Pizza"],
            "inspection_date": [
                date(2024, 6, 1),
                date(2024, 6, 1),
                date(1900, 1, 1),
                date(2024, 6, 2),
                date(2024, 7, 1),
            ],
            "inspection_type": [
                "Cycle Inspection / Initial Inspection",
                "Cycle Inspection / Initial Inspection",
                "Cycle Inspection / Initial Inspection",
                "Pre-permit (Operational) / Initial Inspection",
                "Cycle Inspection / Re-inspection",
            ],
            "violation_code": ["02G", "06D", "10F", "02B", None],
            "violation_description": [
                "Cold food item held above 41 F.",
                "Food contact surface not sanitized.",
                "Facility not vermin proof.",
                "Hot food item not held at or above 140 F.",
                None,
            ],
            "critical_flag": ["Critical", "Not Critical", "Critical", "Critical", None],
            "score": [20.0, 20.0, 12.0, 10.0, 0.0],
            "grade": ["B", "B", "A", "A", "A"],
            "latitude": [1.0, 1.0, 1.0, 2.0, 3.0],
            "longitude": [-1.0, -1.0, -1.0, -2.0, -3.0],
            "zipcode": ["10001", "10001", "10001", "10451", "11101"],
        }
    )


def test_two_violations_become_one_inspection() -> None:
    inspections = collapse_inspections(_rows())
    assert inspections.height == 2
    visit = inspections.filter(pl.col("camis") == "1").row(0, named=True)
    assert visit["positive"] is True
    assert visit["violation_codes"] == ["02G", "06D"]
    assert visit["score"] == 20.0


def test_uninspected_permit_and_non_cycle_program_are_left_out() -> None:
    inspections = collapse_inspections(_rows())
    assert inspections.filter(pl.col("camis") == "2").height == 0
    assert inspections.filter(pl.col("inspection_date") == date(1900, 1, 1)).height == 0
    clean = inspections.filter(pl.col("camis") == "3").row(0, named=True)
    assert clean["positive"] is False
    assert clean["violation_codes"] == []


def test_codebook_keeps_one_description_per_code() -> None:
    codebook = build_codebook(_rows())
    assert codebook["violation_code"].to_list() == ["02G", "06D"]



def test_seven_cities_are_registered() -> None:
    assert set(CITIES) == {
        "new_york",
        "chicago",
        "king_county",
        "los_angeles",
        "boston",
        "san_francisco",
        "austin",
    }

