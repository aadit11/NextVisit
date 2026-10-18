from datetime import date

from nextvisit.prepare.split import assign_split


def test_cutoff_keeps_train_on_or_before_and_test_after() -> None:
    cutoff = date(2024, 1, 1)
    assert assign_split(date(2024, 1, 1), cutoff) == "train"
    assert assign_split(date(2023, 12, 31), cutoff) == "train"
    assert assign_split(date(2024, 1, 2), cutoff) == "test"
