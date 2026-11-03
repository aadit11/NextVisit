"""The README results table is rendered from metrics files, including the baseline."""

import json
from pathlib import Path

import pytest

from nextvisit.cities import CITIES
from nextvisit.report import (
    ANALYSIS_END,
    ANALYSIS_START,
    END,
    START,
    collect_rows,
    format_metric,
    render_analysis,
    render_results,
    write_readme,
)


def test_table_changes_when_metrics_change(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    readme = tmp_path / "README.md"
    readme.write_text(f"# Nextvisit\n\n{START}\n\n{END}\n", encoding="utf-8")
    _write_city(artifacts, "new_york", baseline=0.4, lightgbm=0.5, beats=True)
    write_readme(readme, artifacts, tmp_path / "examples")
    first = readme.read_text(encoding="utf-8")

    _write_city(artifacts, "new_york", baseline=0.4, lightgbm=0.8, beats=True)
    write_readme(readme, artifacts, tmp_path / "examples")
    second = readme.read_text(encoding="utf-8")

    assert first != second
    assert format_metric(0.8) in second
    assert "Repeat last visit" in second
    assert "Cutoff 2026-01-01" in second
    assert "Test window is every target date after the cutoff." in second


def test_baseline_row_stays_when_lightgbm_loses(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    _write_city(artifacts, "chicago", baseline=0.55, lightgbm=0.2, beats=False)
    rendered = render_results(collect_rows(artifacts, tmp_path / "examples"))
    assert "Repeat last visit" in rendered
    assert format_metric(0.55) in rendered
    assert format_metric(0.2) in rendered
    assert "repeat last visit is ahead of LightGBM" in rendered


def test_city_without_metrics_is_omitted(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    _write_city(artifacts, "austin", baseline=0.3, lightgbm=0.35, beats=True)
    rows = collect_rows(artifacts, tmp_path / "examples")
    assert [row["city"] for row in rows] == ["austin"]
    assert "King County" not in render_results(rows)


def test_readme_analysis_matches_artifact_files() -> None:
    artifacts = Path("artifacts")
    if not any((artifacts / city_id / "ablation.json").exists() for city_id in CITIES):
        pytest.skip("no ablation files on this checkout")
    readme = Path("README.md").read_text(encoding="utf-8")
    section = render_analysis(collect_rows(artifacts, Path("data/processed")), artifacts, Path("data/processed"))
    assert ANALYSIS_START in readme and ANALYSIS_END in readme
    assert section.strip() in readme


def test_missing_baseline_is_rejected(tmp_path: Path) -> None:
    city_dir = tmp_path / "artifacts" / "boston"
    city_dir.mkdir(parents=True, exist_ok=True)
    (city_dir / "metrics.json").write_text(
        json.dumps({"city": "boston", "test_rows": 1, "models": {"lightgbm": _scores(0.4)}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="repeat_last_visit"):
        collect_rows(tmp_path / "artifacts", tmp_path / "examples")


def test_readme_matches_artifact_files() -> None:
    artifacts = Path("artifacts")
    if not any((artifacts / city_id / "metrics.json").exists() for city_id in CITIES):
        pytest.skip("no metrics files on this checkout")
    readme = Path("README.md").read_text(encoding="utf-8")
    section = render_results(collect_rows(artifacts, Path("data/processed")))
    assert section.strip() in readme


def _write_city(artifacts: Path, city_id: str, baseline: float, lightgbm: float, beats: bool) -> None:
    city_dir = artifacts / city_id
    city_dir.mkdir(parents=True, exist_ok=True)
    (city_dir / "metrics.json").write_text(
        json.dumps(
            {
                "city": city_id,
                "test_rows": 10,
                "models": {
                    "repeat_last_visit": _scores(baseline),
                    "logistic_regression": _scores(baseline),
                    "lightgbm": _scores(lightgbm),
                },
                "lightgbm_beats_baseline_pr_auc": beats,
            }
        ),
        encoding="utf-8",
    )
    (city_dir / "cutoff.json").write_text(
        json.dumps({"city": city_id, "cutoff": "2026-01-01"}),
        encoding="utf-8",
    )


def _scores(pr_auc: float) -> dict[str, float]:
    return {"pr_auc": pr_auc, "brier": 0.25, "top_decile_capture": 0.1}
