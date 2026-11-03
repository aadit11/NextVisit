"""Fit logistic regression, LightGBM, and calibration for one city.

Writes artifacts/{city}/model.joblib and artifacts/{city}/metrics.json.
"""

import json
from pathlib import Path

import joblib
import numpy as np
import polars as pl
from lightgbm import LGBMClassifier
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.calibration import CalibratedClassifierCV
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from nextvisit.model.evaluate import baseline_probabilities, score_probabilities
from nextvisit.prepare.austin import EXAMPLES_PATH as AUSTIN_EXAMPLES_PATH
from nextvisit.prepare.boston import EXAMPLES_PATH as BOSTON_EXAMPLES_PATH
from nextvisit.prepare.chicago import EXAMPLES_PATH as CHICAGO_EXAMPLES_PATH
from nextvisit.prepare.features import EXAMPLES_PATH
from nextvisit.prepare.king_county import EXAMPLES_PATH as KING_COUNTY_EXAMPLES_PATH
from nextvisit.prepare.los_angeles import EXAMPLES_PATH as LOS_ANGELES_EXAMPLES_PATH
from nextvisit.prepare.san_francisco import EXAMPLES_PATH as SAN_FRANCISCO_EXAMPLES_PATH

CATEGORICAL = ("cuisine", "borough", "previous_grade")
NUMERIC = (
    "days_since_previous",
    "previous_positive",
    "previous_score",
    "prior_inspection_count",
    "prior_positive_count",
    "prior_violation_count",
    "previous_violation_count",
    "days_since_last_positive",
)
CHICAGO_CATEGORICAL = ("facility_type", "risk", "zip")
CHICAGO_NUMERIC = (
    "days_since_previous",
    "previous_positive",
    "prior_inspection_count",
    "prior_positive_count",
    "prior_violation_count",
    "previous_violation_count",
    "days_since_last_positive",
)
AUSTIN_CATEGORICAL = ("zip",)
AUSTIN_NUMERIC = (
    "days_since_previous",
    "previous_positive",
    "previous_score",
    "prior_inspection_count",
    "prior_positive_count",
    "days_since_last_positive",
)
KING_COUNTY_CATEGORICAL = ("risk", "zip", "previous_grade")
KING_COUNTY_NUMERIC = (
    "days_since_previous",
    "previous_positive",
    "previous_score",
    "prior_inspection_count",
    "prior_positive_count",
    "prior_violation_count",
    "previous_violation_count",
    "days_since_last_positive",
)
LOS_ANGELES_CATEGORICAL = ("pe_description", "zip", "previous_grade")
LOS_ANGELES_NUMERIC = KING_COUNTY_NUMERIC
BOSTON_CATEGORICAL = ("license_description", "zip")
BOSTON_NUMERIC = (
    "days_since_previous",
    "previous_positive",
    "prior_inspection_count",
    "prior_positive_count",
    "prior_violation_count",
    "previous_violation_count",
    "days_since_last_positive",
)
SAN_FRANCISCO_CATEGORICAL = ("permit_type", "neighborhood")
SAN_FRANCISCO_NUMERIC = BOSTON_NUMERIC


class FeaturePreprocessor(BaseEstimator, TransformerMixin):
    """One-hot categories and median-fill numbers. Fit on the training period only."""

    categorical = CATEGORICAL
    numeric = NUMERIC

    def __init__(self) -> None:
        self.encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
        self.imputer = SimpleImputer(strategy="median")
        self.scaler = StandardScaler()

    def fit(self, features: pl.DataFrame, y: np.ndarray | None = None) -> "FeaturePreprocessor":
        categorical, numeric = _split(features, self.categorical, self.numeric)
        self._skip_categorical = categorical.shape[1] == 0
        self._skip_numeric = numeric.shape[1] == 0
        encoded = self._encode(categorical, fit=True)
        imputed = self._impute(numeric, fit=True)
        self.scaler.fit(np.hstack([encoded, imputed]))
        return self

    def transform(self, features: pl.DataFrame) -> np.ndarray:
        categorical, numeric = _split(features, self.categorical, self.numeric)
        encoded = self._encode(categorical, fit=False)
        imputed = self._impute(numeric, fit=False)
        return self.scaler.transform(np.hstack([encoded, imputed]))

    def _encode(self, categorical: np.ndarray, fit: bool) -> np.ndarray:
        if getattr(self, "_skip_categorical", categorical.shape[1] == 0):
            return np.zeros((categorical.shape[0], 0))
        if fit:
            return self.encoder.fit_transform(categorical)
        return self.encoder.transform(categorical)

    def _impute(self, numeric: np.ndarray, fit: bool) -> np.ndarray:
        if getattr(self, "_skip_numeric", numeric.shape[1] == 0):
            return np.zeros((numeric.shape[0], 0))
        if fit:
            return self.imputer.fit_transform(numeric)
        return self.imputer.transform(numeric)


