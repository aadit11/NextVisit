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
from nextvisit.prepare.features import EXAMPLES_PATH

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


class FeaturePreprocessor(BaseEstimator, TransformerMixin):
    """One-hot categories and median-fill numbers. Fit on the training period only."""

    def __init__(self) -> None:
        self.encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
        self.imputer = SimpleImputer(strategy="median")
        self.scaler = StandardScaler()

    def fit(self, features: pl.DataFrame, y: np.ndarray | None = None) -> "FeaturePreprocessor":
        categorical, numeric = _split(features)
        encoded = self.encoder.fit_transform(categorical)
        imputed = self.imputer.fit_transform(numeric)
        self.scaler.fit(np.hstack([encoded, imputed]))
        return self

    def transform(self, features: pl.DataFrame) -> np.ndarray:
        categorical, numeric = _split(features)
        encoded = self.encoder.transform(categorical)
        imputed = self.imputer.transform(numeric)
        return self.scaler.transform(np.hstack([encoded, imputed]))


def train_city(city_id: str) -> None:
    if city_id != "new_york":
        raise NotImplementedError(f"Training for {city_id} is not implemented yet.")
    train_new_york()


def train_new_york(
    examples_path: Path = EXAMPLES_PATH,
    model_path: Path = Path("artifacts/new_york/model.joblib"),
    metrics_path: Path = Path("artifacts/new_york/metrics.json"),
) -> tuple[Path, Path]:
    examples = pl.read_parquet(examples_path)
    train = examples.filter(pl.col("split") == "train")
    test = examples.filter(pl.col("split") == "test")
    y_train = train["label"].to_numpy()
    y_test = test["label"].to_numpy()

    preprocessor = FeaturePreprocessor().fit(train)
    x_train = preprocessor.transform(train)
    x_test = preprocessor.transform(test)

    logistic = LogisticRegression(max_iter=2000, random_state=0)
    logistic.fit(x_train, y_train)

    calibrated = CalibratedClassifierCV(
        LGBMClassifier(random_state=0, verbose=-1),
        cv=3,
    )
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
        "city": "new_york",
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


def _split(features: pl.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    categorical = (
        features.select(CATEGORICAL)
        .with_columns(pl.all().fill_null("__missing__").cast(pl.String))
        .to_numpy()
    )
    numeric = (
        features.select(NUMERIC)
        .with_columns(pl.col("previous_positive").cast(pl.Float64))
        .to_numpy()
        .astype(float)
    )
    return categorical, numeric
