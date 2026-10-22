"""One JSON call that writes the diner brief from facts already on the record."""

import json
import os
from dataclasses import dataclass

import httpx

from nextvisit.brief.faithfulness import BriefFacts, brief_errors
from nextvisit.cities import get_city

_SETTINGS = ("BRIEF_API_KEY", "BRIEF_BASE_URL", "BRIEF_MODEL")


@dataclass(frozen=True)
class HygieneBrief:
    text: str
    reason: str | None = None


def generate_brief(
    city_id: str,
    facts: BriefFacts,
    client: httpx.Client | None = None,
) -> HygieneBrief:
    """Return a short brief, or an empty brief and a reason. Never rewrite a rejected one."""
    get_city(city_id)
    payload = _user_payload(city_id, facts)
    if not payload:
        return HygieneBrief("", "No inspection is on file for a brief.")

    settings = _settings()
    if settings is None:
        return HygieneBrief("", "BRIEF_API_KEY, BRIEF_BASE_URL, and BRIEF_MODEL are unset.")
    api_key, base_url, model = settings

    request = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _instructions(austin=city_id == "austin")},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    }
    try:
        body = _post(client, _completions_url(base_url), api_key, request)
    except httpx.HTTPStatusError as exc:
        return HygieneBrief("", f"Brief call failed (HTTP {exc.response.status_code}).")
    except httpx.HTTPError:
        return HygieneBrief("", "Brief call failed.")

    try:
        text = _parse_brief(body)
    except ValueError as exc:
        return HygieneBrief("", str(exc))

    errors = brief_errors(text, _checked_facts(city_id, facts))
    if errors:
        return HygieneBrief("", " ".join(errors))
    return HygieneBrief(text)


def _checked_facts(city_id: str, facts: BriefFacts) -> BriefFacts:
    if city_id != "austin":
        return facts
    return BriefFacts(
        inspection_date=facts.inspection_date,
        score=facts.score,
        score_trend=facts.score_trend,
        include_codes=False,
        today=facts.today,
    )


def _user_payload(city_id: str, facts: BriefFacts) -> dict[str, object]:
    checked = _checked_facts(city_id, facts)
    if city_id == "austin":
        return _austin_payload(checked)
    payload: dict[str, object] = {}
    if checked.inspection_date:
        payload["inspection_date"] = checked.inspection_date
    age = checked.inspection_age
    if age:
        payload["inspection_age"] = age
    if checked.grade:
        payload["grade"] = checked.grade
    if checked.score is not None:
        payload["score"] = int(checked.score) if float(checked.score).is_integer() else checked.score
    if checked.trend in {"cleaner", "steady", "worse"}:
        payload["trend"] = checked.trend
        payload["recent_visit_count"] = checked.recent_visit_count
        payload["recent_serious_count"] = checked.recent_serious_count
    if checked.peer_count >= 1 and checked.peer_cuisine and checked.peer_area:
        peer: dict[str, object] = {
            "cuisine": checked.peer_cuisine,
            "area": checked.peer_area,
            "count": checked.peer_count,
        }
        if checked.peer_graded_count:
            peer["graded_count"] = checked.peer_graded_count
        if checked.peer_standing in {"better", "typical", "worse"}:
            peer["standing"] = checked.peer_standing
        payload["peer"] = peer
    if checked.include_codes:
        codes = [
            {"code": code, "text": text}
            for code, text in checked.codes
            if text
        ]
        if codes:
            payload["codes"] = codes
    return payload


def _austin_payload(facts: BriefFacts) -> dict[str, object]:
    """Austin's brief gets the score, its age, and whether recent scores are falling."""
    payload: dict[str, object] = {}
    if facts.inspection_date:
        payload["inspection_date"] = facts.inspection_date
    age = facts.inspection_age
    if age:
        payload["inspection_age"] = age
    if facts.score is not None:
        payload["score"] = int(facts.score) if float(facts.score).is_integer() else facts.score
    if facts.score_trend in {"falling", "rising", "steady"}:
        payload["scores_falling"] = facts.score_trend == "falling"
        payload["score_trend"] = facts.score_trend
    return payload


def _instructions(*, austin: bool) -> str:
    if austin:
        return (
            "Return one JSON object with the key brief. "
            "The brief is two or three sentences for a diner. "
            "Use only the score, how old the inspection is, and whether recent scores are falling. "
            "Say the scores are falling only when scores_falling is true. "
            "Do not mention violation codes or a probability."
        )
    return (
        "Return one JSON object with the key brief. "
        "The brief is two or three sentences for a diner deciding whether to eat here. "
        "Use only the facts in the user message. "
        "A date, grade, score, trend, count, or code that is not in those facts must not appear. "
        "Do not name pests, handwashing, temperature, plumbing, restrooms, or garbage "
        "unless the code text describes them. "
        "Do not give a probability or a closing checklist. "
        "If a fact is absent, leave it out. "
        "You may mention a violation only by quoting text from codes."
    )


def _settings() -> tuple[str, str, str] | None:
    values = [os.environ.get(name, "").strip() for name in _SETTINGS]
    if not all(values):
        return None
    return values[0], values[1], values[2]


def _completions_url(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/chat/completions"):
        return root
    return f"{root}/chat/completions"


def _post(
    client: httpx.Client | None,
    url: str,
    api_key: str,
    payload: dict[str, object],
) -> object:
    headers = {"Authorization": f"Bearer {api_key}"}
    if client is None:
        with httpx.Client(timeout=90) as owned:
            response = owned.post(url, headers=headers, json=payload)
    else:
        response = client.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()


def _parse_brief(body: object) -> str:
    if not isinstance(body, dict):
        raise ValueError("Brief response was not JSON.")
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Brief response was not JSON.") from exc
    if not isinstance(content, str):
        raise ValueError("Brief response was not JSON.")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("Brief response was not JSON.") from exc
    brief = parsed.get("brief") if isinstance(parsed, dict) else None
    if not isinstance(brief, str) or not brief.strip():
        raise ValueError("Brief response did not include a brief.")
    return brief.strip()
