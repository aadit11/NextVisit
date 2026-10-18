from nextvisit.cities.base import CitySpec

SPEC = CitySpec(
    id="austin",
    name="Austin",
    label="Next routine inspection scores below 90",
    source_url="https://data.austintexas.gov/resource/ecmv-9xxi.json",
    has_work_order=False,
    cuisine_in_source=False,
)
