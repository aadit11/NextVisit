"""Local accounts and the reviews a diner writes for one restaurant."""

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def database_path() -> Path:
    return Path(os.environ.get("NEXTVISIT_DB", "data/app/nextvisit.sqlite"))


def connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    _migrate(connection)
    return connection


def register(name: str, email: str, password: str) -> dict[str, object]:
    clean_name = _name(name)
    clean_email = _email(email)
    _password(password)
    with connect() as connection:
        existing = connection.execute("SELECT id FROM users WHERE email = ?", (clean_email,)).fetchone()
        if existing is not None:
            raise ValueError("An account with that email already exists.")
        cursor = connection.execute(
            "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (clean_name, clean_email, _hash_password(password), _now()),
        )
        user_id = int(cursor.lastrowid)
    return {"token": issue_token(user_id), "name": clean_name, "email": clean_email}


def login(email: str, password: str) -> dict[str, object]:
    clean_email = _email(email)
    with connect() as connection:
        row = connection.execute(
            "SELECT id, name, email, password_hash FROM users WHERE email = ?",
            (clean_email,),
        ).fetchone()
    if row is None or not _password_matches(password, row["password_hash"]):
        raise PermissionError("Email or password is wrong.")
    return {"token": issue_token(int(row["id"])), "name": row["name"], "email": row["email"]}


def user_from_token(token: str | None) -> dict[str, object] | None:
    if not token:
        return None
    user_id = _read_token(token)
    if user_id is None or not database_path().exists():
        return None
    with connect() as connection:
        row = connection.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    return {"id": int(row["id"]), "name": row["name"], "email": row["email"]}


def save_review(city_id: str, restaurant_id: str, user_id: int, stars: int, comment: str) -> None:
    if stars not in range(1, 6):
        raise ValueError("A review needs a star rating from 1 to 5.")
    text = " ".join(comment.split())
    if len(text) > 800:
        raise ValueError("A review comment has to be 800 characters or fewer.")
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO reviews (city_id, restaurant_id, user_id, stars, comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(city_id, restaurant_id, user_id) DO UPDATE SET
                stars = excluded.stars,
                comment = excluded.comment,
                created_at = excluded.created_at
            """,
            (city_id, restaurant_id, user_id, stars, text, _now()),
        )


def reviews_for(
    city_id: str, restaurant_id: str, user_id: int | None = None
) -> dict[str, object]:
    if not database_path().exists():
        return {"average_stars": None, "review_count": 0, "mine": None, "reviews": []}
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT users.name AS author, reviews.stars, reviews.comment, reviews.created_at,
                   reviews.user_id
            FROM reviews
            JOIN users ON users.id = reviews.user_id
            WHERE reviews.city_id = ? AND reviews.restaurant_id = ?
            ORDER BY reviews.created_at DESC
            """,
            (city_id, restaurant_id),
        ).fetchall()
    mine = None
    published = []
    for row in rows:
        item = {
            "author": row["author"],
            "stars": int(row["stars"]),
            "comment": row["comment"],
            "created_at": row["created_at"],
        }
        published.append(item)
        if user_id is not None and int(row["user_id"]) == user_id:
            mine = {"stars": item["stars"], "comment": item["comment"]}
    average = None
    if published:
        average = round(sum(item["stars"] for item in published) / len(published), 2)
    return {
        "average_stars": average,
        "review_count": len(published),
        "mine": mine,
        "reviews": published,
    }


def stats_for(city_id: str, restaurant_ids: list[str]) -> dict[str, tuple[float, int]]:
    if not restaurant_ids or not database_path().exists():
        return {}
    marks = ",".join("?" for _ in restaurant_ids)
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT restaurant_id, AVG(stars) AS average_stars, COUNT(*) AS review_count
            FROM reviews
            WHERE city_id = ? AND restaurant_id IN ({marks})
            GROUP BY restaurant_id
            """,
            (city_id, *restaurant_ids),
        ).fetchall()
    return {
        row["restaurant_id"]: (round(float(row["average_stars"]), 2), int(row["review_count"]))
        for row in rows
    }


def issue_token(user_id: int) -> str:
    expires = int(datetime.now(timezone.utc).timestamp()) + 14 * 24 * 60 * 60
    payload = f"{user_id}.{expires}"
    signature = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def _read_token(token: str) -> int | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = f"{parts[0]}.{parts[1]}"
    expected = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, parts[2]):
        return None
    try:
        user_id = int(parts[0])
        expires = int(parts[1])
    except ValueError:
        return None
    if expires < int(datetime.now(timezone.utc).timestamp()):
        return None
    return user_id


def _secret() -> bytes:
    configured = os.environ.get("NEXTVISIT_SESSION_SECRET", "").strip()
    if configured:
        return configured.encode()
    path = database_path().parent / "session.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(secrets.token_hex(32), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip().encode()


def _migrate(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY,
            city_id TEXT NOT NULL,
            restaurant_id TEXT NOT NULL,
            user_id INTEGER NOT NULL REFERENCES users(id),
            stars INTEGER NOT NULL,
            comment TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (city_id, restaurant_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS osm_cache (
            city_id TEXT NOT NULL,
            restaurant_id TEXT NOT NULL,
            cuisine TEXT,
            hours TEXT,
            latitude REAL,
            longitude REAL,
            PRIMARY KEY (city_id, restaurant_id)
        );
        """
    )


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{salt.hex()}:{digest.hex()}"


def _password_matches(password: str, stored: str) -> bool:
    salt_hex, _, digest_hex = stored.partition(":")
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return hmac.compare_digest(digest, expected)


def _name(value: str) -> str:
    text = " ".join(value.split())
    if not text or len(text) > 80:
        raise ValueError("A name has to be between 1 and 80 characters.")
    return text


def _email(value: str) -> str:
    text = value.strip().lower()
    if "@" not in text or text.startswith("@") or text.endswith("@") or len(text) > 200:
        raise ValueError("Enter an email address.")
    return text


def _password(value: str) -> None:
    if len(value) < 8:
        raise ValueError("A password has to be at least 8 characters.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
