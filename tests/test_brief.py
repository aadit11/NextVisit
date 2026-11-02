"""A hygiene brief may use only the supplied record. An extra claim drops it."""

import json
from datetime import date

import httpx
import pytest

from nextvisit.brief.faithfulness import BriefFacts, brief_errors
from nextvisit.brief.generate import generate_brief

EQUIPMENT = "Non-food contact surface or equipment made of unacceptable material, not kept clean."
MICE = "Evidence of mice or live mice in establishment's food or non-food areas."
TODAY = date(2026, 10, 22)


def _facts(**overrides: object) -> BriefFacts:
    base = dict(
        inspection_date="2026-02-27",
        grade="A",
        score=7,
        trend="steady",
        recent_visit_count=4,
        recent_serious_count=4,
        peer_count=78,
        peer_graded_count=64,
        peer_standing="typical",
        peer_cuisine="Bakery Products/Desserts",
        peer_area="Bronx",
        codes=(("10F", EQUIPMENT),),
        include_codes=True,
        today=TODAY,
    )
    base.update(overrides)
    return BriefFacts(**base)  # type: ignore[arg-type]


def _settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRIEF_API_KEY", "test-key")
    monkeypatch.setenv("BRIEF_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("BRIEF_MODEL", "brief-test")


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_a_pest_claim_the_record_does_not_contain_is_rejected() -> None:
    invented = "Mice were seen in the kitchen, so skip this bakery."
    errors = brief_errors(invented, _facts())
    assert any("pests" in error for error in errors)
    assert invented not in " ".join(errors)


def test_a_faithful_brief_keeps_the_date_grade_and_code_text() -> None:
    brief = (
        "The last inspection was 2026-02-27 and the grade was an A, with a score of 7. "
        "The last four inspections kept finding a serious problem. "
        "Among 64 graded Bakery Products/Desserts restaurants in the Bronx, this A is typical."
    )
    assert brief_errors(brief, _facts()) == []


def test_mice_are_allowed_when_the_code_text_says_mice() -> None:
    brief = "The inspection on 2026-02-27 cites mice in the food area."
    assert brief_errors(brief, _facts(codes=(("04L", MICE),))) == []


def test_a_different_grade_and_a_different_date_are_rejected() -> None:
    errors = brief_errors("This C from 2024-01-01 is getting cleaner.", _facts())
    assert errors
    assert any("cleaner" in error for error in errors)
    assert any("2024-01-01" in error for error in errors)


def test_an_unfaithful_reply_is_dropped_without_rewriting_it(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch)
    invented = "Mice were seen in the kitchen."

    def handler(request: httpx.Request) -> httpx.Response:
        content = {"brief": invented}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})

    result = generate_brief("new_york", _facts(), client=_client(handler))
    assert result.text == ""
    assert result.reason
    assert "pests" in result.reason
    assert invented not in result.reason


def test_a_faithful_reply_is_returned_and_the_call_sees_only_the_record(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch)
    seen: dict[str, object] = {}
    written = "Inspected eight months ago. The grade was an A and the score was 7."

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content.decode())
        content = {"brief": written}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})

    result = generate_brief("new_york", _facts(), client=_client(handler))
    assert result.reason is None
    assert result.text == written
    assert seen["url"] == "https://example.test/v1/chat/completions"
    assert seen["authorization"] == "Bearer test-key"
    body = seen["body"]
    assert isinstance(body, dict)
    user = json.loads(body["messages"][1]["content"])
    assert set(user) == {
        "inspection_date",
        "inspection_age",
        "grade",
        "score",
        "trend",
        "recent_visit_count",
        "recent_serious_count",
        "peer",
        "codes",
    }
    assert user["codes"] == [{"code": "10F", "text": EQUIPMENT}]
    assert "probability" not in user


