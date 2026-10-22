"""Recent inspections move cleaner, stay put, or get worse."""

from nextvisit.history import recent_trend


def test_one_visit_is_not_a_trend() -> None:
    result = recent_trend([False])
    assert result["trend"] is None
    assert result["recent_visit_count"] == 1
    assert result["recent_serious_count"] == 0


def test_a_new_serious_visit_is_worse() -> None:
    result = recent_trend([False, True])
    assert result["trend"] == "worse"
    assert result["recent_serious_count"] == 1


def test_a_clean_visit_after_a_serious_one_is_cleaner() -> None:
    assert recent_trend([True, False])["trend"] == "cleaner"


def test_the_same_outcome_is_steady() -> None:
    clean = recent_trend([False, False, False])
    serious = recent_trend([True, True, True, True])
    assert clean["trend"] == "steady"
    assert clean["recent_serious_count"] == 0
    assert serious["trend"] == "steady"
    assert serious["recent_serious_count"] == 4


def test_only_the_last_four_visits_count() -> None:
    # Older serious visits fall outside the window. The last four are clean.
    result = recent_trend([True, True, False, False, False, False])
    assert result["trend"] == "steady"
    assert result["recent_visit_count"] == 4
    assert result["recent_serious_count"] == 0


def test_fewer_serious_visits_in_the_later_half_is_cleaner() -> None:
    assert recent_trend([True, True, False, True])["trend"] == "cleaner"


def test_austin_scores_fall_when_the_later_half_is_lower() -> None:
    from nextvisit.history import score_direction

    assert score_direction([98, 96, 91, 84]) == "falling"
    assert score_direction([80, 85, 92, 97]) == "rising"
    assert score_direction([90, 90]) == "steady"
    assert score_direction([88]) is None
