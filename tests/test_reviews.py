"""Diner accounts, reviews, and the list filters."""

import polars as pl
import pytest
from fastapi.testclient import TestClient

from nextvisit.api.main import app
from nextvisit.places import apply_filters

client = TestClient(app)


def test_filters_keep_the_named_clean_grade() -> None:
    frame = pl.DataFrame(
        {
            "restaurant_id": ["1", "2", "3"],
            "name": ["A", "B", "C"],
            "name_key": ["alpha pizza", "beta", "alpha diner"],
            "area": ["Manhattan", "Manhattan", "Brooklyn"],
            "cuisine": ["Pizza", "Thai", "Pizza"],
            "grade": ["A", "C", "A"],
            "serious": [False, True, False],
        }
    )
    kept = apply_filters(
        frame,
        needle="alpha",
        area="Manhattan",
        cuisine="pizza",
        grade="A",
        clean=True,
        limit=10,
    )
    assert kept["restaurant_id"].to_list() == ["1"]


def test_a_diner_can_register_and_review(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("NEXTVISIT_DB", str(tmp_path / "reviews.sqlite"))
    monkeypatch.setenv("NEXTVISIT_SESSION_SECRET", "test-secret")
    created = client.post(
        "/account/register",
        json={"name": "Ava", "email": "ava@example.com", "password": "correct-horse"},
    )
    assert created.status_code == 200
    token = created.json()["token"]
    denied = client.post(
        "/cities/new_york/restaurants/30075445/reviews",
        json={"stars": 4, "comment": "The counter was clean."},
    )
    assert denied.status_code == 401
    saved = client.post(
        "/cities/new_york/restaurants/30075445/reviews",
        json={"stars": 4, "comment": "The counter was clean."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["review_count"] == 1
    assert body["average_stars"] == 4
    assert body["reviews"][0]["author"] == "Ava"
    assert body["mine"]["stars"] == 4
    duplicate = client.post(
        "/account/register",
        json={"name": "Ava", "email": "ava@example.com", "password": "correct-horse"},
    )
    assert duplicate.status_code == 409
