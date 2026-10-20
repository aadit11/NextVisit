"""Address lines keep a real street and drop placeholder parts."""

from nextvisit.addresses import format_address, street_line
from nextvisit.cities.new_york import normalize_rows


def test_placeholder_parts_are_left_out() -> None:
    assert street_line("N/A", "N/A") is None
    assert format_address(None, "0", "NY", "0") is None
    assert format_address("100 MAIN ST", "Manhattan", "NY", "10028") == "100 MAIN ST, Manhattan, NY 10028"


def test_new_york_row_keeps_the_street_and_drops_the_phone() -> None:
    frame = normalize_rows(
        [
            {
                "camis": "50086385",
                "dba": "$1 PIZZA",
                "building": "126",
                "street": "FULTON ST",
                "boro": "Manhattan",
                "zipcode": "10038",
                "phone": "2125550100",
                "inspection_date": "2024-01-01T00:00:00.000",
            }
        ]
    )
    assert "phone" not in frame.columns
    assert frame["address"][0] == "126 FULTON ST, Manhattan, NY 10038"
