from datetime import date

import polars as pl
import pytest

from nextvisit.prepare.features import LeakageError, assert_features_before_target, build_examples


def test_same_day_feature_is_leakage() -> None:
    target = date(2024, 6, 1)
    with pytest.raises(LeakageError):
        assert_features_before_target([target], target)


def test_earlier_feature_is_allowed() -> None:
    assert_features_before_target([date(2024, 5, 1)], date(2024, 6, 1))


def test_target_score_grade_and_codes_are_not_features() -> None:
    examples = build_examples(
        _visits(
            [
                _visit(date(2024, 1, 1), score=10, grade="A", codes=["02G"], positive=True),
                _visit(date(2024, 6, 1), score=50, grade="C", codes=["10F"], positive=True),
            ]
        )
    )
    row = examples.row(0, named=True)
    assert row["label"] == 1
    assert row["previous_score"] == 10
    assert row["previous_grade"] == "A"
    assert row["previous_violation_count"] == 1
    assert row["prior_violation_count"] == 1
    assert row["days_since_previous"] == 152


def test_same_day_history_is_leakage() -> None:
    with pytest.raises(LeakageError):
        build_examples(
            _visits(
                [
                    _visit(date(2024, 6, 1), score=10, grade="A", codes=["02G"], positive=False),
                    _visit(date(2024, 6, 1), score=20, grade="B", codes=["06D"], positive=True),
                ]
            )
        )


def test_a_restaurant_with_one_visit_has_no_example() -> None:
    examples = build_examples(
        _visits([_visit(date(2024, 1, 1), score=5, grade="A", codes=[], positive=False)])
    )
    assert examples.height == 0


def _visit(
    inspection_date: date,
    *,
    score: float,
    grade: str,
    codes: list[str],
    positive: bool,
) -> dict[str, object]:
    return {
        "camis": "1",
        "inspection_date": inspection_date,
        "name": "A",
        "borough": "Manhattan",
        "cuisine": "Japanese",
        "inspection_type": "Cycle Inspection / Initial Inspection",
        "score": score,
        "grade": grade,
        "latitude": 1.0,
        "longitude": -1.0,
        "zipcode": "10001",
        "positive": positive,
        "violation_codes": codes,
    }


def _visits(rows: list[dict[str, object]]) -> pl.DataFrame:
    return pl.DataFrame(rows)
