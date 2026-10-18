"""City adapters. Each file owns one health department's columns and label."""

from nextvisit.cities.austin import SPEC as AUSTIN
from nextvisit.cities.boston import SPEC as BOSTON
from nextvisit.cities.chicago import SPEC as CHICAGO
from nextvisit.cities.king_county import SPEC as KING_COUNTY
from nextvisit.cities.los_angeles import SPEC as LOS_ANGELES
from nextvisit.cities.new_york import SPEC as NEW_YORK
from nextvisit.cities.san_francisco import SPEC as SAN_FRANCISCO
from nextvisit.cities.base import CitySpec

CITIES: dict[str, CitySpec] = {
    spec.id: spec
    for spec in (
        NEW_YORK,
        CHICAGO,
        KING_COUNTY,
        LOS_ANGELES,
        BOSTON,
        SAN_FRANCISCO,
        AUSTIN,
    )
}


def get_city(city_id: str) -> CitySpec:
    try:
        return CITIES[city_id]
    except KeyError as exc:
        known = ", ".join(sorted(CITIES))
        raise KeyError(f"Unknown city {city_id!r}. Known cities: {known}") from exc
