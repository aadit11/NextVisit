"""Each city adapter exposes one label and one source."""

from nextvisit.cities import CITIES


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


def test_only_austin_lacks_a_work_order() -> None:
    without = {city_id for city_id, spec in CITIES.items() if not spec.has_work_order}
    assert without == {"austin"}
