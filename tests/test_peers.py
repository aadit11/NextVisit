"""A last grade is better than most, typical, or worse than most of its peers."""

from nextvisit.peers import grade_rank, peer_standing
from nextvisit.places import nearby_places, one, peer_comparison


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


def test_the_batch_score_matches_the_single_restaurant_score() -> None:
    from nextvisit.model.predict import predict_new_york, serious_probabilities

    single = predict_new_york("30075445")["probability"]
    batch = serious_probabilities("new_york", ["30075445"])
    assert isinstance(single, float)
    assert abs(batch["30075445"] - single) < 1e-9


def test_cleaner_names_are_real_rows_in_the_same_group(monkeypatch) -> None:
    monkeypatch.setattr(
        "nextvisit.model.predict.serious_probabilities",
        lambda _city, ids: {item: 0.01 for item in ids},
    )
    origin = one("new_york", "30075445")
    assert origin is not None
    result = nearby_places(
        "new_york",
        "30075445",
        area="Bronx",
        cuisine="Bakery Products/Desserts",
        own_probability=0.5,
        origin_latitude=origin["latitude"],
        origin_longitude=origin["longitude"],
    )
    chosen = result["cleaner_peers"]
    assert result["nearby_basis"] == "cleaner"
    assert 1 <= len(chosen) <= 3
    assert all(item["restaurant_id"] != "30075445" for item in chosen)
    assert all("probability" not in item for item in chosen)
    assert all(isinstance(item["distance_miles"], float) and item["distance_miles"] >= 0 for item in chosen)
    for item in chosen:
        row = one("new_york", item["restaurant_id"])
        assert row is not None
        assert row["name"] == item["name"]
        assert row["grade"] == item["grade"]
        assert row["area"] == "Bronx"
        assert row["cuisine"] == "Bakery Products/Desserts"


def test_a_higher_score_lists_the_nearest_real_places(monkeypatch) -> None:
    monkeypatch.setattr(
        "nextvisit.model.predict.serious_probabilities",
        lambda _city, ids: {item: 0.9 for item in ids},
    )
    origin = one("new_york", "30075445")
    assert origin is not None
    result = nearby_places(
        "new_york",
        "30075445",
        area="Bronx",
        cuisine="Bakery Products/Desserts",
        own_probability=0.2,
        origin_latitude=origin["latitude"],
        origin_longitude=origin["longitude"],
    )
    chosen = result["cleaner_peers"]
    assert result["nearby_basis"] == "closest"
    assert 1 <= len(chosen) <= 3
    distances = [item["distance_miles"] for item in chosen]
    assert distances == sorted(distances)
    assert all(item["restaurant_id"] != "30075445" for item in chosen)
    assert all(item["latitude"] is not None and item["longitude"] is not None for item in chosen)


def test_an_unscored_restaurant_without_a_point_keeps_an_empty_list() -> None:
    result = nearby_places(
        "new_york",
        "30075445",
        area="Bronx",
        cuisine="Bakery Products/Desserts",
        own_probability=None,
    )
    assert result["nearby_basis"] is None
    assert result["cleaner_peers"] == []
