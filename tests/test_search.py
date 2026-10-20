"""A name search stays inside one city and keeps two ids as two rows."""

from fastapi.testclient import TestClient

from nextvisit.api.main import app

client = TestClient(app)


def test_two_restaurants_with_one_name_are_two_rows() -> None:
    response = client.get("/cities/new_york/restaurants", params={"q": "$1 pizza"})
    assert response.status_code == 200
    hits = [hit for hit in response.json() if hit["name"].casefold() == "$1 pizza"]
    assert len(hits) == 2
    assert hits[0]["restaurant_id"] != hits[1]["restaurant_id"]
    assert {hit["area"] for hit in hits}


def test_a_chicago_name_does_not_appear_in_new_york() -> None:
    new_york = client.get("/cities/new_york/restaurants", params={"q": "Portillo's"}).json()
    chicago = client.get("/cities/chicago/restaurants", params={"q": "Portillo's"}).json()
    assert new_york == []
    assert chicago
    assert all(hit["name"].casefold().startswith("portillo") for hit in chicago)
    chicago_ids = {hit["restaurant_id"] for hit in chicago}
    assert chicago_ids.isdisjoint({hit["restaurant_id"] for hit in new_york})


def test_an_unknown_city_is_not_searched() -> None:
    response = client.get("/cities/not_a_city/restaurants", params={"q": "cafe"})
    assert response.status_code == 404
