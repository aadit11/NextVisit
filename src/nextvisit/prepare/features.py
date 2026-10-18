"""History features. Every feature date must be strictly before the target visit."""

from datetime import date


class LeakageError(ValueError):
    """A feature is dated on or after the visit being predicted."""


def assert_features_before_target(feature_dates: list[date], target_date: date) -> None:
    late = [day for day in feature_dates if day >= target_date]
    if late:
        raise LeakageError(f"Features dated on or after {target_date.isoformat()}: {late}")
