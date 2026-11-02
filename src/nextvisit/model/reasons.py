"""Plain reasons for the next-inspection sentence, taken from the model's inputs."""

_SERIOUS = {
    "new_york": "The next inspection is likely to include a critical violation again.",
    "chicago": "The next inspection is likely to be a Fail again.",
    "king_county": "The next inspection is likely to include a serious violation again.",
    "los_angeles": "The next inspection is likely to include a serious violation again.",
    "boston": "The next inspection is likely to be a fail again.",
    "san_francisco": "The next inspection is likely to be a Conditional Pass or a Closure again.",
    "austin": "The next routine score is likely to fall below 90 again.",
}


def decision_sentence(city_id: str, probability: float | None, abstained: bool) -> str | None:
    """The same sentence the card used to show, without a percentage."""
    if abstained or probability is None:
        return None
    if probability < 0.5:
        return "The next inspection is likely to come back clean."
    return _SERIOUS.get(city_id, "The next inspection is likely to find a serious problem again.")


def decision_reasons(
    *,
    city_id: str,
    previous_positive: bool,
    inspections: int,
    serious_count: int,
    trend: str | None,
    score: object,
    score_trend: str | None = None,
) -> list[str]:
    """Facts the classifier saw, in the order a diner can check them."""
    reasons: list[str] = []
    if previous_positive:
        reasons.append("The last inspection was a serious problem.")
    else:
        reasons.append("The last inspection was not a serious problem.")
    if inspections >= 2:
        reasons.append(f"{serious_count} of {inspections} inspections on file were serious.")
    if city_id == "austin":
        if score_trend == "falling":
            reasons.append("Recent scores are falling.")
        elif score_trend == "rising":
            reasons.append("Recent scores are rising.")
        elif score_trend == "steady":
            reasons.append("Recent scores have stayed about the same.")
    elif trend == "worse":
        reasons.append("Recent inspections are getting worse.")
    elif trend == "cleaner":
        reasons.append("Recent inspections are getting cleaner.")
    elif trend == "steady":
        reasons.append("Recent inspections have stayed about the same.")
    score_line = _score_line(city_id, score)
    if score_line:
        reasons.append(score_line)
    return reasons


def _score_line(city_id: str, score: object) -> str | None:
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    value = int(score) if float(score).is_integer() else score
    if city_id in {"los_angeles", "austin"}:
        side = "90 or above" if score >= 90 else "below 90"
        return f"The last score was {value}, which is {side}."
    if city_id == "new_york":
        if score <= 13:
            band = "0–13"
        elif score <= 27:
            band = "14–27"
        else:
            band = "28 or more"
        return f"The last score was {value}, in the {band} range."
    return None
