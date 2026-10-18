from datetime import date

import pytest

from nextvisit.prepare.features import LeakageError, assert_features_before_target


def test_same_day_feature_is_leakage() -> None:
    target = date(2024, 6, 1)
    with pytest.raises(LeakageError):
        assert_features_before_target([target], target)


def test_earlier_feature_is_allowed() -> None:
    assert_features_before_target([date(2024, 5, 1)], date(2024, 6, 1))