class ChicagoPreprocessor(FeaturePreprocessor):
    """Chicago has facility type, risk, and zip. It has no cuisine, score, or grade."""

    categorical = CHICAGO_CATEGORICAL
    numeric = CHICAGO_NUMERIC


class AustinPreprocessor(FeaturePreprocessor):
    """Austin has a zip and the previous routine score. It has no violation codes."""

    categorical = AUSTIN_CATEGORICAL
    numeric = AUSTIN_NUMERIC


class KingCountyPreprocessor(FeaturePreprocessor):
    """King County has risk, zip, grade, and the previous inspection score."""

    categorical = KING_COUNTY_CATEGORICAL
    numeric = KING_COUNTY_NUMERIC


class LosAngelesPreprocessor(FeaturePreprocessor):
    """Los Angeles has the program description, zip, grade, and previous score."""

    categorical = LOS_ANGELES_CATEGORICAL
    numeric = LOS_ANGELES_NUMERIC


class BostonPreprocessor(FeaturePreprocessor):
    """Boston has the license description and zip. It has no numeric score."""

    categorical = BOSTON_CATEGORICAL
    numeric = BOSTON_NUMERIC


class SanFranciscoPreprocessor(FeaturePreprocessor):
    """San Francisco has the permit type and the neighborhood. It has no numeric score."""

    categorical = SAN_FRANCISCO_CATEGORICAL
    numeric = SAN_FRANCISCO_NUMERIC


EXAMPLES_PATHS = {
    "new_york": EXAMPLES_PATH,
    "chicago": CHICAGO_EXAMPLES_PATH,
    "king_county": KING_COUNTY_EXAMPLES_PATH,
    "los_angeles": LOS_ANGELES_EXAMPLES_PATH,
    "boston": BOSTON_EXAMPLES_PATH,
    "san_francisco": SAN_FRANCISCO_EXAMPLES_PATH,
    "austin": AUSTIN_EXAMPLES_PATH,
}
PREPROCESSORS = {
    "new_york": FeaturePreprocessor,
    "chicago": ChicagoPreprocessor,
    "king_county": KingCountyPreprocessor,
    "los_angeles": LosAngelesPreprocessor,
    "boston": BostonPreprocessor,
    "san_francisco": SanFranciscoPreprocessor,
    "austin": AustinPreprocessor,
}


def calibrated_lightgbm() -> CalibratedClassifierCV:
    """The production estimator: calibrated LightGBM with the training settings."""
    return CalibratedClassifierCV(
        LGBMClassifier(random_state=0, verbose=-1),
        cv=3,
    )


def train_city(city_id: str) -> None:
    trainer = _TRAINERS.get(city_id)
    if trainer is None:
        raise NotImplementedError(f"Training for {city_id} is not implemented yet.")
    trainer()


def train_new_york(
    examples_path: Path = EXAMPLES_PATH,
    model_path: Path = Path("artifacts/new_york/model.joblib"),
    metrics_path: Path = Path("artifacts/new_york/metrics.json"),
) -> tuple[Path, Path]:
    return _fit("new_york", examples_path, model_path, metrics_path, FeaturePreprocessor())


def train_chicago(
    examples_path: Path = CHICAGO_EXAMPLES_PATH,
    model_path: Path = Path("artifacts/chicago/model.joblib"),
    metrics_path: Path = Path("artifacts/chicago/metrics.json"),
) -> tuple[Path, Path]:
    return _fit("chicago", examples_path, model_path, metrics_path, ChicagoPreprocessor())


