"""New York download keeps the inspection fields and drops phone."""

from nextvisit.cities.new_york import normalize_rows


def test_phone_is_dropped_and_fields_are_renamed() -> None:
    frame = normalize_rows(
        [
            {
                "camis": "50045348",
                "dba": "MCDONALD'S",
                "boro": "Manhattan",
                "cuisine_description": "Hamburgers",
                "inspection_date": "2024-09-10T00:00:00.000",
                "inspection_type": "Cycle Inspection / Initial Inspection",
                "violation_code": "04M",
                "violation_description": "Live roaches in facility's food or non-food area.",
                "critical_flag": "Critical",
                "score": "20",
                "grade": None,
                "latitude": "40.777835742497",
                "longitude": "-73.954685828487",
                "zipcode": "10028",
                "phone": "7185644939",
            }
        ]
    )
    assert "phone" not in frame.columns
    row = frame.row(0, named=True)
    assert row["name"] == "MCDONALD'S"
    assert row["address"] == "Manhattan, NY 10028"
    assert row["borough"] == "Manhattan"
    assert row["cuisine"] == "Hamburgers"
    assert str(row["inspection_date"]) == "2024-09-10"
    assert row["score"] == 20.0


def test_every_city_has_a_downloader() -> None:
    from nextvisit.cities import CITIES
    from nextvisit.download import _DOWNLOADERS

    assert set(_DOWNLOADERS) == set(CITIES)
