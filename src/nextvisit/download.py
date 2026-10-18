"""Dispatch a city download. New York and Chicago are implemented."""

import os
from pathlib import Path

from nextvisit.cities.austin import download as download_austin
from nextvisit.cities.chicago import download as download_chicago
from nextvisit.cities.new_york import download as download_new_york

_DOWNLOADERS = {
    "new_york": download_new_york,
    "chicago": download_chicago,
    "austin": download_austin,
}


def download_cities(targets: list[str]) -> None:
    pending = [city for city in targets if city not in _DOWNLOADERS]
    for city_id in targets:
        download = _DOWNLOADERS.get(city_id)
        if download is None:
            continue
        path = download()
        print(f"{city_id}: wrote {path}", flush=True)
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
