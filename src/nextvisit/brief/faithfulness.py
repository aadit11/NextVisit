"""Reject a hygiene brief that adds a fact the record did not supply."""

import re
from dataclasses import dataclass
from datetime import date

COUNT_WORDS = (
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

# A hit in the brief is allowed only when the supplied code text hits the same topic.
_TOPICS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pests", re.compile(r"roach|rodent|mouse|mice|\brats?\b|vermin|pest|fruit fly|\bflies\b|insects?|harborage", re.I)),
    ("handwashing", re.compile(r"hand\s?wash|handwashing|\bsoap\b|hand sink", re.I)),
    ("temperature", re.compile(r"cold hold|hot hold|refrigerat|danger zone|\btemperature\b", re.I)),
    ("plumbing", re.compile(r"\bplumbing\b|sewage|backflow", re.I)),
    ("restrooms", re.compile(r"restroom|\btoilet\b|bathroom", re.I)),
    ("garbage", re.compile(r"\bgarbage\b|\brefuse\b", re.I)),
)

_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_AGE = re.compile(r"\b(?:today|yesterday|[a-z]+ (?:day|days|week|weeks|month|months|year|years) ago)\b", re.I)
_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")
_CODE = re.compile(r"\b\d{2}[A-Z]\b")
_LETTER_GRADE = re.compile(r"\b(?:grade|an|this)\s+([ABCabc])\b", re.I)
_MAX_SENTENCES = 4


@dataclass(frozen=True)
class BriefFacts:
    inspection_date: str | None = None
    grade: str | None = None
    score: float | None = None
    trend: str | None = None
    recent_visit_count: int = 0
    recent_serious_count: int = 0
    peer_count: int = 0
    peer_graded_count: int = 0
    peer_standing: str | None = None
    peer_cuisine: str | None = None
    peer_area: str | None = None
    codes: tuple[tuple[str, str | None], ...] = ()
    include_codes: bool = True
    problem_kinds: tuple[str, ...] = ()
    score_trend: str | None = None
    today: date | None = None
    next_inspection: str | None = None
    reasons: tuple[str, ...] = ()

    @property
    def inspection_age(self) -> str | None:
        return inspection_age_sentence(self.inspection_date, self.today)

    @property
    def code_text(self) -> str:
        if not self.include_codes:
            return ""
        return "\n".join(text for _, text in self.codes if text)


def inspection_age_sentence(iso_date: str | None, today: date | None = None) -> str | None:
    """Same wording the card uses for how old the inspection is."""
    inspected = _parse_date(iso_date)
    if inspected is None:
        return None
    current = today or date.today()
    days = (current - inspected).days
    if days < 0:
        return None
    if days == 0:
        return "Inspected today."
    if days == 1:
        return "Inspected yesterday."
    if days < 7:
        return f"Inspected {days} days ago."
    if days < 30:
        return f"Inspected {_span(days // 7, 'week')} ago."
    if days < 365:
        months = max(1, round(days / 30.44))
        if months >= 12:
            return "Inspected one year ago."
        return f"Inspected {_span(months, 'month')} ago."
    return f"Inspected {_span(max(1, round(days / 365.25)), 'year')} ago."


def brief_errors(brief: str, facts: BriefFacts) -> list[str]:
    """A date, grade, score, trend, kind, or code must be one of the supplied facts."""
    text = brief.strip()
    sentences = [part for part in re.split(r"[.!?]+", text) if part.strip()]
    if not sentences:
        return ["Brief was empty."]
    if len(sentences) > _MAX_SENTENCES:
        return ["Brief is longer than a few sentences."]

    errors: list[str] = []
    errors.extend(_date_errors(text, facts))
    errors.extend(_number_errors(text, facts))
    errors.extend(_grade_errors(text, facts))
    errors.extend(_trend_errors(text, facts))
    errors.extend(_kind_errors(text, facts))
    errors.extend(_code_errors(text, facts))
    errors.extend(_topic_errors(text, facts))
    errors.extend(_score_trend_errors(text, facts))
    errors.extend(_outcome_errors(text, facts))
    if re.search(r"\bpercent\b|%", text, re.I):
        errors.append("Brief mentions a probability.")
    return errors


def _parse_date(iso_date: str | None) -> date | None:
    if not iso_date:
        return None
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", iso_date)
    if match is None:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _span(count: int, unit: str) -> str:
    word = COUNT_WORDS[count] if 0 <= count < len(COUNT_WORDS) else str(count)
    suffix = "" if count == 1 else "s"
    return f"{word} {unit}{suffix}"


def _date_errors(brief: str, facts: BriefFacts) -> list[str]:
    errors: list[str] = []
    for found in _ISO_DATE.findall(brief):
        if found != facts.inspection_date:
            errors.append(f"Brief mentions {found}, which is not the inspection date.")
    inspected = _parse_date(facts.inspection_date)
    for index, month in enumerate(_MONTHS, start=1):
        if re.search(rf"\b{month}\b", brief, re.I) and (inspected is None or inspected.month != index):
            errors.append(f"Brief mentions {month}, which is not the inspection month.")
    age = facts.inspection_age or ""
    for phrase in _AGE.findall(brief):
        if phrase.casefold() not in age.casefold():
            errors.append(f"Brief says {phrase}, which is not the age of this inspection.")
    return errors


