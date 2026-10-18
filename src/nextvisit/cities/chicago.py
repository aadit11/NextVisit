from nextvisit.cities.base import CitySpec

SPEC = CitySpec(
    id="chicago",
    name="Chicago",
    label="Next inspection result is Fail",
    source_url="https://data.cityofchicago.org/resource/4ijn-s7e5.json",
    has_work_order=True,
    cuisine_in_source=False,
)
