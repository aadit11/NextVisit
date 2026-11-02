"""The inspections already on file for one restaurant, and the facts an account may use."""

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime

from nextvisit.peers import grade_rank

SHOWN_VISITS = 8

_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


@dataclass(frozen=True)
class VisitFact:
    date: str
    grade: str | None
    score: float | None
    codes: tuple[tuple[str, str | None], ...]


@dataclass(frozen=True)
class HistoryFacts:
    visits: tuple[VisitFact, ...]
    earlier_count: int
    repeated: tuple[tuple[str, str | None, int], ...]
    latest_only: tuple[tuple[str, str | None], ...]
    standing: str | None
    include_codes: bool
    score_trend: str | None = None


def raw_visits(records: list[dict[str, object]]) -> list[dict[str, object]]:
    """Newest first. Grade, score, and codes are whatever that city's row stores."""
    visits: list[dict[str, object]] = []
    for record in reversed(records):
        inspected = _iso(record.get("inspection_date"))
        if inspected is None:
            continue
        visits.append(
            {
                "date": inspected,
                "grade": _grade(record),
                "score": _score(record.get("score")),
                "codes": _codes(record),
            }
        )
    return visits


def assemble(
    city_id: str,
    visits: list[dict[str, object]],
    codebook: dict[str, str],
    *,
    score_trend: str | None = None,
) -> HistoryFacts:
    """Keep the newest visits. Repeated problems and best or worst use that same list."""
    include_codes = city_id != "austin"
    parsed = tuple(_with_text(visit, codebook, include_codes=include_codes) for visit in visits)
    shown = parsed[:SHOWN_VISITS]
    repeated, latest_only = _code_groups(shown) if include_codes else ((), ())
    return HistoryFacts(
        visits=shown,
        earlier_count=max(0, len(parsed) - len(shown)),
        repeated=repeated,
        latest_only=latest_only,
        standing=_standing(city_id, shown),
        include_codes=include_codes,
        score_trend=score_trend if score_trend in {"falling", "rising", "steady"} else None,
    )


def render_account(facts: HistoryFacts) -> str:
    """Write the account from the visit groups. A code cannot move into the wrong group."""
    blocks: list[str] = []
    if facts.standing == "worst":
        subject = "grade" if facts.include_codes else "score"
        blocks.append(f"The latest {subject} is the worst of the listed inspections.")
    elif facts.standing == "best":
        subject = "grade" if facts.include_codes else "score"
        blocks.append(f"The latest {subject} is the best of the listed inspections.")
    if facts.include_codes:
        repeated = [_label(text) for _code, text, _count in facts.repeated if text]
        latest = [_label(text) for _code, text in facts.latest_only if text]
        if repeated:
            blocks.append("Cited on more than one inspection:\n" + "\n".join(repeated))
        if latest:
            blocks.append("Cited only on the latest inspection:\n" + "\n".join(latest))
    elif facts.score_trend == "falling":
        blocks.append("Recent scores are falling.")
    elif facts.score_trend == "rising":
        blocks.append("Recent scores are rising.")
    elif facts.score_trend == "steady":
        blocks.append("Recent scores have stayed about the same.")
    return "\n\n".join(blocks)


def render_summary(facts: HistoryFacts) -> str:
    """One paragraph about the cited codes. Every phrase comes from those codes."""
    if not facts.include_codes or not facts.visits:
        return ""
    latest = facts.visits[0]
    latest_labels = [_short(text) for _code, text in latest.codes if text]
    repeated = [_short(text) for _code, text, _count in facts.repeated if text]
    added = [_short(text) for _code, text in facts.latest_only if text]
    earlier = _earlier_labels(facts)
    if not latest_labels and not repeated and not earlier:
        return ""
    if len(facts.visits) == 1:
        return f"The {_spoken_date(latest.date)} inspection cited {_series(latest_labels)}."
    sentences: list[str] = []
    if latest_labels:
        cited = f"The {_spoken_date(latest.date)} inspection cited {_count(len(latest_labels))} {_rules(len(latest_labels))}"
        if facts.standing == "worst":
            cited += ", and that grade is the worst of the visits listed."
        elif facts.standing == "best":
            cited += ", and that grade is the best of the visits listed."
        else:
            cited += "."
        sentences.append(cited)
    if repeated and len(facts.visits) >= 2:
        when = _spoken_date(facts.visits[1].date) if len(facts.visits) == 2 else "an earlier listed inspection"
        verb = "was" if len(repeated) == 1 else "were"
        sentences.append(
            f"{_count(len(repeated)).capitalize()} of those rules {verb} also cited on {when}: {_series(repeated)}."
        )
    if added:
        sentences.append(f"The latest visit added {_series(added)}.")
    if earlier:
        verb = "citation did" if len(earlier) == 1 else "citations did"
        sentences.append(f"An earlier listed inspection also cited {_series(earlier)}, and that {verb} not return.")
    return " ".join(sentences)


