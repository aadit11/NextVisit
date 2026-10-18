"""Score one New York restaurant from inspections already on disk."""

from datetime import date, timedelta
from functools import lru_cache

import joblib
import polars as pl

from nextvisit.cities.austin import RAW_PATH as AUSTIN_RAW_PATH
from nextvisit.cities.austin import SPEC as AUSTIN_SPEC
from nextvisit.cities.chicago import RAW_PATH as CHICAGO_RAW_PATH
from nextvisit.cities.chicago import SPEC as CHICAGO_SPEC
from nextvisit.cities.new_york import RAW_PATH, SPEC
from nextvisit.model.train import AUSTIN_CATEGORICAL, AUSTIN_NUMERIC, CHICAGO_CATEGORICAL, CHICAGO_NUMERIC, FeaturePreprocessor
from nextvisit.prepare.austin import INSPECTIONS_PATH as AUSTIN_INSPECTIONS_PATH
from nextvisit.prepare.chicago import INSPECTIONS_PATH as CHICAGO_INSPECTIONS_PATH
from nextvisit.prepare.collapse import INSPECTIONS_PATH
from nextvisit.prepare.features import assert_features_before_target

MODEL_PATH = "artifacts/new_york/model.joblib"
CHICAGO_MODEL_PATH = "artifacts/chicago/model.joblib"
AUSTIN_MODEL_PATH = "artifacts/austin/model.joblib"


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


def predict_chicago(license_id: str) -> dict[str, object]:
    visits = _chicago_inspections().filter(pl.col("license") == license_id).sort(
        ["inspection_date", "inspection_id"]
    )
    if visits.height == 0:
        if license_id not in _known_chicago_licenses():
            raise UnknownRestaurant(license_id)
        return {
            "city": CHICAGO_SPEC.id,
            "restaurant_id": license_id,
            "name": _chicago_name(license_id),
            "cuisine": None,
            "abstained": True,
            "probability": None,
            "label": CHICAGO_SPEC.label,
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
    features = pl.DataFrame([_chicago_feature_row(records, as_of)])
    bundle = _chicago_model()
    probability = float(bundle["model"].predict_proba(bundle["preprocessor"].transform(features))[0, 1])
    return {
        "city": CHICAGO_SPEC.id,
        "restaurant_id": license_id,
        "name": latest["name"],
        "cuisine": None,
        "abstained": False,
        "probability": probability,
        "label": CHICAGO_SPEC.label,
        "codes": _history_codes(records),
        "work_order": [],
    }


def _chicago_feature_row(visits: list[dict[str, object]], as_of: date) -> dict[str, object]:
    previous = visits[-1]
    last_positive = next(
        (visit["inspection_date"] for visit in reversed(visits) if visit["positive"]),
        None,
    )
    row = {
        "facility_type": previous["facility_type"],
        "risk": previous["risk"],
        "zip": previous["zip"],
        "days_since_previous": (as_of - previous["inspection_date"]).days,
        "previous_positive": bool(previous["positive"]),
        "prior_inspection_count": len(visits),
        "prior_positive_count": sum(bool(visit["positive"]) for visit in visits),
        "prior_violation_count": sum(int(visit["violation_count"]) for visit in visits),
        "previous_violation_count": int(previous["violation_count"]),
        "days_since_last_positive": (
            None if last_positive is None else (as_of - last_positive).days
        ),
    }
    missing = [name for name in (*CHICAGO_CATEGORICAL, *CHICAGO_NUMERIC) if name not in row]
    if missing:
        raise KeyError(f"Chicago feature row is missing {missing}.")
    return row


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


@lru_cache(maxsize=1)
def _chicago_inspections() -> pl.DataFrame:
    return pl.read_parquet(CHICAGO_INSPECTIONS_PATH)


@lru_cache(maxsize=1)
def _known_chicago_licenses() -> frozenset[str]:
    licenses = pl.read_parquet(CHICAGO_RAW_PATH, columns=["license"])["license"].drop_nulls()
    return frozenset(licenses.to_list())


@lru_cache(maxsize=1)
def _chicago_model() -> dict[str, object]:
    bundle = joblib.load(CHICAGO_MODEL_PATH)
    if not isinstance(bundle["preprocessor"], FeaturePreprocessor):
        raise TypeError("Saved preprocessor does not match this version.")
    return bundle


def _chicago_name(license_id: str) -> str | None:
    rows = (
        pl.read_parquet(CHICAGO_RAW_PATH, columns=["license", "name"])
        .filter(pl.col("license") == license_id)
        .drop_nulls("name")
    )
    if rows.height == 0:
        return None
    return rows["name"][0]


def predict_austin(facility_id: str) -> dict[str, object]:
    visits = _austin_inspections().filter(pl.col("facility_id") == facility_id).sort(
        ["inspection_date", "inspection_id"]
    )
    if visits.height == 0:
        if facility_id not in _known_austin_facilities():
            raise UnknownRestaurant(facility_id)
        return {
            "city": AUSTIN_SPEC.id,
            "restaurant_id": facility_id,
            "name": _austin_name(facility_id),
            "cuisine": None,
            "abstained": True,
            "probability": None,
            "label": AUSTIN_SPEC.label,
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
    features = pl.DataFrame([_austin_feature_row(records, as_of)])
    bundle = _austin_model()
    probability = float(bundle["model"].predict_proba(bundle["preprocessor"].transform(features))[0, 1])
    return {
        "city": AUSTIN_SPEC.id,
        "restaurant_id": facility_id,
        "name": latest["name"],
        "cuisine": None,
        "abstained": False,
        "probability": probability,
        "label": AUSTIN_SPEC.label,
        "codes": [],
        "work_order": [],
    }


def _austin_feature_row(visits: list[dict[str, object]], as_of: date) -> dict[str, object]:
    previous = visits[-1]
    last_positive = next(
        (visit["inspection_date"] for visit in reversed(visits) if visit["positive"]),
        None,
    )
    row = {
        "zip": previous["zip"],
        "days_since_previous": (as_of - previous["inspection_date"]).days,
        "previous_positive": bool(previous["positive"]),
        "previous_score": previous["score"],
        "prior_inspection_count": len(visits),
        "prior_positive_count": sum(bool(visit["positive"]) for visit in visits),
        "days_since_last_positive": (
            None if last_positive is None else (as_of - last_positive).days
        ),
    }
    missing = [name for name in (*AUSTIN_CATEGORICAL, *AUSTIN_NUMERIC) if name not in row]
    if missing:
        raise KeyError(f"Austin feature row is missing {missing}.")
    return row


@lru_cache(maxsize=1)
def _austin_inspections() -> pl.DataFrame:
    return pl.read_parquet(AUSTIN_INSPECTIONS_PATH)


@lru_cache(maxsize=1)
def _known_austin_facilities() -> frozenset[str]:
    facilities = pl.read_parquet(AUSTIN_RAW_PATH, columns=["facility_id"])["facility_id"].drop_nulls()
    return frozenset(facilities.to_list())


@lru_cache(maxsize=1)
def _austin_model() -> dict[str, object]:
    bundle = joblib.load(AUSTIN_MODEL_PATH)
    if not isinstance(bundle["preprocessor"], FeaturePreprocessor):
        raise TypeError("Saved preprocessor does not match this version.")
    return bundle


def _austin_name(facility_id: str) -> str | None:
    rows = (
        pl.read_parquet(AUSTIN_RAW_PATH, columns=["facility_id", "name"])
        .filter(pl.col("facility_id") == facility_id)
        .drop_nulls("name")
    )
    if rows.height == 0:
        return None
    return rows["name"][0]
