"""Whether recent inspections are getting cleaner or worse.

Each visit is the city's own serious-problem flag: true means that visit
found the bad outcome. The window is the last four visits already on file.
One visit is not a trend.
"""

RECENT_WINDOW = 4


def recent_trend(serious: list[bool]) -> dict[str, object]:
    """Compare the earlier half of the recent window with the later half."""
    window = [bool(flag) for flag in serious[-RECENT_WINDOW:]]
    count = len(window)
    serious_count = sum(window)
    trend = None
    if count >= 2:
        midpoint = count // 2
        earlier = sum(window[:midpoint]) / midpoint
        later = sum(window[midpoint:]) / (count - midpoint)
        if later > earlier:
            trend = "worse"
        elif later < earlier:
            trend = "cleaner"
        else:
            trend = "steady"
    return {
        "trend": trend,
        "recent_visit_count": count,
        "recent_serious_count": serious_count,
    }


def score_direction(scores: list[object]) -> str | None:
    """Whether recent Austin scores are falling. A higher score is cleaner."""
    values = [float(score) for score in scores if isinstance(score, (int, float)) and not isinstance(score, bool)]
    window = values[-RECENT_WINDOW:]
    if len(window) < 2:
        return None
    midpoint = len(window) // 2
    earlier = sum(window[:midpoint]) / midpoint
    later = sum(window[midpoint:]) / (len(window) - midpoint)
    if later < earlier:
        return "falling"
    if later > earlier:
        return "rising"
    return "steady"