def _short(text: str) -> str:
    label = _label(text)
    return label[:1].lower() + label[1:]


def _rules(count: int) -> str:
    return "rule" if count == 1 else "rules"


def _count(count: int) -> str:
    words = (
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
        "twenty",
    )
    return words[count] if count < len(words) else str(count)


def _spoken_date(iso: str) -> str:
    parsed = date.fromisoformat(iso)
    return f"{_MONTHS[parsed.month - 1]} {parsed.day}, {parsed.year}"


def _earlier_labels(facts: HistoryFacts) -> list[str]:
    if len(facts.visits) < 2:
        return []
    latest = {code for code, _text in facts.visits[0].codes}
    seen: set[str] = set()
    labels: list[str] = []
    for visit in facts.visits[1:]:
        for code, text in visit.codes:
            if not text or code in latest or code in seen:
                continue
            seen.add(code)
            labels.append(_short(text))
    return labels


def _series(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + ", and " + items[-1]


def _label(text: str) -> str:
    """The short topic from a code title, without the rule's trailing conditions."""
    cleaned = re.sub(r"^#?\s*[0-9A-Za-z]+\.\s*", "", text).strip().rstrip(".")
    cleaned = re.split(r"\s*[:;]\s*|\s+/\s+|\s+-\s+", cleaned, maxsplit=1)[0]
    cleaned = re.sub(r"^(no|adequate|proper|properly)\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*/\s*", " and ", cleaned).strip(" .")
    if not cleaned:
        cleaned = text.strip().rstrip(".")
    return cleaned[:1].upper() + cleaned[1:].lower()


def _with_text(
    visit: dict[str, object],
    codebook: dict[str, str],
    *,
    include_codes: bool,
) -> VisitFact:
    codes: list[tuple[str, str | None]] = []
    if include_codes:
        raw_codes = visit.get("codes")
        if isinstance(raw_codes, list):
            for code in raw_codes:
                if not isinstance(code, str) or not code:
                    continue
                text = codebook.get(code)
                codes.append((code, text if isinstance(text, str) and text else None))
    return VisitFact(
        date=str(visit.get("date") or ""),
        grade=visit.get("grade") if isinstance(visit.get("grade"), str) else None,
        score=_score(visit.get("score")),
        codes=tuple(codes),
    )


def _code_groups(
    visits: tuple[VisitFact, ...],
) -> tuple[tuple[tuple[str, str | None, int], ...], tuple[tuple[str, str | None], ...]]:
    if len(visits) < 2:
        return (), ()
    counts: Counter[str] = Counter()
    text_for: dict[str, str | None] = {}
    for visit in visits:
        seen: set[str] = set()
        for code, text in visit.codes:
            text_for.setdefault(code, text)
            if code in seen:
                continue
            seen.add(code)
            counts[code] += 1
    repeated = tuple(
        (code, text_for.get(code), count)
        for code, count in counts.items()
        if count >= 2
    )
    latest_only = tuple(
        (code, text)
        for code, text in visits[0].codes
        if counts[code] == 1
    )
    return repeated, latest_only


def _standing(city_id: str, visits: tuple[VisitFact, ...]) -> str | None:
    if len(visits) < 2:
        return None
    if city_id == "austin":
        scores = [visit.score for visit in visits if visit.score is not None]
        if len(scores) < 2:
            return None
        latest, others = scores[0], scores[1:]
        if latest > max(others):
            return "best"
        if latest < min(others):
            return "worst"
        return None
    latest_rank = grade_rank(city_id, visits[0].grade)
    others = [grade_rank(city_id, visit.grade) for visit in visits[1:]]
    ranked = [rank for rank in others if rank is not None]
    if latest_rank is None or not ranked:
        return None
    if latest_rank < min(ranked):
        return "best"
    if latest_rank > max(ranked):
        return "worst"
    return None


def _iso(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and len(value) >= 10:
        return value[:10]
    return None


def _grade(record: dict[str, object]) -> str | None:
    for key in ("grade", "results", "result", "status"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _score(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _codes(record: dict[str, object]) -> list[str]:
    raw = record.get("violation_codes")
    if not isinstance(raw, list):
        return []
    return [str(code) for code in raw if code]
