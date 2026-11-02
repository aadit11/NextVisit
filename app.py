"""Vercel entry. The package lives in src/, and the inspection files sit beside this file."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
if os.environ.get("VERCEL"):
    os.environ.setdefault("NEXTVISIT_DB", "/tmp/nextvisit.sqlite")
sys.path.insert(0, str(ROOT / "src"))

from nextvisit.api.main import app  # noqa: E402
