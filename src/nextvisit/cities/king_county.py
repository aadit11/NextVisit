from nextvisit.cities.base import CitySpec

SPEC = CitySpec(
    id="king_county",
    name="King County",
    label="Next inspection includes a violation the county marks as serious",
    source_url="https://data.kingcounty.gov/resource/r878-4sxa.json",
    has_work_order=True,
    cuisine_in_source=False,
)
