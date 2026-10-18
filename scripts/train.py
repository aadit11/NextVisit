"""Train one city model, or all seven, and write artifacts/{city}/."""

import argparse

from nextvisit.cities import CITIES
from nextvisit.model.train import train_city


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the next-visit ranker.")
    parser.add_argument("--city", default="all", choices=["all", *sorted(CITIES)])
    args = parser.parse_args()
    targets = sorted(CITIES) if args.city == "all" else [args.city]
    for city_id in targets:
        train_city(city_id)


if __name__ == "__main__":
    main()
