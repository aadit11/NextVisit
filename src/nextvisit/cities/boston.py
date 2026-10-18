from nextvisit.cities.base import CitySpec

SPEC = CitySpec(
    id="boston",
    name="Boston",
    label="Next inspection result is a fail",
    source_url="https://data.boston.gov/dataset/food-establishment-inspections",
    has_work_order=True,
    cuisine_in_source=False,
)
