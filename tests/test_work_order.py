"""The hosted work order keeps only a faithful order. A bad reply is dropped."""

import json

import httpx
import pytest

from nextvisit.workorder.generate import build_work_order, closing_work_order

DESCRIPTION = "Cold food item held above 41 F except during necessary preparation."
CODEBOOK = {"02G": DESCRIPTION, "04L": "Evidence of mice or live mice present in facility's food and/or non-food areas."}
CUISINE = "Japanese"
SPAN = "Cold food item held above 41 F"


def _settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKORDER_API_KEY", "test-key")
    monkeypatch.setenv("WORKORDER_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("WORKORDER_MODEL", "workorder-test")


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_a_faithful_reply_is_returned_and_the_call_sees_only_cuisine_and_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch)
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content.decode())
        step = f"{CUISINE}: at close, check the display case. {SPAN}."
        content = {
            "items": [
                {
                    "station": "cold_holding",
                    "violation_code": "02G",
                    "source_span": SPAN,
                    "step": step,
                }
            ]
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})

    result = closing_work_order(
        "new_york",
        cuisine=CUISINE,
        predicted_codes=["02G"],
        codebook=CODEBOOK,
        client=_client(handler),
    )
    assert result.reason is None
    assert len(result.items) == 1
    assert CUISINE in result.items[0].step
    assert SPAN in result.items[0].step
    assert seen["url"] == "https://example.test/v1/chat/completions"
    assert seen["authorization"] == "Bearer test-key"
    body = seen["body"]
    assert isinstance(body, dict)
    user = json.loads(body["messages"][1]["content"])
    assert set(user) == {"cuisine", "codes"}
    assert user["cuisine"] == CUISINE
    assert user["codes"] == [{"violation_code": "02G", "official_description": DESCRIPTION}]
    assert "04L" not in body["messages"][1]["content"]


def test_an_unfaithful_reply_is_dropped_without_rewriting_it(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch)
    rewritten = "Japanese: cool the soup before close."

    def handler(request: httpx.Request) -> httpx.Response:
        content = {
            "items": [
                {
                    "station": "cold_holding",
                    "violation_code": "99Z",
                    "source_span": "invented wording",
                    "step": rewritten,
                }
            ]
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})

    result = closing_work_order(
        "new_york",
        cuisine=CUISINE,
        predicted_codes=["02G"],
        codebook=CODEBOOK,
        client=_client(handler),
    )
    assert result.items == []
    assert result.reason
    assert "99Z" in result.reason or "02G" in result.reason
    assert rewritten not in result.reason


def test_unset_settings_do_not_call_the_host(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("WORKORDER_API_KEY", "WORKORDER_BASE_URL", "WORKORDER_MODEL"):
        monkeypatch.delenv(name, raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("host was called")

    result = closing_work_order(
        "new_york",
        cuisine=CUISINE,
        predicted_codes=["02G"],
        codebook=CODEBOOK,
        client=_client(handler),
    )
    assert result.items == []
    assert result.reason == "WORKORDER_API_KEY, WORKORDER_BASE_URL, and WORKORDER_MODEL are unset."


def test_austin_does_not_call_when_settings_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("host was called")

    order = build_work_order(
        "austin",
        cuisine=None,
        predicted_codes=["score"],
        codebook={},
        client=_client(handler),
    )
    assert order == []
