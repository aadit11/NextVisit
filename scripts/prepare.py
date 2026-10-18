"""Build examples and a cutoff for one city, or all seven."""

import argparse

from nextvisit.cities import CITIES


def main() -> None:
    parser = argparse.ArgumentParser(description="Build pre-target examples.")
    parser.add_argument("--city", default="all", choices=["all", *sorted(CITIES)])
    args = parser.parse_args()
    targets = sorted(CITIES) if args.city == "all" else [args.city]
    raise NotImplementedError(
        "Prepare is not implemented yet for: " + ", ".join(targets)
    )


if __name__ == "__main__":
    main()
