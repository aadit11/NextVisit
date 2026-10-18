"""Score one New York restaurant from inspections already on disk."""

from datetime import date, timedelta
from functools import lru_cache

import joblib
import polars as pl

from nextvisit.cities.new_york import RAW_PATH, SPEC
from nextvisit.model.train import FeaturePreprocessor
from nextvisit.prepare.collapse import INSPECTIONS_PATH
from nextvisit.prepare.features import assert_features_before_target

MODEL_PATH = "artifacts/new_york/model.joblib"


class UnknownRestaurant(LookupError):
    """This CAMIS is not in the New York extract."""


def predict_new_york(camis: str) -> dict[str, object]:
    visits = _inspections().filter(pl.col("camis") == camis).sort("inspection_date")
    if visits.height == 0:
        if camis not in _known_camis():
            raise UnknownRestaurant(camis)
        name = _raw_name(camis)
        return {
            "city": SPEC.id,
            "restaurant_id": camis,
            "name": name,
            "cuisine": None,
            "abstained": True,
            "probability": None,
            "label": SPEC.label,
            "codes": [],
            "work_order": [],
        }

    records = visits.to_dicts()
    latest = records[-1]
    as_of = _as_of(latest["inspection_date"])
    assert_features_before_target(
        [visit["inspection_date"] for visit in records],
        as_of,
    )
    features = pl.DataFrame([_feature_row(records, as_of)])
    bundle = _model()
    probability = float(bundle["model"].predict_proba(bundle["preprocessor"].transform(features))[0, 1])
    return {
        "city": SPEC.id,
        "restaurant_id": camis,
        "name": latest["name"],
        "cuisine": latest["cuisine"],
        "abstained": False,
        "probability": probability,
        "label": SPEC.label,
        "codes": _history_codes(records),
        "work_order": [],
    }


def _feature_row(visits: list[dict[str, object]], as_of: date) -> dict[str, object]:
    previous = visits[-1]
    last_positive = next(
        (visit["inspection_date"] for visit in reversed(visits) if visit["positive"]),
        None,
    )
    return {
        "cuisine": previous["cuisine"],
        "borough": previous["borough"],
        "previous_grade": previous["grade"],
        "days_since_previous": (as_of - previous["inspection_date"]).days,
        "previous_positive": bool(previous["positive"]),
        "previous_score": previous["score"],
        "prior_inspection_count": len(visits),
        "prior_positive_count": sum(bool(visit["positive"]) for visit in visits),
        "prior_violation_count": sum(_code_count(visit) for visit in visits),
        "previous_violation_count": _code_count(previous),
        "days_since_last_positive": (
            None if last_positive is None else (as_of - last_positive).days
        ),
    }


def _history_codes(visits: list[dict[str, object]]) -> list[str]:
    seen: list[str] = []
    for visit in reversed(visits):
        for code in visit["violation_codes"] or []:
            if code not in seen:
                seen.append(code)
    return seen


def _as_of(last_inspection: date) -> date:
    today = date.today()
    if today <= last_inspection:
        return last_inspection + timedelta(days=1)
    return today


def _code_count(visit: dict[str, object]) -> int:
    codes = visit["violation_codes"]
    if not codes:
        return 0
    return len(codes)


def _raw_name(camis: str) -> str | None:
    rows = (
        pl.read_parquet(RAW_PATH, columns=["camis", "name"])
        .filter(pl.col("camis") == camis)
        .drop_nulls("name")
    )
    if rows.height == 0:
        return None
    return rows["name"][0]


@lru_cache(maxsize=1)
def _inspections() -> pl.DataFrame:
    return pl.read_parquet(INSPECTIONS_PATH)


@lru_cache(maxsize=1)
def _known_camis() -> frozenset[str]:
    camis = pl.read_parquet(RAW_PATH, columns=["camis"])["camis"].drop_nulls()
    return frozenset(camis.to_list())


@lru_cache(maxsize=1)
def _model() -> dict[str, object]:
    bundle = joblib.load(MODEL_PATH)
    if not isinstance(bundle["preprocessor"], FeaturePreprocessor):
        raise TypeError("Saved preprocessor does not match this version.")
    return bundle
