from nextvisit.cities.base import CitySpec

SPEC = CitySpec(
    id="new_york",
    name="New York",
    label="Next cycle inspection includes a critical violation",
    source_url="https://data.cityofnewyork.us/resource/43nn-pn8j.json",
    has_work_order=True,
    cuisine_in_source=True,
)
