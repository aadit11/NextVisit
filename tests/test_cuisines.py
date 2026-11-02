import polars as pl

from nextvisit.cuisines import _match, cuisine_from_name, tidy_cuisine


def test_osm_cuisine_tag_becomes_a_label() -> None:
    assert tidy_cuisine("pizza;italian") == "Pizza"
    assert tidy_cuisine("tex-mex") == "Tex-Mex"
    assert tidy_cuisine("yes") is None


def test_match_keeps_the_nearby_name_and_drops_a_far_one() -> None:
    frame = pl.DataFrame(
        {
            "restaurant_id": ["near", "far"],
            "name": ["Chick Fil A", "County Cafeteria"],
            "latitude": [30.27, 30.50],
            "longitude": [-97.74, -97.74],
        }
    )
    places = [
        {
            "name_key": "chick fil a",
            "latitude": 30.271,
            "longitude": -97.741,
            "cuisine": "Chicken",
        }
    ]
    rows = _match(frame, places)
    assert rows == [{"restaurant_id": "near", "cuisine": "Chicken"}]


def test_a_store_number_still_matches_the_chain_name() -> None:
    frame = pl.DataFrame(
        {
            "restaurant_id": ["store"],
            "name": ["Chipotle Mexican Grill 214"],
            "latitude": [30.27],
            "longitude": [-97.74],
        }
    )
    places = [
        {
            "name_key": "chipotle",
            "latitude": 30.271,
            "longitude": -97.741,
            "cuisine": "Mexican",
        }
    ]
    assert _match(frame, places) == [{"restaurant_id": "store", "cuisine": "Mexican"}]


def test_a_name_that_says_pizza_is_pizza_without_a_map_hit() -> None:
    frame = pl.DataFrame(
        {
            "restaurant_id": ["shop"],
            "name": ["Joe's Pizza"],
            "latitude": [30.27],
            "longitude": [-97.74],
        }
    )
    assert _match(frame, []) == [{"restaurant_id": "shop", "cuisine": "Pizza"}]


def test_plurals_and_cafe_in_the_name_count() -> None:
    assert cuisine_from_name("La Montana Tacos") == "Mexican"
    assert cuisine_from_name("Cheddars Casual Cafe #2031") == "Cafe"
    assert cuisine_from_name("Round Rock Donuts") == "Donuts"
