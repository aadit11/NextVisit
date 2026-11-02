"""What every city adapter must declare. Column names stay inside the adapter."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CitySpec:
    id: str
    name: str
    label: str
    source_url: str
    cuisine_in_source: bool
