"""Refit each city with one feature group removed, and score the clean-previous slice.

Writes artifacts/{city}/ablation.json and artifacts/{city}/slices.json.
Does not replace model.joblib.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import polars as pl

from nextvisit.cities import CITIES
from nextvisit.model.analysis import groups_for, previous_clean_slice, without_group
from nextvisit.model.evaluate import score_probabilities
from nextvisit.model.train import EXAMPLES_PATHS, PREPROCESSORS, FeaturePreprocessor, calibrated_lightgbm


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the ablation and the clean-previous slice.")
    parser.add_argument("--city", default="all", choices=["all", *CITIES])
    args = parser.parse_args()
    targets = list(CITIES) if args.city == "all" else [args.city]
    for city_id in targets:
        run_city(city_id)


def run_city(city_id: str) -> None:
    examples_path = EXAMPLES_PATHS[city_id]
    if not examples_path.exists():
        raise FileNotFoundError(f"{examples_path} is not on disk.")
    examples = pl.read_parquet(examples_path)
    train = examples.filter(pl.col("split") == "train")
    test = examples.filter(pl.col("split") == "test")
    artifact_dir = Path("artifacts") / city_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    slice_path = artifact_dir / "slices.json"
    slice_payload = _saved_slice(city_id, test, artifact_dir / "model.joblib")
    _write(slice_path, slice_payload)
    print(f"{city_id}: wrote {slice_path}", flush=True)

    ablation_path = artifact_dir / "ablation.json"
    _write(ablation_path, _ablation(city_id, train, test))
    print(f"{city_id}: wrote {ablation_path}", flush=True)


def _ablation(city_id: str, train: pl.DataFrame, test: pl.DataFrame) -> dict[str, object]:
    city_preprocessor = PREPROCESSORS[city_id]()
    categorical = tuple(city_preprocessor.categorical)
    numeric = tuple(city_preprocessor.numeric)
    y_train = train["label"].to_numpy()
    y_test = test["label"].to_numpy()
    full = _fit_scores(categorical, numeric, train, test, y_train, y_test)
    print(f"{city_id}: full refit PR-AUC {full['pr_auc']:.3f}", flush=True)
    groups = []
    for group in groups_for(categorical, numeric):
        kept_categorical, kept_numeric = without_group(categorical, numeric, group)
        scores = _fit_scores(kept_categorical, kept_numeric, train, test, y_train, y_test)
        groups.append(
            {
                "id": group.id,
                "label": group.label,
                "columns": list(group.columns),
                "metrics": scores,
                "pr_auc_change": scores["pr_auc"] - full["pr_auc"],
            }
        )
        print(
            f"{city_id}: without {group.id} PR-AUC {scores['pr_auc']:.3f} "
            f"({scores['pr_auc'] - full['pr_auc']:+.3f})",
            flush=True,
        )
    return {"city": city_id, "full": full, "groups": groups}


def _fit_scores(
    categorical: tuple[str, ...],
    numeric: tuple[str, ...],
    train: pl.DataFrame,
    test: pl.DataFrame,
    y_train,
    y_test,
) -> dict[str, float]:
    preprocessor = FeaturePreprocessor()
    preprocessor.categorical = categorical
    preprocessor.numeric = numeric
    preprocessor.fit(train)
    model = calibrated_lightgbm()
    model.fit(preprocessor.transform(train), y_train)
    probabilities = model.predict_proba(preprocessor.transform(test))[:, 1]
    return score_probabilities(y_test, probabilities)


def _saved_slice(city_id: str, test: pl.DataFrame, model_path: Path) -> dict[str, object]:
    if not model_path.exists():
        return {"city": city_id, "slice": "previous_clean", "available": False, "eligible": False}
    bundle = joblib.load(model_path)
    probabilities = bundle["model"].predict_proba(bundle["preprocessor"].transform(test))[:, 1]
    payload = previous_clean_slice(
        test["label"].to_numpy(),
        probabilities,
        test["previous_positive"].to_numpy(),
    )
    payload["city"] = city_id
    payload["available"] = True
    return payload


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
