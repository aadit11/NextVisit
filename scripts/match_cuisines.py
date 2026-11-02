"""Fill missing cuisines from OpenStreetMap for every city."""

import sys

from nextvisit.cuisines import match_city
from nextvisit.places import _SOURCES


def main() -> None:
    requested = sys.argv[1:] or [city_id for city_id in _SOURCES if city_id != "new_york"]
    for city_id in requested:
        try:
            restaurants, matches = match_city(city_id)
        except Exception as error:
            print(f"{city_id}: failed ({error})")
            continue
        print(f"{city_id}: {matches} of {restaurants} restaurants matched a cuisine")


if __name__ == "__main__":
    main()
