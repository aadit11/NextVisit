"""Fit logistic regression, LightGBM, and calibration for one city.

Writes artifacts/{city}/model.joblib and artifacts/{city}/metrics.json.
"""


def train_city(city_id: str) -> None:
    raise NotImplementedError(f"Training for {city_id} is not implemented yet.")
