"""The inspections already on file for one restaurant, and the facts an account may use."""

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime

from nextvisit.brief.faithfulness import _TOPICS
from nextvisit.peers import grade_rank

SHOWN_VISITS = 8
_MAX_SENTENCES = 12

_GRADE_PHRASES = (
    "Needs To Improve",
    "Pass w/ Conditions",
    "Conditional Pass",
    "90 or above",
    "Below 90",
    "Excellent",
    "Closure",
    "PassViol",
)

_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")
_CODE = re.compile(r"\b\d{2}[A-Z]\b")
_HASH_CODE = re.compile(r"#\s*0*(\d+)\b")
_CLAIMS = (
    ("latest", re.compile(r"only on the latest|only the latest", re.I)),
    ("repeated", re.compile(r"more than one|more than once", re.I)),
)
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
_AGE = re.compile(
    r"\b(?:today|yesterday|[a-z]+ (?:day|days|week|weeks|month|months|year|years) ago)\b",
    re.I,
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

    @property
    def code_text(self) -> str:
        if not self.include_codes:
            return ""
        parts: list[str] = []
        for visit in self.visits:
            for _code, text in visit.codes:
                if text:
                    parts.append(text)
        return "\n".join(parts)


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
    sentences: list[str] = []
    if facts.include_codes:
        repeated = [_plain(text) for _code, text, _count in facts.repeated if text]
        latest = [_plain(text) for _code, text in facts.latest_only if text]
        if repeated:
            sentences.append("Cited on more than one of these inspections: " + _series(repeated) + ".")
        if latest:
            sentences.append("Cited only on the latest inspection: " + _series(latest) + ".")
    elif facts.score_trend == "falling":
        sentences.append("Recent scores are falling.")
    elif facts.score_trend == "rising":
        sentences.append("Recent scores are rising.")
    elif facts.score_trend == "steady":
        sentences.append("Recent scores have stayed about the same.")
    if facts.standing == "worst":
        subject = "grade" if facts.include_codes else "score"
        sentences.append(f"The latest {subject} is the worst of the listed inspections.")
    elif facts.standing == "best":
        subject = "grade" if facts.include_codes else "score"
        sentences.append(f"The latest {subject} is the best of the listed inspections.")
    return " ".join(sentences)


def _plain(text: str) -> str:
    cleaned = re.sub(r"^#?\s*[0-9A-Za-z]+\.\s*", "", text).strip().rstrip(".")
    if not cleaned:
        return text.strip().rstrip(".")
    return cleaned[:1].upper() + cleaned[1:].lower()


def _series(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + ", and " + items[-1]


def history_errors(account: str, facts: HistoryFacts) -> list[str]:
    """A date, grade, score, or code in the account must be one of the listed visits."""
    text = account.strip()
    sentences = [part for part in re.split(r"[.!?]+", text) if part.strip()]
    if not sentences:
        return ["History was empty."]
    if len(sentences) > _MAX_SENTENCES:
        return ["History is longer than a few sentences."]

    errors: list[str] = []
    dates = {visit.date for visit in facts.visits}
    for found in _ISO_DATE.findall(text):
        if found not in dates:
            errors.append(f"History mentions {found}, which is not one of these inspections.")
    months = {_month(visit.date) for visit in facts.visits}
    for index, month in enumerate(_MONTHS, start=1):
        if re.search(rf"\b{month}\b", text, re.I) and index not in months:
            errors.append(f"History mentions {month}, which is not one of these inspections.")
    if _AGE.search(text):
        errors.append("History gives an age instead of the inspection date.")
    errors.extend(_number_errors(text, facts))
    errors.extend(_grade_errors(text, facts))
    errors.extend(_code_errors(text, facts))
    errors.extend(_topic_errors(text, facts))
    if re.search(r"\bbest\b", text, re.I) and facts.standing != "best":
        errors.append("History says this inspection is the best on the list.")
    if re.search(r"\bworst\b", text, re.I) and facts.standing != "worst":
        errors.append("History says this inspection is the worst on the list.")
    if re.search(r"more than one|more than once", text, re.I) and not facts.repeated:
        errors.append("History says a problem was cited on more than one inspection.")
    if re.search(r"only on the latest|only the latest", text, re.I) and not facts.latest_only:
        errors.append("History says a problem appears only on the latest inspection.")
    errors.extend(_assignment_errors(text, facts))
    if re.search(r"\bnext inspection\b", text, re.I):
        errors.append("History mentions a next inspection.")
    if re.search(r"\bpercent\b|%", text, re.I):
        errors.append("History mentions a probability.")
    if re.search(r"\bfalling\b|\bfallen\b", text, re.I) and facts.score_trend != "falling":
        errors.append("History says the scores are falling.")
    if re.search(r"\brising\b|\brisen\b", text, re.I) and facts.score_trend != "rising":
        errors.append("History says the scores are rising.")
    return errors


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


def _month(iso_date: str) -> int | None:
    match = re.match(r"\d{4}-(\d{2})-\d{2}", iso_date)
    if match is None:
        return None
    month = int(match.group(1))
    return month if 1 <= month <= 12 else None


def _number_errors(account: str, facts: HistoryFacts) -> list[str]:
    allowed = _allowed_numbers(facts)
    errors: list[str] = []
    for token in _NUMBER.findall(account):
        normalized = str(int(token)) if re.fullmatch(r"\d+", token) else token
        if normalized not in allowed and token not in allowed:
            errors.append(f"History mentions {token}, which is not on these inspections.")
    return errors


def _allowed_numbers(facts: HistoryFacts) -> set[str]:
    allowed: set[str] = set()

    def add(token: str) -> None:
        allowed.add(token)
        if re.fullmatch(r"\d+", token):
            allowed.add(str(int(token)))

    add(str(len(facts.visits)))
    if facts.earlier_count:
        add(str(facts.earlier_count))
    for visit in facts.visits:
        for part in re.findall(r"\d+", visit.date):
            add(part)
        if visit.score is not None:
            if float(visit.score).is_integer():
                add(str(int(visit.score)))
            add(str(visit.score))
        if facts.include_codes:
            for code, text in visit.codes:
                for part in re.findall(r"\d+(?:\.\d+)?", code):
                    add(part)
                if text:
                    for part in re.findall(r"\d+(?:\.\d+)?", text):
                        add(part)
    for _code, _text, count in facts.repeated:
        add(str(count))
    return allowed


def _grade_errors(account: str, facts: HistoryFacts) -> list[str]:
    allowed = {visit.grade.casefold() for visit in facts.visits if visit.grade}
    errors: list[str] = []
    scratch = account.casefold()
    for phrase in sorted(_GRADE_PHRASES, key=len, reverse=True):
        token = phrase.casefold()
        if re.search(rf"(?<!\w){re.escape(token)}(?!\w)", scratch):
            if token not in allowed:
                errors.append(f"History mentions {phrase}, which is not a grade on these inspections.")
            scratch = re.sub(rf"(?<!\w){re.escape(token)}(?!\w)", " ", scratch)
    for word in ("good", "okay", "pass", "fail"):
        if re.search(rf"\b(?:grade|an|a)\s+{word}\b", scratch) and word not in allowed:
            errors.append(f"History mentions {word}, which is not a grade on these inspections.")
    for letter in re.findall(r"\b(?:grade|[a])\s+([abc])\b", account, re.I):
        if letter.casefold() not in allowed:
            errors.append(f"History mentions grade {letter.upper()}, which is not on these inspections.")
    for letter in re.findall(r"\b([abc])\s+grade\b", account, re.I):
        if letter.casefold() not in allowed:
            errors.append(f"History mentions grade {letter.upper()}, which is not on these inspections.")
    return errors


def _code_errors(account: str, facts: HistoryFacts) -> list[str]:
    supplied = {code.upper() for visit in facts.visits for code, _text in visit.codes}
    errors: list[str] = []
    for found in _CODE.findall(account):
        if not facts.include_codes or found.upper() not in supplied:
            errors.append(f"History mentions code {found}, which is not on these inspections.")
    if not facts.include_codes and re.search(r"violation code", account, re.I):
        errors.append("History mentions a violation code.")
    return errors


def _topic_errors(account: str, facts: HistoryFacts) -> list[str]:
    errors: list[str] = []
    for name, pattern in _TOPICS:
        if pattern.search(account) and not pattern.search(facts.code_text):
            errors.append(f"History mentions {name}, which these inspections do not describe.")
    return errors


def _assignment_errors(account: str, facts: HistoryFacts) -> list[str]:
    """A named problem has to sit in the group the sentence gives it."""
    if not facts.include_codes:
        return []
    refs = _code_refs(facts)
    errors: list[str] = []
    for sentence in re.split(r"[.!?]+", account):
        for claim, scope in _claim_scopes(sentence):
            for code, bucket in _mentions(scope, refs):
                if bucket == claim:
                    continue
                if claim == "latest":
                    errors.append(f"History says {code} appears only on the latest inspection.")
                else:
                    errors.append(f"History says {code} was cited on more than one inspection.")
    return errors


def _claim_scopes(sentence: str) -> list[tuple[str, str]]:
    found: list[tuple[int, str]] = []
    for name, pattern in _CLAIMS:
        match = pattern.search(sentence)
        if match:
            found.append((match.start(), name))
    found.sort()
    scopes: list[tuple[str, str]] = []
    for index, (start, name) in enumerate(found):
        begin = 0 if index == 0 else start
        end = found[index + 1][0] if index + 1 < len(found) else len(sentence)
        scopes.append((name, sentence[begin:end]))
    return scopes


def _code_refs(facts: HistoryFacts) -> list[tuple[str, str, set[str], str | None]]:
    repeated = {code for code, _text, _count in facts.repeated}
    latest = {code for code, _text in facts.latest_only}
    seen: dict[str, tuple[str, str | None]] = {}
    for visit in facts.visits:
        for code, text in visit.codes:
            if code in repeated:
                bucket = "repeated"
            elif code in latest:
                bucket = "latest"
            else:
                bucket = "other"
            current = seen.get(code)
            if current is None or (current[1] is None and text):
                seen[code] = (bucket, text)
    refs: list[tuple[str, str, set[str], str | None]] = []
    for code, (bucket, text) in seen.items():
        numbers = {str(int(part)) for part in re.findall(r"\d+", code)}
        refs.append((code, bucket, numbers, _phrase(text)))
    return refs


def _phrase(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"^#?\s*\d+\.?\s*", "", text).strip(" .")
    if len(cleaned) < 20:
        return None
    return cleaned.casefold()


def _mentions(
    scope: str,
    refs: list[tuple[str, str, set[str], str | None]],
) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    scratch = scope.casefold()
    for code, bucket, _numbers, phrase in sorted(refs, key=lambda item: len(item[3] or ""), reverse=True):
        if phrase and phrase in scratch:
            found.append((code, bucket))
            scratch = scratch.replace(phrase, " ")
    for match in _HASH_CODE.finditer(scope):
        number = str(int(match.group(1)))
        found.extend((code, bucket) for code, bucket, numbers, _phrase in refs if number in numbers)
    for code, bucket, _numbers, _phrase in refs:
        if re.search(rf"(?<!\w){re.escape(code)}(?!\w)", scope, re.I):
            found.append((code, bucket))
    unique: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in found:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique
