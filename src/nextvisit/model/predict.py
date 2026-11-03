"""Score one New York restaurant from inspections already on disk."""

from datetime import date, timedelta
from functools import lru_cache

import joblib
import polars as pl

from nextvisit.cities.austin import RAW_PATH as AUSTIN_RAW_PATH
from nextvisit.cities.austin import SPEC as AUSTIN_SPEC
from nextvisit.cities.boston import RAW_PATH as BOSTON_RAW_PATH
from nextvisit.cities.boston import SPEC as BOSTON_SPEC
from nextvisit.cities.chicago import RAW_PATH as CHICAGO_RAW_PATH
from nextvisit.cities.chicago import SPEC as CHICAGO_SPEC
from nextvisit.cities.king_county import RAW_PATH as KING_COUNTY_RAW_PATH
from nextvisit.cities.king_county import SPEC as KING_COUNTY_SPEC
from nextvisit.cities.los_angeles import INSPECTIONS_PATH as LOS_ANGELES_RAW_PATH
from nextvisit.cities.los_angeles import SPEC as LOS_ANGELES_SPEC
from nextvisit.cities.new_york import RAW_PATH, SPEC
from nextvisit.cities.san_francisco import RAW_PATH as SAN_FRANCISCO_RAW_PATH
from nextvisit.history import recent_trend, score_direction
from nextvisit.brief.history import raw_visits
from nextvisit.cities.san_francisco import SPEC as SAN_FRANCISCO_SPEC
from nextvisit.model.train import (
    AUSTIN_CATEGORICAL,
    AUSTIN_NUMERIC,
    BOSTON_CATEGORICAL,
    BOSTON_NUMERIC,
    CHICAGO_CATEGORICAL,
    CHICAGO_NUMERIC,
    KING_COUNTY_CATEGORICAL,
    KING_COUNTY_NUMERIC,
    LOS_ANGELES_CATEGORICAL,
    LOS_ANGELES_NUMERIC,
    SAN_FRANCISCO_CATEGORICAL,
    SAN_FRANCISCO_NUMERIC,
    FeaturePreprocessor,
)
from nextvisit.prepare.austin import INSPECTIONS_PATH as AUSTIN_INSPECTIONS_PATH
from nextvisit.prepare.boston import INSPECTIONS_PATH as BOSTON_INSPECTIONS_PATH
from nextvisit.prepare.chicago import INSPECTIONS_PATH as CHICAGO_INSPECTIONS_PATH
from nextvisit.prepare.collapse import INSPECTIONS_PATH
from nextvisit.prepare.features import LeakageError, assert_features_before_target
from nextvisit.prepare.king_county import INSPECTIONS_PATH as KING_COUNTY_INSPECTIONS_PATH
from nextvisit.prepare.los_angeles import PROCESSED_INSPECTIONS_PATH as LOS_ANGELES_INSPECTIONS_PATH
from nextvisit.prepare.san_francisco import INSPECTIONS_PATH as SAN_FRANCISCO_INSPECTIONS_PATH

MODEL_PATH = "artifacts/new_york/model.joblib"
CHICAGO_MODEL_PATH = "artifacts/chicago/model.joblib"
AUSTIN_MODEL_PATH = "artifacts/austin/model.joblib"


class UnknownRestaurant(LookupError):
    """This CAMIS is not in the New York extract."""


def _trend_fields(records: list[dict[str, object]]) -> dict[str, object]:
    return recent_trend([bool(visit["positive"]) for visit in records])


def _score_trend(records: list[dict[str, object]]) -> str | None:
    return score_direction([visit.get("score") for visit in records])


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
            "address": _latest_address(RAW_PATH, "camis", camis),
            "cuisine": None,
            "abstained": True,
            "probability": None,
            "label": SPEC.label,
            "codes": [],
            "visits": [],
            **_trend_fields([]),
        }

    records = visits.to_dicts()
    latest = records[-1]
    as_of = _as_of(latest["inspection_date"])
    assert_features_before_target(
        [visit["inspection_date"] for visit in records],
        as_of,
    )
    row = _feature_row(records, as_of)
    features = pl.DataFrame([row])
    bundle = _model()
    probability = float(bundle["model"].predict_proba(bundle["preprocessor"].transform(features))[0, 1])
    return {
        "city": SPEC.id,
        "restaurant_id": camis,
        "name": latest["name"],
        "address": _latest_address(RAW_PATH, "camis", camis),
        "cuisine": latest["cuisine"],
        "abstained": False,
        "probability": probability,
        "label": SPEC.label,
        "codes": _history_codes(records),
        "visits": raw_visits(records),
        **_trend_fields(records),
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
            "address": _latest_address(CHICAGO_RAW_PATH, "license", license_id),
            "cuisine": None,
            "abstained": True,
            "probability": None,
            "label": CHICAGO_SPEC.label,
            "codes": [],
            "visits": [],
            **_trend_fields([]),
        }

    records = visits.to_dicts()
    latest = records[-1]
    as_of = _as_of(latest["inspection_date"])
    assert_features_before_target(
        [visit["inspection_date"] for visit in records],
        as_of,
    )
    row = _chicago_feature_row(records, as_of)
    features = pl.DataFrame([row])
    bundle = _chicago_model()
    probability = float(bundle["model"].predict_proba(bundle["preprocessor"].transform(features))[0, 1])
    return {
        "city": CHICAGO_SPEC.id,
        "restaurant_id": license_id,
        "name": latest["name"],
        "address": _latest_address(CHICAGO_RAW_PATH, "license", license_id),
        "cuisine": None,
        "abstained": False,
        "probability": probability,
        "label": CHICAGO_SPEC.label,
        "codes": _history_codes(records),
        "visits": raw_visits(records),
        **_trend_fields(records),
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
            "address": _latest_address(AUSTIN_RAW_PATH, "facility_id", facility_id),
            "cuisine": None,
            "abstained": True,
            "probability": None,
            "label": AUSTIN_SPEC.label,
            "codes": [],
            "visits": [],
            **_trend_fields([]),
            "score_trend": None,
        }

    records = visits.to_dicts()
    latest = records[-1]
    as_of = _as_of(latest["inspection_date"])
    assert_features_before_target(
        [visit["inspection_date"] for visit in records],
        as_of,
    )
    row = _austin_feature_row(records, as_of)
    features = pl.DataFrame([row])
    bundle = _austin_model()
    probability = float(bundle["model"].predict_proba(bundle["preprocessor"].transform(features))[0, 1])
    score_trend = _score_trend(records)
    return {
        "city": AUSTIN_SPEC.id,
        "restaurant_id": facility_id,
        "name": latest["name"],
        "address": _latest_address(AUSTIN_RAW_PATH, "facility_id", facility_id),
        "cuisine": None,
        "abstained": False,
        "probability": probability,
        "label": AUSTIN_SPEC.label,
        "codes": [],
        "visits": raw_visits(records),
        **_trend_fields(records),
        "score_trend": score_trend,
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


def predict_king_county(business_id: str) -> dict[str, object]:
    return _lookup(
        spec=KING_COUNTY_SPEC,
        restaurant_id=business_id,
        visits=_king_county_inspections()
        .filter(pl.col("business_id") == business_id)
        .sort(["inspection_date", "inspection_id"]),
        known=_known_ids(KING_COUNTY_RAW_PATH, "business_id"),
        absent_name=_raw_column_name(KING_COUNTY_RAW_PATH, "business_id", business_id),
        address=_latest_address(KING_COUNTY_RAW_PATH, "business_id", business_id),
        feature_row=lambda records, as_of: _city_feature_row(
            records,
            as_of,
            KING_COUNTY_CATEGORICAL,
            KING_COUNTY_NUMERIC,
            extra=_king_county_extra,
        ),
        bundle=_saved_model("artifacts/king_county/model.joblib"),
    )


def predict_los_angeles(facility_id: str) -> dict[str, object]:
    return _lookup(
        spec=LOS_ANGELES_SPEC,
        restaurant_id=facility_id,
        visits=_los_angeles_inspections()
        .filter(pl.col("facility_id") == facility_id)
        .sort(["inspection_date", "inspection_id"]),
        known=_known_ids(LOS_ANGELES_RAW_PATH, "facility_id"),
        absent_name=_raw_column_name(LOS_ANGELES_RAW_PATH, "facility_id", facility_id),
        address=_latest_address(LOS_ANGELES_RAW_PATH, "facility_id", facility_id),
        feature_row=lambda records, as_of: _city_feature_row(
            records,
            as_of,
            LOS_ANGELES_CATEGORICAL,
            LOS_ANGELES_NUMERIC,
            extra=_los_angeles_extra,
        ),
        bundle=_saved_model("artifacts/los_angeles/model.joblib"),
    )


def predict_boston(license_id: str) -> dict[str, object]:
    return _lookup(
        spec=BOSTON_SPEC,
        restaurant_id=license_id,
        visits=_boston_inspections()
        .filter(pl.col("license") == license_id)
        .sort(["inspection_date", "inspection_id"]),
        known=_known_ids(BOSTON_RAW_PATH, "license"),
        absent_name=_raw_column_name(BOSTON_RAW_PATH, "license", license_id),
        address=_latest_address(BOSTON_RAW_PATH, "license", license_id),
        feature_row=lambda records, as_of: _city_feature_row(
            records,
            as_of,
            BOSTON_CATEGORICAL,
            BOSTON_NUMERIC,
            extra=_boston_extra,
        ),
        bundle=_saved_model("artifacts/boston/model.joblib"),
    )


def predict_san_francisco(permit_number: str) -> dict[str, object]:
    return _lookup(
        spec=SAN_FRANCISCO_SPEC,
        restaurant_id=permit_number,
        visits=_san_francisco_inspections()
        .filter(pl.col("permit_number") == permit_number)
        .sort(["inspection_date", "inspection_id"]),
        known=_known_ids(SAN_FRANCISCO_RAW_PATH, "permit_number"),
        absent_name=_raw_column_name(SAN_FRANCISCO_RAW_PATH, "permit_number", permit_number),
        address=_latest_address(SAN_FRANCISCO_RAW_PATH, "permit_number", permit_number),
        feature_row=lambda records, as_of: _city_feature_row(
            records,
            as_of,
            SAN_FRANCISCO_CATEGORICAL,
            SAN_FRANCISCO_NUMERIC,
            extra=_san_francisco_extra,
        ),
        bundle=_saved_model("artifacts/san_francisco/model.joblib"),
    )


def _latest_address(path, column: str, restaurant_id: str) -> str | None:
    """Latest non-empty street line for this restaurant. Missing column means no address yet."""
    if "address" not in pl.scan_parquet(path).collect_schema().names():
        return None
    rows = (
        pl.read_parquet(path, columns=[column, "address", "inspection_date"])
        .filter(pl.col(column) == restaurant_id)
        .drop_nulls("address")
        .sort("inspection_date")
    )
    if rows.height == 0:
        return None
    return str(rows["address"][-1])


def _lookup(
    *,
    spec,
    restaurant_id: str,
    visits: pl.DataFrame,
    known: frozenset[str],
    absent_name: str | None,
    address: str | None,
    feature_row,
    bundle: dict[str, object],
) -> dict[str, object]:
    if visits.height == 0:
        if restaurant_id not in known:
            raise UnknownRestaurant(restaurant_id)
        return {
            "city": spec.id,
            "restaurant_id": restaurant_id,
            "name": absent_name,
            "address": address,
            "cuisine": None,
            "abstained": True,
            "probability": None,
            "label": spec.label,
            "codes": [],
            "visits": [],
            **_trend_fields([]),
        }
    records = visits.to_dicts()
    latest = records[-1]
    as_of = _as_of(latest["inspection_date"])
    assert_features_before_target(
        [visit["inspection_date"] for visit in records],
        as_of,
    )
    row = feature_row(records, as_of)
    features = pl.DataFrame([row])
    probability = float(bundle["model"].predict_proba(bundle["preprocessor"].transform(features))[0, 1])
    return {
        "city": spec.id,
        "restaurant_id": restaurant_id,
        "name": latest["name"],
        "address": address,
        "cuisine": None,
        "abstained": False,
        "probability": probability,
        "label": spec.label,
        "codes": _history_codes(records),
        "visits": raw_visits(records),
        **_trend_fields(records),
    }


def _city_feature_row(visits, as_of, categorical, numeric, extra) -> dict[str, object]:
    previous = visits[-1]
    last_positive = next(
        (visit["inspection_date"] for visit in reversed(visits) if visit["positive"]),
        None,
    )
    row = {
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
    row.update(extra(previous))
    missing = [name for name in (*categorical, *numeric) if name not in row]
    if missing:
        raise KeyError(f"Feature row is missing {missing}.")
    return row


def _king_county_extra(previous: dict[str, object]) -> dict[str, object]:
    return {
        "risk": previous["risk"],
        "zip": previous["zip"],
        "previous_grade": previous["grade"],
        "previous_score": previous["score"],
    }


def _los_angeles_extra(previous: dict[str, object]) -> dict[str, object]:
    return {
        "pe_description": previous["pe_description"],
        "zip": previous["zip"],
        "previous_grade": previous["grade"],
        "previous_score": previous["score"],
    }


def _boston_extra(previous: dict[str, object]) -> dict[str, object]:
    return {"license_description": previous["license_description"], "zip": previous["zip"]}


def _san_francisco_extra(previous: dict[str, object]) -> dict[str, object]:
    return {"permit_type": previous["permit_type"], "neighborhood": previous["neighborhood"]}


@lru_cache(maxsize=1)
def _king_county_inspections() -> pl.DataFrame:
    return pl.read_parquet(KING_COUNTY_INSPECTIONS_PATH)


@lru_cache(maxsize=1)
def _los_angeles_inspections() -> pl.DataFrame:
    return pl.read_parquet(LOS_ANGELES_INSPECTIONS_PATH)


@lru_cache(maxsize=1)
def _boston_inspections() -> pl.DataFrame:
    return pl.read_parquet(BOSTON_INSPECTIONS_PATH)


@lru_cache(maxsize=1)
def _san_francisco_inspections() -> pl.DataFrame:
    return pl.read_parquet(SAN_FRANCISCO_INSPECTIONS_PATH)


@lru_cache(maxsize=8)
def _known_ids(path: str, column: str) -> frozenset[str]:
    values = pl.read_parquet(path, columns=[column])[column].drop_nulls()
    return frozenset(values.to_list())


@lru_cache(maxsize=4)
def _saved_model(path: str) -> dict[str, object]:
    bundle = joblib.load(path)
    if not isinstance(bundle["preprocessor"], FeaturePreprocessor):
        raise TypeError("Saved preprocessor does not match this version.")
    return bundle


def _raw_column_name(path: str, column: str, restaurant_id: str) -> str | None:
    rows = (
        pl.read_parquet(path, columns=[column, "name"])
        .filter(pl.col(column) == restaurant_id)
        .drop_nulls("name")
    )
    if rows.height == 0:
        return None
    return rows["name"][0]


_SCORE_LIMIT = 40


def _shared_features(categorical: tuple[str, ...], numeric: tuple[str, ...], extra):
    def build(visits: list[dict[str, object]], as_of: date) -> dict[str, object]:
        return _city_feature_row(visits, as_of, categorical, numeric, extra)

    return build


_CITY_SCORERS = {
    "new_york": ("camis", ["inspection_date"], _inspections, _model, _feature_row),
    "chicago": (
        "license",
        ["inspection_date", "inspection_id"],
        _chicago_inspections,
        _chicago_model,
        _chicago_feature_row,
    ),
    "austin": (
        "facility_id",
        ["inspection_date", "inspection_id"],
        _austin_inspections,
        _austin_model,
        _austin_feature_row,
    ),
    "king_county": (
        "business_id",
        ["inspection_date", "inspection_id"],
        _king_county_inspections,
        lambda: _saved_model("artifacts/king_county/model.joblib"),
        _shared_features(KING_COUNTY_CATEGORICAL, KING_COUNTY_NUMERIC, _king_county_extra),
    ),
    "los_angeles": (
        "facility_id",
        ["inspection_date", "inspection_id"],
        _los_angeles_inspections,
        lambda: _saved_model("artifacts/los_angeles/model.joblib"),
        _shared_features(LOS_ANGELES_CATEGORICAL, LOS_ANGELES_NUMERIC, _los_angeles_extra),
    ),
    "boston": (
        "license",
        ["inspection_date", "inspection_id"],
        _boston_inspections,
        lambda: _saved_model("artifacts/boston/model.joblib"),
        _shared_features(BOSTON_CATEGORICAL, BOSTON_NUMERIC, _boston_extra),
    ),
    "san_francisco": (
        "permit_number",
        ["inspection_date", "inspection_id"],
        _san_francisco_inspections,
        lambda: _saved_model("artifacts/san_francisco/model.joblib"),
        _shared_features(
            SAN_FRANCISCO_CATEGORICAL,
            SAN_FRANCISCO_NUMERIC,
            _san_francisco_extra,
        ),
    ),
}


def serious_probabilities(city_id: str, restaurant_ids: list[str]) -> dict[str, float]:
    """Score several restaurants with that city's saved model.

    The value is the probability that the next inspection is serious.
    Each feature date is strictly before the date the score is for.
    """
    spec = _CITY_SCORERS.get(city_id)
    wanted = list(dict.fromkeys(str(item) for item in restaurant_ids if item))[:_SCORE_LIMIT]
    if spec is None or not wanted:
        return {}
    id_column, sort_columns, load, model, features = spec
    subset = (
        load()
        .with_columns(pl.col(id_column).cast(pl.String))
        .filter(pl.col(id_column).is_in(wanted))
        .sort(sort_columns)
    )
    grouped: dict[str, list[dict[str, object]]] = {}
    for record in subset.to_dicts():
        grouped.setdefault(str(record[id_column]), []).append(record)
    rows: list[dict[str, object]] = []
    scored: list[str] = []
    for restaurant_id, records in grouped.items():
        try:
            as_of = _as_of(records[-1]["inspection_date"])
            assert_features_before_target(
                [visit["inspection_date"] for visit in records],
                as_of,
            )
            rows.append(features(records, as_of))
        except (LeakageError, KeyError, TypeError, ValueError):
            continue
        scored.append(restaurant_id)
    if not rows:
        return {}
    bundle = model()
    matrix = bundle["preprocessor"].transform(pl.DataFrame(rows))
    probabilities = bundle["model"].predict_proba(matrix)[:, 1]
    return {
        restaurant_id: float(score)
        for restaurant_id, score in zip(scored, probabilities, strict=True)
    }
