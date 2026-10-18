"""Build examples and a cutoff for one city, or all seven."""

import argparse

from nextvisit.cities import CITIES
from nextvisit.prepare.features import prepare_new_york


def main() -> None:
    parser = argparse.ArgumentParser(description="Build pre-target examples.")
    parser.add_argument("--city", default="all", choices=["all", *sorted(CITIES)])
    args = parser.parse_args()
    targets = sorted(CITIES) if args.city == "all" else [args.city]
    prepare_cities(targets)


def prepare_cities(targets: list[str]) -> None:
    pending = [city for city in targets if city != "new_york"]
    if "new_york" in targets:
        examples_path, cutoff_path = prepare_new_york()
        print(f"new_york: wrote {examples_path}", flush=True)
        print(f"new_york: wrote {cutoff_path}", flush=True)
    if pending:
        raise NotImplementedError(
            "Prepare is not implemented yet for: " + ", ".join(pending)
        )


if __name__ == "__main__":
    main()
