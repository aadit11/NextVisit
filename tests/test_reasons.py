from nextvisit.model.reasons import decision_reasons


def test_a_serious_history_lists_the_last_visit_the_count_and_the_score() -> None:
    reasons = decision_reasons(
        city_id="los_angeles",
        previous_positive=True,
        inspections=4,
        serious_count=3,
        trend="worse",
        score=74,
    )
    assert reasons == [
        "The last inspection was a serious problem.",
        "3 of 4 inspections on file were serious.",
        "Recent inspections are getting worse.",
        "The last score was 74, which is below 90.",
    ]


def test_austin_uses_the_score_direction_instead_of_the_serious_flag_trend() -> None:
    reasons = decision_reasons(
        city_id="austin",
        previous_positive=False,
        inspections=2,
        serious_count=0,
        trend="worse",
        score=93,
        score_trend="rising",
    )
    assert "Recent scores are rising." in reasons
    assert "Recent inspections are getting worse." not in reasons
    assert "The last score was 93, which is 90 or above." in reasons


def test_new_york_names_the_score_band() -> None:
    reasons = decision_reasons(
        city_id="new_york",
        previous_positive=False,
        inspections=1,
        serious_count=0,
        trend=None,
        score=8,
    )
    assert reasons == [
        "The last inspection was not a serious problem.",
        "The last score was 8, in the 0–13 range.",
    ]
