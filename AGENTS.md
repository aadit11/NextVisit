# Nextvisit — agent guide

Nextvisit helps a diner judge a restaurant's hygiene. The last inspection on the page is the health department's record. The card lists the grade, score, date, age, result, recent-visit trend, area, and hours. A line under that box gives the city's grade and score range. Codes are explained one by one. They are not grouped into illness, the room, or paperwork. The nearby line counts the same cuisine in the same area, then lists a few of those restaurants with the distance. Choosing one draws a path on the map. Read this before changing the repo. `README.md` is the human-facing map. This file is the build contract.

## Invariants

1. One city, one model. Do not pool cities into a single classifier. The label strings live on each `CitySpec`. The diner page shows that label as a sentence and does not show the probability.
2. Features are strictly earlier than the target visit. `assert_features_before_target` must fail a same-day score, grade, or violation.
3. The split is temporal. `assign_split` sends target dates on or before the cutoff to train and later dates to test.
4. The baseline stays in the report. `repeat_last_visit` predicts the previous outcome. Score it with PR-AUC, Brier, and top-decile capture beside LightGBM.
5. Metrics are computed into `artifacts/{city}/metrics.json`. The feature ablation is computed into `artifacts/{city}/ablation.json`, and the clean-previous slice into `artifacts/{city}/slices.json`. Do not type a number into the README. Do not print those metrics on the diner page.
6. The inspection history account is written from the listed visits. It names code text cited on more than one listed visit, code text that appears only on the latest visit, and whether that visit is the best or worst of the list. It does not call a model. One visit has no account. A code summary above the violation list is written from the same visits: how many rules the latest visit cited, which of those were cited before, which were added, and which earlier citations did not return. Austin has no code summary. The diner page does not show a hygiene brief or a separate next-inspection section.
7. Austin's card follows the score (falling, rising, or steady) and does not list violation codes. Austin's history uses the scores and does not mention violation codes.
8. Do not add a vector database or a chat endpoint. The codebook is a dictionary. The inspection history account and the code summary are written in `brief/history.py` from the listed visits. The peer comparison count is the same cuisine in the same area. Under that count, the card lists up to three real restaurants from that group with the name, last grade, and distance. A restaurant with a worse last grade or a worse last inspection stays off that list. The city's own model chooses among the rest when the next inspection looks cleaner. When it finds none, the list is the nearest remaining places that have coordinates, and the count sentence stays. Choosing one draws a path on the map from the open restaurant to that place.
9. Do not commit `data/` extracts or `artifacts/` models. Phone numbers are dropped on ingest. Cuisine matches belong in `data/cuisines/`. Geocodes belong in `data/geocodes/`.
10. Download, prepare, and train are built for the seven city ids. An unknown city id still raises `NotImplementedError`. Do not fake a brief, a trend, a peer line, or a cuisine. New York's cuisine comes from the inspection file. The other cities use `data/cuisines/{city}.parquet` from `scripts/match_cuisines.py`: a nearby OpenStreetMap name match, or the restaurant name when the words say the cuisine.

## Folder contract

```
src/nextvisit/cities/{city}.py          CitySpec only; column mapping belongs here
src/nextvisit/places.py                 one restaurant row, cuisine join, peer count, cleaner nearby list
src/nextvisit/history.py                recent-visit trend and Austin score direction
src/nextvisit/peers.py                  same cuisine in the same area
src/nextvisit/cuisines.py               OpenStreetMap and name cuisine match
src/nextvisit/osm.py                    hours, and a cuisine lookup for one place
src/nextvisit/geocode.py                coordinates when the inspection file has none
src/nextvisit/accounts.py               login and reviews
src/nextvisit/prepare/features.py
src/nextvisit/prepare/split.py
src/nextvisit/model/baseline.py
src/nextvisit/model/train.py
src/nextvisit/model/evaluate.py
src/nextvisit/model/analysis.py         # feature groups, weak-result rules, clean-previous slice
src/nextvisit/brief/history.py          # account and code summary written from the listed visits
src/nextvisit/api/main.py               GET /cities, facets, search, map, and one restaurant
scripts/download.py
scripts/prepare.py
scripts/train.py
scripts/analyze.py                      # ablation and the clean-previous slice
scripts/record_results.py               # writes the README table, the weak-result notes, the ablation, and the slice
scripts/match_cuisines.py
scripts/geocode_missing.py
tests/test_collapse.py
tests/test_leakage.py
tests/test_split.py
tests/test_baseline.py
web/src/App.tsx
web/src/ResultCard.tsx
web/src/reading.ts                      # age, trend, scale, nearby line
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
uv run python scripts/analyze.py
uv run python scripts/record_results.py
uv run python scripts/match_cuisines.py
uv run uvicorn nextvisit.api.main:app --reload
```

From `web/`: `npm install` then `npm run dev`.

## Out of scope

Payout reconciliation, menu prices, and a chat box. Do not scrape review sites. Do not hand-write restaurant rows so a demo has a score. Do not group violation codes into illness, the room, or paperwork unless that feature is asked for.
