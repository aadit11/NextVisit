"""Geocode restaurants whose inspection file has no usable coordinate."""

from nextvisit.geocode import geocode_missing


def main() -> None:
    for city_id, (missing, found) in geocode_missing().items():
        print(f"{city_id}: {found} of {missing} missing restaurants geocoded")


if __name__ == "__main__":
    main()
