"""Compare one last grade with the same cuisine in the same area.

The comparison is a count. A lower rank is a cleaner grade. Grades the city
does not order, such as a pending New York grade, stay out of the ranking.
"""

from nextvisit.cities.boston import FAIL_RESULTS, PASS_RESULTS

# Lower is cleaner. Pending, unrated, and missing grades are absent on purpose.
_RANKS: dict[str, dict[str, int]] = {
    "new_york": {"A": 0, "B": 1, "C": 2},
    "chicago": {"Pass": 0, "Pass w/ Conditions": 1, "Fail": 2},
    "king_county": {"Excellent": 0, "Good": 1, "Okay": 2, "Needs To Improve": 3},
    "los_angeles": {"A": 0, "B": 1, "C": 2},
    "san_francisco": {"Pass": 0, "Conditional Pass": 1, "Closure": 2},
    "austin": {"90 or above": 0, "Below 90": 1},
    "boston": {
        **{result: 0 for result in PASS_RESULTS - {"PassViol"}},
        "PassViol": 1,
        **{result: 2 for result in FAIL_RESULTS},
    },
}


def grade_rank(city_id: str, grade: str | None) -> int | None:
    if not grade:
        return None
    return _RANKS.get(city_id, {}).get(grade)


def peer_standing(own_rank: int | None, other_ranks: list[int]) -> str | None:
    """Better than most, typical, or worse than most of the other graded places."""
    if own_rank is None or not other_ranks:
        return None
    better = sum(rank > own_rank for rank in other_ranks)
    worse = sum(rank < own_rank for rank in other_ranks)
    half = len(other_ranks) / 2
    if better > half:
        return "better"
    if worse > half:
        return "worse"
    return "typical"
