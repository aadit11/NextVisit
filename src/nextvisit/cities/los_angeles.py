from nextvisit.cities.base import CitySpec

SPEC = CitySpec(
    id="los_angeles",
    name="Los Angeles County",
    label="Next inspection includes a serious violation in the county points system",
    source_url="https://data.lacounty.gov/resource/6ni6-h5kp.json",
    has_work_order=True,
    cuisine_in_source=False,
)