def test_unset_settings_do_not_call_the_host(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "BRIEF_API_KEY",
        "BRIEF_BASE_URL",
        "BRIEF_MODEL",
        "WORKORDER_API_KEY",
        "WORKORDER_BASE_URL",
        "WORKORDER_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("host was called")

    result = generate_brief("new_york", _facts(), client=_client(handler))
    assert result.text == ""
    assert result.reason == "BRIEF_API_KEY, BRIEF_BASE_URL, and BRIEF_MODEL are unset."


def test_empty_brief_settings_use_the_work_order_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("BRIEF_API_KEY", "BRIEF_BASE_URL", "BRIEF_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("WORKORDER_API_KEY", "work-key")
    monkeypatch.setenv("WORKORDER_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("WORKORDER_MODEL", "work-model")
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content.decode())
        content = {"brief": "Inspected eight months ago. The grade was an A and the score was 7."}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})

    result = generate_brief("new_york", _facts(), client=_client(handler))
    assert result.text.startswith("Inspected eight months ago.")
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["model"] == "work-model"


def test_austin_sends_the_score_and_age_and_no_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch)
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content.decode())
        content = {"brief": "The score was 82. Inspected eight months ago. Recent scores are falling."}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})

    facts = _facts(
        grade="Below 90",
        score=82,
        trend="worse",
        score_trend="falling",
        recent_serious_count=3,
        peer_count=0,
        peer_graded_count=0,
        peer_standing=None,
        peer_cuisine=None,
        peer_area=None,
        codes=(("04L", MICE),),
        include_codes=True,
    )
    result = generate_brief("austin", facts, client=_client(handler))
    assert result.reason is None
    assert result.text
    body = seen["body"]
    assert isinstance(body, dict)
    user = json.loads(body["messages"][1]["content"])
    assert set(user) == {"inspection_date", "inspection_age", "score", "scores_falling", "score_trend"}
    assert user["score"] == 82
    assert user["scores_falling"] is True
    assert user["score_trend"] == "falling"
    assert "violation" in body["messages"][0]["content"].lower()


def test_austin_drops_a_brief_that_mentions_a_code(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch)
    invented = "Score 82. The visit also cites code 04L."

    def handler(request: httpx.Request) -> httpx.Response:
        content = {"brief": invented}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})

    facts = _facts(grade="Below 90", score=82, trend="worse", score_trend="falling", codes=(("04L", MICE),))
    result = generate_brief("austin", facts, client=_client(handler))
    assert result.text == ""
    assert result.reason
    assert "04L" in result.reason
    assert invented not in result.reason


def test_austin_drops_a_brief_that_says_scores_are_falling_when_they_are_rising(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch)
    invented = "The score was 97. Recent scores are falling."

    def handler(request: httpx.Request) -> httpx.Response:
        content = {"brief": invented}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})

    facts = _facts(score=97, score_trend="rising", peer_count=0, peer_cuisine=None, peer_area=None)
    result = generate_brief("austin", facts, client=_client(handler))
    assert result.text == ""
    assert result.reason
    assert "falling" in result.reason
    assert invented not in result.reason


def test_a_brief_that_contradicts_the_next_inspection_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch)
    invented = "The next inspection is likely to come back clean. The last score was 74, which is below 90."

    def handler(request: httpx.Request) -> httpx.Response:
        content = {"brief": invented}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})

    facts = _facts(
        grade="C",
        score=74,
        trend="worse",
        recent_visit_count=2,
        recent_serious_count=1,
        peer_count=0,
        peer_cuisine=None,
        peer_area=None,
        codes=(),
        next_inspection="The next inspection is likely to include a serious violation again.",
        reasons=(
            "The last inspection was a serious problem.",
            "1 of 2 inspections on file were serious.",
            "Recent inspections are getting worse.",
            "The last score was 74, which is below 90.",
        ),
    )
    result = generate_brief("los_angeles", facts, client=_client(handler))
    assert result.text == ""
    assert result.reason
    assert "clean" in result.reason
    assert invented not in result.reason
