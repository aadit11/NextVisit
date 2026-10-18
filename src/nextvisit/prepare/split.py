"""Time split. Train on target dates on or before the cutoff. Test on the rest."""

from datetime import date


def assign_split(target_date: date, cutoff: date) -> str:
    if target_date <= cutoff:
        return "train"
    return "test"


def choose_cutoff(target_dates: list[date], train_fraction: float = 0.8) -> date:
    """Cutoff is the last target date inside the earliest slice of examples."""
    if not target_dates:
        raise ValueError("Cannot choose a cutoff without examples.")
    ordered = sorted(target_dates)
    last_train_index = max(0, int(len(ordered) * train_fraction) - 1)
    return ordered[last_train_index]
