"""Dispatch a city download. Only New York is implemented."""

import os
from pathlib import Path

from nextvisit.cities.new_york import download as download_new_york


def download_cities(targets: list[str]) -> None:
    pending = [city for city in targets if city != "new_york"]
    if "new_york" in targets:
        path = download_new_york()
        print(f"new_york: wrote {path}", flush=True)
    if pending:
        raise NotImplementedError(
            "Download is not implemented yet for: " + ", ".join(pending)
        )


def load_env(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())
