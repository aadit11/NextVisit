# Nextvisit — agent guide

Nextvisit ranks the next inspection for seven cities. Read this before changing the repo. `README.md` is the human-facing map. This file is the build contract.

## Invariants

1. One city, one label, one model. Do not pool cities into a single classifier. The label strings live on each `CitySpec`.
2. Features are strictly earlier than the target visit. `assert_features_before_target` must fail a same-day score, grade, or violation.
3. The split is temporal. `assign_split` sends target dates on or before the cutoff to train and later dates to test.
4. The baseline stays in the report. `repeat_last_visit` predicts the previous outcome. Score it with PR-AUC, Brier, and top-decile capture beside LightGBM.
5. Metrics are computed into `artifacts/{city}/metrics.json`. Do not type a number into the README.
6. The work order is one JSON call after the ranker chooses codes. `faithfulness_errors` rejects an unknown code, a dropped code, a station outside `STATIONS`, a `source_span` that is not an exact substring of the official description, and a step that drops that span. Require the cuisine name only when `CitySpec.cuisine_in_source` is true.
7. Austin has `has_work_order` false. `build_work_order("austin", ...)` returns an empty list and must not call a model.
8. Do not add a vector database or a chat endpoint. The codebook is a dictionary. The language-model surface is `workorder/generate.py`.
9. Do not commit `data/` extracts or `artifacts/` models. Phone numbers are dropped on ingest.
10. Download, prepare, and train raise `NotImplementedError` until that phase is actually built. Do not fake a probability so the API looks finished.

## Folder contract

```
src/nextvisit/cities/{city}.py          CitySpec only; column mapping belongs here
src/nextvisit/prepare/features.py
src/nextvisit/prepare/split.py
src/nextvisit/model/baseline.py
src/nextvisit/model/train.py
src/nextvisit/model/evaluate.py
src/nextvisit/workorder/generate.py
src/nextvisit/workorder/faithfulness.py
src/nextvisit/api/main.py               GET /cities and GET /cities/{city_id}/restaurants/{restaurant_id}
scripts/download.py
scripts/prepare.py
scripts/train.py
tests/test_collapse.py
tests/test_leakage.py
tests/test_split.py
tests/test_baseline.py
tests/test_faithfulness.py
tests/test_austin_abstains_work_order.py
web/src/App.tsx
web/src/api.ts
```

City ids: `new_york`, `chicago`, `king_county`, `los_angeles`, `boston`, `san_francisco`, `austin`.

## Commands

```bash
uv sync
uv run pytest
uv run python scripts/download.py --city new_york
uv run python scripts/prepare.py --city new_york
uv run python scripts/train.py --city new_york
uv run uvicorn nextvisit.api.main:app --reload
```

From `web/`: `npm install` then `npm run dev`.

## Out of scope

Payout reconciliation, menu prices, and a chat box. Do not scrape review sites. Do not hand-write restaurant rows so a demo has a score.
