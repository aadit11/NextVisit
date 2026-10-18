"""Time split. Train on target dates on or before the cutoff. Test on the rest."""

from datetime import date


def assign_split(target_date: date, cutoff: date) -> str:
    if target_date <= cutoff:
        return "train"
    return "test"
