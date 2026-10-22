"""A last grade is better than most, typical, or worse than most of its peers."""

from nextvisit.peers import grade_rank, peer_standing
from nextvisit.places import peer_comparison


def test_an_a_is_cleaner_than_a_c() -> None:
    assert grade_rank("new_york", "A") < grade_rank("new_york", "C")


def test_a_pending_grade_is_not_ranked() -> None:
    assert grade_rank("new_york", "Z") is None
    assert grade_rank("new_york", None) is None


def test_better_than_most_needs_more_than_half() -> None:
    assert peer_standing(0, [2, 2, 1]) == "better"
    assert peer_standing(0, [0, 0, 1]) == "typical"


def test_worse_than_most_when_the_others_are_cleaner() -> None:
    assert peer_standing(2, [0, 0, 1]) == "worse"


def test_one_other_place_can_decide_the_standing() -> None:
    assert peer_standing(0, [2]) == "better"
    assert peer_standing(0, []) is None


def test_bronx_bakeries_are_counted_for_morris_park() -> None:
    result = peer_comparison(
        "new_york",
        "30075445",
        area="Bronx",
        cuisine="Bakery Products/Desserts",
        grade="A",
    )
    assert result["peer_count"] > 1
    assert result["peer_graded_count"] >= 2
    assert result["peer_standing"] in {"better", "typical", "worse"}
