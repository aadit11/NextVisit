"""Repeat-last-visit baseline. The previous outcome is the prediction."""


def repeat_last_visit(previous_positive: bool) -> bool:
    return previous_positive