def train_austin(
    examples_path: Path = AUSTIN_EXAMPLES_PATH,
    model_path: Path = Path("artifacts/austin/model.joblib"),
    metrics_path: Path = Path("artifacts/austin/metrics.json"),
) -> tuple[Path, Path]:
    return _fit("austin", examples_path, model_path, metrics_path, AustinPreprocessor())


def train_king_county(
    examples_path: Path = KING_COUNTY_EXAMPLES_PATH,
    model_path: Path = Path("artifacts/king_county/model.joblib"),
    metrics_path: Path = Path("artifacts/king_county/metrics.json"),
) -> tuple[Path, Path]:
    return _fit("king_county", examples_path, model_path, metrics_path, KingCountyPreprocessor())


def train_los_angeles(
    examples_path: Path = LOS_ANGELES_EXAMPLES_PATH,
    model_path: Path = Path("artifacts/los_angeles/model.joblib"),
    metrics_path: Path = Path("artifacts/los_angeles/metrics.json"),
) -> tuple[Path, Path]:
    return _fit("los_angeles", examples_path, model_path, metrics_path, LosAngelesPreprocessor())


def train_boston(
    examples_path: Path = BOSTON_EXAMPLES_PATH,
    model_path: Path = Path("artifacts/boston/model.joblib"),
    metrics_path: Path = Path("artifacts/boston/metrics.json"),
) -> tuple[Path, Path]:
    return _fit("boston", examples_path, model_path, metrics_path, BostonPreprocessor())


def train_san_francisco(
    examples_path: Path = SAN_FRANCISCO_EXAMPLES_PATH,
    model_path: Path = Path("artifacts/san_francisco/model.joblib"),
    metrics_path: Path = Path("artifacts/san_francisco/metrics.json"),
) -> tuple[Path, Path]:
    return _fit("san_francisco", examples_path, model_path, metrics_path, SanFranciscoPreprocessor())


_TRAINERS = {
    "new_york": train_new_york,
    "chicago": train_chicago,
    "king_county": train_king_county,
    "los_angeles": train_los_angeles,
    "boston": train_boston,
    "san_francisco": train_san_francisco,
    "austin": train_austin,
}


def _fit(
    city_id: str,
    examples_path: Path,
    model_path: Path,
    metrics_path: Path,
    preprocessor: FeaturePreprocessor,
) -> tuple[Path, Path]:
    examples = pl.read_parquet(examples_path)
    train = examples.filter(pl.col("split") == "train")
    test = examples.filter(pl.col("split") == "test")
    y_train = train["label"].to_numpy()
    y_test = test["label"].to_numpy()

    preprocessor = preprocessor.fit(train)
    x_train = preprocessor.transform(train)
    x_test = preprocessor.transform(test)

    logistic = LogisticRegression(max_iter=2000, random_state=0)
    logistic.fit(x_train, y_train)

    calibrated = calibrated_lightgbm()
    calibrated.fit(x_train, y_train)

    scores = {
        "repeat_last_visit": score_probabilities(
            y_test,
            baseline_probabilities(test["previous_positive"].to_numpy()),
        ),
        "logistic_regression": score_probabilities(y_test, logistic.predict_proba(x_test)[:, 1]),
        "lightgbm": score_probabilities(y_test, calibrated.predict_proba(x_test)[:, 1]),
    }
    metrics = {
        "city": city_id,
        "test_rows": int(test.height),
        "models": scores,
        "lightgbm_beats_baseline_pr_auc": (
            scores["lightgbm"]["pr_auc"] > scores["repeat_last_visit"]["pr_auc"]
        ),
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    joblib.dump({"preprocessor": preprocessor, "model": calibrated}, model_path)
    return model_path, metrics_path


def _split(
    features: pl.DataFrame,
    categorical: tuple[str, ...],
    numeric: tuple[str, ...],
) -> tuple[np.ndarray, np.ndarray]:
    if categorical:
        categories = (
            features.select(list(categorical))
            .with_columns(pl.all().fill_null("__missing__").cast(pl.String))
            .to_numpy()
        )
    else:
        categories = np.zeros((features.height, 0), dtype=object)
    if not numeric:
        return categories, np.zeros((features.height, 0), dtype=float)
    numbers = features.select(list(numeric))
    if "previous_positive" in numeric:
        numbers = numbers.with_columns(pl.col("previous_positive").cast(pl.Float64))
    return categories, numbers.to_numpy().astype(float)
