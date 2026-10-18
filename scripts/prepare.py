"""Build examples and a cutoff for one city, or all seven."""

import argparse

from nextvisit.cities import CITIES
from nextvisit.prepare.austin import prepare_austin
from nextvisit.prepare.chicago import prepare_chicago
from nextvisit.prepare.features import prepare_new_york

_PREPARERS = {
    "new_york": prepare_new_york,
    "chicago": prepare_chicago,
    "austin": prepare_austin,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build pre-target examples.")
    parser.add_argument("--city", default="all", choices=["all", *sorted(CITIES)])
    args = parser.parse_args()
    targets = sorted(CITIES) if args.city == "all" else [args.city]
    prepare_cities(targets)


def prepare_cities(targets: list[str]) -> None:
    pending = [city for city in targets if city not in _PREPARERS]
    for city_id in targets:
        prepare = _PREPARERS.get(city_id)
        if prepare is None:
            continue
        examples_path, cutoff_path = prepare()
        print(f"{city_id}: wrote {examples_path}", flush=True)
        print(f"{city_id}: wrote {cutoff_path}", flush=True)
    if pending:
        raise NotImplementedError(
            "Prepare is not implemented yet for: " + ", ".join(pending)
        )


if __name__ == "__main__":
    main()
