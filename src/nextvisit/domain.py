"""Shared types. City adapters normalize their files into these."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Inspection:
    city: str
    restaurant_id: str
    name: str
    inspection_id: str
    inspection_date: date
    cuisine: str | None
    violation_code: str | None
    violation_description: str | None
    positive: bool


@dataclass(frozen=True)
class Example:
    city: str
    restaurant_id: str
    target_date: date
    label: int
    previous_positive: bool


@dataclass(frozen=True)
class Prediction:
    city: str
    restaurant_id: str
    name: str
    cuisine: str | None
    abstained: bool
    probability: float | None
    codes: tuple[str, ...]
