import json
from datetime import date

import polars as pl

from nextvisit.prepare.features import CUTOFF_PATH, EXAMPLES_PATH
from nextvisit.prepare.split import assign_split


def test_cutoff_keeps_train_on_or_before_and_test_after() -> None:
    cutoff = date(2024, 1, 1)
    assert assign_split(date(2024, 1, 1), cutoff) == "train"
    assert assign_split(date(2023, 12, 31), cutoff) == "train"
    assert assign_split(date(2024, 1, 2), cutoff) == "test"


def test_saved_examples_match_cutoff_file() -> None:
    cutoff = date.fromisoformat(json.loads(CUTOFF_PATH.read_text(encoding="utf-8"))["cutoff"])
    examples = pl.read_parquet(EXAMPLES_PATH)
    mismatches = [
        (target_date, split)
        for target_date, split in examples.select(["target_date", "split"]).iter_rows()
        if split != assign_split(target_date, cutoff)
    ]
    assert mismatches == []
    assert examples.filter(pl.col("split") == "train").height > 0
    assert examples.filter(pl.col("split") == "test").height > 0
