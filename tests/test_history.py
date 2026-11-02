"""The history account may use only the listed inspections."""

from datetime import date

from nextvisit.brief.history import assemble, raw_visits, render_account, render_summary

RODENTS = "No rodents, insects, birds, or animals."
HANDS = "Adequate handwashing facilities supplied and accessible."


def _visits() -> list[dict[str, object]]:
    return raw_visits(
        [
            {
                "inspection_date": date(2024, 3, 2),
                "grade": "A",
                "score": 96,
                "violation_codes": ["23"],
            },
            {
                "inspection_date": date(2024, 12, 5),
                "grade": "C",
                "score": 74,
                "violation_codes": ["23", "06"],
            },
        ]
    )


def _facts():
    return assemble(
        "los_angeles",
        _visits(),
        {"23": RODENTS, "06": HANDS},
    )


def test_repeated_and_latest_only_codes_come_from_the_listed_visits() -> None:
    facts = _facts()
    assert [visit.date for visit in facts.visits] == ["2024-12-05", "2024-03-02"]
    assert facts.repeated == (("23", RODENTS, 2),)
    assert facts.latest_only == (("06", HANDS),)
    assert facts.standing == "worst"
    assert facts.earlier_count == 0


def test_the_summary_names_repeated_latest_and_earlier_codes() -> None:
    facts = assemble(
        "los_angeles",
        raw_visits(
            [
                {
                    "inspection_date": date(2023, 12, 12),
                    "grade": "A",
                    "score": 91,
                    "violation_codes": ["06", "44"],
                },
                {
                    "inspection_date": date(2024, 12, 5),
                    "grade": "C",
                    "score": 74,
                    "violation_codes": ["06", "14"],
                },
            ]
        ),
        {
            "06": HANDS,
            "14": "Food contact surfaces: clean and sanitized.",
            "44": "Floors, walls and ceilings: properly built, maintained in good repair and clean.",
        },
    )
    text = render_summary(facts)
    assert text == (
        "The December 5, 2024 inspection cited two rules, and that grade is the worst of the visits listed. "
        "One of those rules was also cited on December 12, 2023: handwashing facilities supplied and accessible. "
        "The latest visit added food contact surfaces. "
        "An earlier listed inspection also cited floors, walls and ceilings, and that citation did not return."
    )
    assert "plumbing" not in text


def test_one_visit_summary_lists_that_visits_codes() -> None:
    facts = assemble(
        "los_angeles",
        raw_visits([{"inspection_date": date(2024, 12, 5), "grade": "C", "score": 74, "violation_codes": ["23"]}]),
        {"23": RODENTS},
    )
    assert render_summary(facts) == (
        "The December 5, 2024 inspection cited rodents, insects, birds, or animals."
    )


def test_austin_summary_does_not_mention_codes() -> None:
    facts = assemble(
        "austin",
        raw_visits(
            [
                {"inspection_date": date(2024, 1, 1), "score": 96, "violation_codes": ["04L"]},
                {"inspection_date": date(2024, 6, 1), "score": 82, "violation_codes": ["04L"]},
            ]
        ),
        {"04L": "mice"},
        score_trend="falling",
    )
    assert render_summary(facts) == ""


def test_a_single_visit_has_no_pattern() -> None:
    facts = assemble(
        "los_angeles",
        raw_visits([{"inspection_date": date(2024, 12, 5), "grade": "C", "score": 74, "violation_codes": ["23"]}]),
        {"23": RODENTS},
    )
    assert len(facts.visits) == 1
    assert facts.repeated == ()
    assert facts.latest_only == ()
    assert facts.standing is None


def test_austin_history_uses_scores_and_drops_codes() -> None:
    facts = assemble(
        "austin",
        raw_visits(
            [
                {"inspection_date": date(2024, 1, 1), "score": 96, "violation_codes": ["04L"]},
                {"inspection_date": date(2024, 6, 1), "score": 82, "violation_codes": ["04L"]},
            ]
        ),
        {"04L": "mice"},
        score_trend="falling",
    )
    assert facts.include_codes is False
    assert facts.visits[0].codes == ()
    assert facts.standing == "worst"
    assert facts.score_trend == "falling"


def test_the_account_names_each_code_in_its_own_group() -> None:
    text = render_account(_facts())
    assert "Rodents, insects, birds, or animals" in text
    assert "more than one" in text
    assert "Handwashing facilities supplied and accessible" in text
    assert "only on the latest" in text
    assert "worst" in text


def test_one_visit_has_no_account() -> None:
    facts = assemble(
        "los_angeles",
        raw_visits([{"inspection_date": date(2024, 12, 5), "grade": "C", "score": 74, "violation_codes": ["23"]}]),
        {"23": RODENTS},
    )
    assert render_account(facts) == ""


def test_austin_history_uses_the_score_and_names_no_code() -> None:
    facts = assemble(
        "austin",
        raw_visits(
            [
                {"inspection_date": date(2024, 1, 1), "score": 96, "violation_codes": ["04L"]},
                {"inspection_date": date(2024, 6, 1), "score": 82, "violation_codes": ["04L"]},
            ]
        ),
        {"04L": "Evidence of mice."},
        score_trend="falling",
    )
    text = render_account(facts)
    assert "04L" not in text
    assert "mice" not in text.casefold()
    assert "falling" in text
    assert "worst" in text