def _allowed_numbers(facts: BriefFacts) -> set[str]:
    allowed: set[str] = set()

    def add(token: str) -> None:
        allowed.add(token)
        if re.fullmatch(r"\d+", token):
            allowed.add(str(int(token)))

    if facts.score is not None:
        if float(facts.score).is_integer():
            add(str(int(facts.score)))
        add(str(facts.score))
    for count in (
        facts.peer_count,
        facts.peer_graded_count,
        facts.recent_visit_count,
        facts.recent_serious_count,
    ):
        if count:
            add(str(count))
    if facts.inspection_date:
        for part in re.findall(r"\d+", facts.inspection_date):
            add(part)
    for part in re.findall(r"\d+(?:\.\d+)?", facts.code_text):
        add(part)
    for source in (facts.next_inspection, *facts.reasons):
        if source:
            for part in re.findall(r"\d+(?:\.\d+)?", source):
                add(part)
    return allowed


def _number_errors(brief: str, facts: BriefFacts) -> list[str]:
    allowed = _allowed_numbers(facts)
    errors: list[str] = []
    for token in _NUMBER.findall(brief):
        normalized = str(int(token)) if re.fullmatch(r"\d+", token) else token
        if normalized not in allowed and token not in allowed:
            errors.append(f"Brief mentions {token}, which is not on the record.")
    return errors


def _grade_errors(brief: str, facts: BriefFacts) -> list[str]:
    errors: list[str] = []
    supplied = (facts.grade or "").casefold()
    for mention in _LETTER_GRADE.findall(brief):
        if mention.casefold() != supplied:
            errors.append(f"Brief mentions grade {mention.upper()}, which is not this inspection's grade.")
    return errors


def _trend_errors(brief: str, facts: BriefFacts) -> list[str]:
    errors: list[str] = []
    if re.search(r"\bcleaner\b", brief, re.I) and facts.trend != "cleaner":
        errors.append("Brief says the inspections are getting cleaner.")
    getting_worse = re.search(r"getting worse", brief, re.I)
    worse_than_most = re.search(r"worse than most", brief, re.I)
    if getting_worse and facts.trend != "worse":
        errors.append("Brief says the inspections are getting worse.")
    if worse_than_most and facts.peer_standing != "worse":
        errors.append("Brief says the grade is worse than most.")
    if (
        re.search(r"\bworse\b", brief, re.I)
        and not getting_worse
        and not worse_than_most
        and facts.trend != "worse"
    ):
        errors.append("Brief says the inspections are getting worse.")
    if re.search(r"\bsteady\b", brief, re.I) and facts.trend != "steady":
        errors.append("Brief says the inspections are steady.")
    if re.search(r"better than most", brief, re.I) and facts.peer_standing != "better":
        errors.append("Brief says the grade is better than most.")
    if re.search(r"\btypical\b", brief, re.I) and facts.peer_standing != "typical":
        errors.append("Brief says the grade is typical.")
    if re.search(r"stayed clean", brief, re.I) and facts.recent_serious_count != 0:
        errors.append("Brief says the recent inspections stayed clean.")
    if re.search(r"serious problem", brief, re.I) and facts.recent_serious_count <= 0:
        supplied = " ".join(part for part in (facts.next_inspection, *facts.reasons) if part).casefold()
        if "serious problem" not in supplied:
            errors.append("Brief mentions a serious problem the recent inspections do not show.")
    return errors


def _kind_errors(brief: str, facts: BriefFacts) -> list[str]:
    supplied = {kind.casefold() for kind in facts.problem_kinds}
    errors: list[str] = []
    for kind in ("illness", "paperwork"):
        if re.search(rf"\b{kind}\b", brief, re.I) and kind not in supplied:
            errors.append(f"Brief mentions {kind}, which is not a kind on this record.")
    return errors


def _code_errors(brief: str, facts: BriefFacts) -> list[str]:
    supplied = {code.upper() for code, _ in facts.codes}
    errors: list[str] = []
    for found in _CODE.findall(brief):
        if not facts.include_codes or found.upper() not in supplied:
            errors.append(f"Brief mentions code {found}, which is not on this record.")
    if not facts.include_codes and re.search(r"violation code", brief, re.I):
        errors.append("Brief mentions a violation code.")
    return errors


def _score_trend_errors(brief: str, facts: BriefFacts) -> list[str]:
    errors: list[str] = []
    if re.search(r"\bfalling\b|\bfallen\b", brief, re.I) and facts.score_trend != "falling":
        errors.append("Brief says the scores are falling.")
    if re.search(r"\brising\b|\brisen\b", brief, re.I) and facts.score_trend != "rising":
        errors.append("Brief says the scores are rising.")
    return errors


def _outcome_errors(brief: str, facts: BriefFacts) -> list[str]:
    verdict = (facts.next_inspection or "").casefold()
    if not verdict:
        return []
    errors: list[str] = []
    clean_claim = re.search(r"come back clean", brief, re.I)
    serious_claim = re.search(r"serious violation again|serious problem again|below 90 again|\bfail again\b", brief, re.I)
    if "come back clean" in verdict and serious_claim:
        errors.append("Brief says the next inspection is likely to find a serious problem.")
    if "come back clean" not in verdict and clean_claim:
        errors.append("Brief says the next inspection is likely to come back clean.")
    return errors


def _topic_errors(brief: str, facts: BriefFacts) -> list[str]:
    errors: list[str] = []
    for name, pattern in _TOPICS:
        if pattern.search(brief) and not pattern.search(facts.code_text):
            errors.append(f"Brief mentions {name}, which the record does not describe.")
    return errors
