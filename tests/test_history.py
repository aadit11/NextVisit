"""The history account may use only the listed inspections."""

from datetime import date

import httpx

from nextvisit.brief.generate import generate_history
from nextvisit.brief.history import assemble, history_errors, raw_visits

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


def test_an_invented_date_is_rejected() -> None:
    errors = history_errors(
        "On 2020-01-01 the grade was a C. Rodents were cited on more than one inspection. Handwashing appears only on the latest inspection. This grade is the worst of the listed inspections.",
        _facts(),
    )
    assert any("2020-01-01" in error for error in errors)


def test_a_repeated_code_described_as_latest_only_is_rejected() -> None:
    account = (
        "Handwashing appears only on the latest inspection. "
        "Rodents (# 23) appear only on the latest inspection."
    )
    errors = history_errors(account, _facts())
    assert any("23" in error and "latest" in error for error in errors)


def test_a_code_on_both_visits_cannot_be_called_new() -> None:
    facts = assemble(
        "los_angeles",
        raw_visits(
            [
                {
                    "inspection_date": date(2023, 12, 12),
                    "grade": "A",
                    "score": 91,
                    "violation_codes": ["F052", "F006"],
                },
                {
                    "inspection_date": date(2024, 12, 5),
                    "grade": "C",
                    "score": 74,
                    "violation_codes": ["F052", "F014"],
                },
            ]
        ),
        {
            "F052": "# 52. MULTIPLE MAJOR CRITICAL VIOLATIONS / INCREASED RISK TO PUBLIC HEALTH",
            "F006": "# 06. ADEQUATE HANDWASHING FACILITIES SUPPLIED & ACCESSIBLE",
            "F014": "# 14. FOOD CONTACT SURFACES: CLEAN AND SANITIZED",
        },
    )
    account = (
        "The problems that appear only on the latest inspection include food contact surfaces: clean and sanitized (# 14) "
        "and multiple major critical violations / increased risk to public health (# 52)."
    )
    errors = history_errors(account, facts)
    assert any("F052" in error for error in errors)


def test_a_latest_only_code_described_as_repeated_is_rejected() -> None:
    account = "Handwashing (# 06) was cited on more than one inspection."
    errors = history_errors(account, _facts())
    assert any("06" in error and "more than one" in error for error in errors)


def test_best_is_rejected_when_the_latest_grade_is_the_worst() -> None:
    errors = history_errors(
        "The latest grade is the best of the listed inspections. Rodents were cited on more than one inspection.",
        _facts(),
    )
    assert any("best" in error for error in errors)


def test_the_account_names_each_code_in_its_own_group() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("host was called")

    result = generate_history("los_angeles", _facts(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert result.reason is None
    assert "No rodents, insects, birds, or animals" in result.text
    assert "more than one" in result.text
    assert "Adequate handwashing facilities supplied and accessible" in result.text
    assert "only on the latest" in result.text
    assert "worst" in result.text


def test_one_visit_does_not_call_the_host() -> None:
    facts = assemble(
        "los_angeles",
        raw_visits([{"inspection_date": date(2024, 12, 5), "grade": "C", "score": 74, "violation_codes": ["23"]}]),
        {"23": RODENTS},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("host was called")

    result = generate_history("los_angeles", facts, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert result.text == ""
    assert result.reason is None


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
    result = generate_history("austin", facts)
    assert "04L" not in result.text
    assert "mice" not in result.text.casefold()
    assert "falling" in result.text
    assert "worst" in result.text
