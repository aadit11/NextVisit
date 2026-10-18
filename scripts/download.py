"""Download one city extract, or all seven, into data/raw/{city}/."""

import argparse

from nextvisit.cities import CITIES
from nextvisit.download import download_cities, load_env


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Download public inspection files.")
    parser.add_argument("--city", default="all", choices=["all", *sorted(CITIES)])
    args = parser.parse_args()
    targets = sorted(CITIES) if args.city == "all" else [args.city]
    download_cities(targets)


if __name__ == "__main__":
    main()
