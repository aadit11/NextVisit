"""README results table. Every number is read from artifacts/{city}/."""

import json
from pathlib import Path

import polars as pl

from nextvisit.cities import CITIES

START = "<!-- results:start -->"
END = "<!-- results:end -->"
MODEL_ORDER = ("repeat_last_visit", "logistic_regression", "lightgbm")
MODEL_LABELS = {
    "repeat_last_visit": "Repeat last visit",
    "logistic_regression": "Logistic regression",
    "lightgbm": "LightGBM",
}
METRIC_KEYS = ("pr_auc", "brier", "top_decile_capture")


def format_metric(value: float) -> str:
    return f"{float(value):.3f}"


def collect_rows(artifacts: Path, examples_root: Path) -> list[dict[str, object]]:
    """One row per city that already has a metrics file, in registry order."""
    rows: list[dict[str, object]] = []
    for city_id, spec in CITIES.items():
        metrics_path = artifacts / city_id / "metrics.json"
        if not metrics_path.exists():
            continue
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        models = metrics.get("models") or {}
        if "repeat_last_visit" not in models:
            raise ValueError(f"{metrics_path} is missing the repeat_last_visit row.")
        cutoff_path = artifacts / city_id / "cutoff.json"
        cutoff = None
        if cutoff_path.exists():
            cutoff = json.loads(cutoff_path.read_text(encoding="utf-8")).get("cutoff")
        window = _test_window(examples_root / city_id / "examples.parquet")
        beats = metrics.get("lightgbm_beats_baseline_pr_auc")
        if beats is None and "lightgbm" in models:
            beats = models["lightgbm"]["pr_auc"] > models["repeat_last_visit"]["pr_auc"]
        rows.append(
            {
                "city": city_id,
                "name": spec.name,
                "label": spec.label,
                "cutoff": cutoff,
                "test_start": window[0] if window else None,
                "test_end": window[1] if window else None,
                "test_rows": metrics.get("test_rows"),
                "models": models,
                "lightgbm_beats_baseline_pr_auc": bool(beats),
            }
        )
    return rows


def render_results(rows: list[dict[str, object]]) -> str:
    """Markdown for the cities that have metrics. The baseline row is always included."""
    if not rows:
        return "No metrics files are on disk yet.\n"
    parts = [render_city(row) for row in rows]
    return "\n".join(parts).rstrip() + "\n"


def render_city(row: dict[str, object]) -> str:
    models = row["models"]
    assert isinstance(models, dict)
    lines = [
        f"### {row['name']}",
        "",
        str(row["label"]),
        "",
        _window_sentence(row),
        "",
        "| Model | PR-AUC | Brier | Top-decile capture |",
        "|---|---:|---:|---:|",
    ]
    ordered = [key for key in MODEL_ORDER if key in models]
    ordered.extend(key for key in models if key not in MODEL_ORDER)
    for key in ordered:
        scores = models[key]
        cells = " | ".join(format_metric(scores[name]) for name in METRIC_KEYS)
        lines.append(f"| {MODEL_LABELS.get(key, key)} | {cells} |")
    lines.append("")
    if row["lightgbm_beats_baseline_pr_auc"]:
        lines.append("On PR-AUC, LightGBM is ahead of repeat last visit.")
    else:
        lines.append("On PR-AUC, repeat last visit is ahead of LightGBM. The baseline row stays.")
    lines.append("")
    return "\n".join(lines)


def write_readme(readme: Path, artifacts: Path, examples_root: Path) -> str:
    """Replace the marked results block. Returns the block that was written."""
    section = render_results(collect_rows(artifacts, examples_root))
    text = readme.read_text(encoding="utf-8")
    block = f"{START}\n{section.rstrip()}\n{END}"
    if START in text and END in text:
        before, rest = text.split(START, 1)
        _, after = rest.split(END, 1)
        updated = before + block + after
    else:
        needle = "## Folder structure"
        if needle in text:
            updated = text.replace(needle, block + "\n\n" + needle, 1)
        else:
            updated = text.rstrip() + "\n\n" + block + "\n"
    readme.write_text(updated, encoding="utf-8")
    return section


def _window_sentence(row: dict[str, object]) -> str:
    cutoff = row["cutoff"] or "not recorded"
    visits = row["test_rows"]
    visit_text = f"{visits} test visits." if visits is not None else "Test visit count is not recorded."
    start, end = row["test_start"], row["test_end"]
    if start and end:
        return f"Cutoff {cutoff}. Test window {start} through {end}. {visit_text}"
    return f"Cutoff {cutoff}. Test window is every target date after the cutoff. {visit_text}"


def _test_window(examples_path: Path) -> tuple[str, str] | None:
    if not examples_path.exists():
        return None
    frame = (
        pl.scan_parquet(examples_path)
        .filter(pl.col("split") == "test")
        .select(pl.col("target_date").min().alias("start"), pl.col("target_date").max().alias("end"))
        .collect()
    )
    start, end = frame["start"][0], frame["end"][0]
    if start is None or end is None:
        return None
    return start.isoformat(), end.isoformat()
