"""Refresh the README results table from artifacts/{city}/metrics.json."""

from pathlib import Path

from nextvisit.report import write_readme


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    write_readme(root / "README.md", root / "artifacts", root / "data" / "processed")


if __name__ == "__main__":
    main()
