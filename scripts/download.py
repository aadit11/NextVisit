"""Download one city extract, or all seven, into data/raw/{city}/."""

import argparse

from nextvisit.cities import CITIES


def main() -> None:
    parser = argparse.ArgumentParser(description="Download public inspection files.")
    parser.add_argument("--city", default="all", choices=["all", *sorted(CITIES)])
    args = parser.parse_args()
    targets = sorted(CITIES) if args.city == "all" else [args.city]
    raise NotImplementedError(
        "Download is not implemented yet for: " + ", ".join(targets)
    )


if __name__ == "__main__":
    main()
