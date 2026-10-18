from nextvisit.cities.base import CitySpec

SPEC = CitySpec(
    id="san_francisco",
    name="San Francisco",
    label="Next inspection status is Conditional Pass or Closure",
    source_url="https://data.sf.gov/resource/tvy3-wexg.json",
    has_work_order=True,
    cuisine_in_source=False,
)
