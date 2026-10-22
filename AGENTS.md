# Nextvisit — agent guide

Nextvisit helps a diner judge a restaurant's hygiene. The last inspection on the page is the health department's record. Around it, the page shows how old that inspection is, whether recent visits are getting cleaner or worse, what kind of problem the codes describe, and how this place compares with the same cuisine in the same area. Read this before changing the repo. `README.md` is the human-facing map. This file is the build contract.

## Invariants

1. One city, one model. Do not pool cities into a single classifier. The label strings live on each `CitySpec`. The diner page shows that label as a sentence and does not show the probability.
2. Features are strictly earlier than the target visit. `assert_features_before_target` must fail a same-day score, grade, or violation.
3. The split is temporal. `assign_split` sends target dates on or before the cutoff to train and later dates to test.
4. The baseline stays in the report. `repeat_last_visit` predicts the previous outcome. Score it with PR-AUC, Brier, and top-decile capture beside LightGBM.
5. Metrics are computed into `artifacts/{city}/metrics.json`. Do not type a number into the README. Do not print those metrics on the diner page.
6. The hygiene brief is one JSON call. It may mention only the inspection date, grade, score, trend, problem kind, peer comparison, and code text supplied from the record. A claim outside that record is rejected and the brief is empty. The diner page does not show a closing work order.
7. Austin has `has_work_order` false. `build_work_order("austin", ...)` returns an empty list and must not call a model. Austin's brief uses the score, its age, and whether recent scores are falling, and it does not mention violation codes.
8. Do not add a vector database or a chat endpoint. The codebook is a dictionary. The language-model surface is `brief/generate.py`. The peer comparison is a count of the same cuisine in the same area, not a model.
9. Do not commit `data/` extracts or `artifacts/` models. Phone numbers are dropped on ingest.
10. Download, prepare, and train raise `NotImplementedError` until that phase is actually built. Do not fake a brief, a trend, or a peer line so the API looks finished.

## Folder contract

```
src/nextvisit/cities/{city}.py          CitySpec only; column mapping belongs here
src/nextvisit/prepare/features.py
src/nextvisit/prepare/split.py
src/nextvisit/model/baseline.py
src/nextvisit/model/train.py
src/nextvisit/model/evaluate.py
src/nextvisit/brief/generate.py         # diner brief; claims must match the record
src/nextvisit/brief/faithfulness.py
src/nextvisit/workorder/generate.py     # not shown on the diner page
src/nextvisit/workorder/faithfulness.py
src/nextvisit/api/main.py               GET /cities and GET /cities/{city_id}/restaurants/{restaurant_id}
scripts/download.py
scripts/prepare.py
scripts/train.py
scripts/record_results.py               # writes the README table from metrics.json
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
uv run python scripts/record_results.py
uv run uvicorn nextvisit.api.main:app --reload
```

From `web/`: `npm install` then `npm run dev`.

## Out of scope

Payout reconciliation, menu prices, and a chat box. Do not scrape review sites. Do not hand-write restaurant rows so a demo has a score.
