"""README results table. Every number is read from artifacts/{city}/."""

import json
from pathlib import Path

import polars as pl

from nextvisit.cities import CITIES
from nextvisit.model.analysis import (
    other_group_callout,
    read_json,
    test_positive_rate,
    weak_paragraphs,
)

START = "<!-- results:start -->"
END = "<!-- results:end -->"
ANALYSIS_START = "<!-- analysis:start -->"
ANALYSIS_END = "<!-- analysis:end -->"
MODEL_ORDER = ("repeat_last_visit", "logistic_regression", "lightgbm")
MODEL_LABELS = {
    "repeat_last_visit": "Repeat last visit",
    "logistic_regression": "Logistic regression",
    "lightgbm": "LightGBM",
}
METRIC_KEYS = ("pr_auc", "brier", "top_decile_capture")


def format_metric(value: float) -> str:
    return f"{float(value):.3f}"


def format_change(value: float) -> str:
    return f"{float(value):+.3f}"


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


def render_analysis(rows: list[dict[str, object]], artifacts: Path, examples_root: Path) -> str:
    """Weak-result notes, the ablation tables, and the clean-previous slice."""
    lines = ["### Where a higher PR-AUC still leaves a weak result", ""]
    notes: list[str] = []
    for row in rows:
        models = row["models"]
        assert isinstance(models, dict)
        rate = test_positive_rate(examples_root / str(row["city"]) / "examples.parquet")
        notes.extend(weak_paragraphs(str(row["name"]), models, rate))
    if notes:
        for note in notes:
            lines.append(note)
            lines.append("")
    else:
        lines.append("No city matches the weak-result rules on the files that are on disk.")
        lines.append("")

    lines.extend(
        [
            "### Features removed one group at a time",
            "",
            "Each row refits calibrated LightGBM on the same time split with that group removed. "
            "Change is that refit minus the full refit. A negative change means removing the group lowered PR-AUC.",
            "",
        ]
    )
    found_ablation = False
    for row in rows:
        payload = read_json(artifacts / str(row["city"]) / "ablation.json")
        if payload is None:
            continue
        found_ablation = True
        lines.extend(_ablation_city(row, payload))
    if not found_ablation:
        lines.append("No ablation files are on disk yet.")
        lines.append("")

    lines.extend(
        [
            "### Previous inspection was clean",
            "",
            "The slice keeps test visits whose previous inspection was clean. "
            "Repeat last visit scores every one of those rows 0, so it has no ranking there. "
            "LightGBM is the saved city model. A city is listed when the slice has at least 200 rows and 30 serious visits.",
            "",
        ]
    )
    lines.extend(_slice_section(rows, artifacts))
    return "\n".join(lines).rstrip() + "\n"


def write_readme(readme: Path, artifacts: Path, examples_root: Path) -> str:
    """Replace the marked results and analysis blocks. Returns the results block."""
    rows = collect_rows(artifacts, examples_root)
    section = render_results(rows)
    analysis = render_analysis(rows, artifacts, examples_root)
    text = readme.read_text(encoding="utf-8")
    text = _replace_block(text, START, END, section, "## Folder structure")
    analysis_block = f"{ANALYSIS_START}\n{analysis.rstrip()}\n{ANALYSIS_END}"
    if ANALYSIS_START in text and ANALYSIS_END in text:
        text = _replace_block(text, ANALYSIS_START, ANALYSIS_END, analysis, "## Folder structure")
    elif END in text:
        text = text.replace(END, END + "\n\n" + analysis_block, 1)
    else:
        text = _replace_block(text, ANALYSIS_START, ANALYSIS_END, analysis, "## Folder structure")
    readme.write_text(text, encoding="utf-8")
    return section


def _replace_block(text: str, start: str, end: str, body: str, insert_before: str) -> str:
    block = f"{start}\n{body.rstrip()}\n{end}"
    if start in text and end in text:
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        return before + block + after
    if insert_before in text:
        return text.replace(insert_before, block + "\n\n" + insert_before, 1)
    return text.rstrip() + "\n\n" + block + "\n"


def _ablation_city(row: dict[str, object], payload: dict[str, object]) -> list[str]:
    full = payload["full"]
    groups = payload["groups"]
    assert isinstance(full, dict)
    assert isinstance(groups, list)
    lines = [
        f"#### {row['name']}",
        "",
        "| Group removed | Columns | PR-AUC | Change |",
        "|---|---|---:|---:|",
        f"| Full refit |  | {format_metric(full['pr_auc'])} |  |",
    ]
    for group in groups:
        columns = ", ".join(group["columns"])
        lines.append(
            f"| {group['label']} | {columns} | {format_metric(group['metrics']['pr_auc'])} | "
            f"{format_change(group['pr_auc_change'])} |"
        )
    lines.append("")
    callout = other_group_callout(str(row["city"]), str(row["name"]), groups)
    if callout:
        lines.append(callout)
        lines.append("")
    return lines


def _slice_section(rows: list[dict[str, object]], artifacts: Path) -> list[str]:
    found = False
    eligible: list[tuple[dict[str, object], dict[str, object]]] = []
    for row in rows:
        path = artifacts / str(row["city"]) / "slices.json"
        if not path.exists():
            continue
        found = True
        payload = read_json(path)
        if payload and payload.get("available") and payload.get("eligible"):
            eligible.append((row, payload))
    if not found:
        return ["No slice files are on disk yet.", ""]
    if not eligible:
        return ["No city has 200 clean-previous test rows and 30 serious visits in that slice.", ""]
    headline_row, headline = max(eligible, key=lambda item: float(item[1]["pr_auc_gap"]))
    lightgbm = headline["lightgbm"]
    assert isinstance(lightgbm, dict)
    lines = [
        (
            f"The largest gap between LightGBM PR-AUC and the serious-visit rate is {headline_row['name']}: "
            f"PR-AUC {format_metric(lightgbm['pr_auc'])} against a serious-visit rate of "
            f"{format_metric(headline['positive_rate'])} on {headline['rows']} rows "
            f"({headline['serious_visits']} serious)."
        ),
        "",
        "| City | Rows | Serious visits | Serious-visit rate | LightGBM PR-AUC | Gap | Top-decile capture |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row, payload in eligible:
        scores = payload["lightgbm"]
        assert isinstance(scores, dict)
        lines.append(
            f"| {row['name']} | {payload['rows']} | {payload['serious_visits']} | "
            f"{format_metric(payload['positive_rate'])} | {format_metric(scores['pr_auc'])} | "
            f"{format_change(payload['pr_auc_gap'])} | {format_metric(scores['top_decile_capture'])} |"
        )
    lines.append("")
    return lines


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
