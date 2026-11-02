"""Vercel entry. The package lives in src/, and the inspection files sit beside this file."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
if os.environ.get("VERCEL"):
    os.environ.setdefault("NEXTVISIT_DB", "/tmp/nextvisit.sqlite")
sys.path.insert(0, str(ROOT / "src"))


def _load_openmp() -> None:
    """LightGBM needs libgomp, which the Vercel Python image does not ship."""
    library = ROOT / "native" / "libgomp.so.1"
    if os.name == "nt" or not library.is_file():
        return
    import ctypes

    ctypes.CDLL(str(library), mode=ctypes.RTLD_GLOBAL)


_load_openmp()

from nextvisit.api.main import app  # noqa: E402
