# Nextvisit

Nextvisit helps a diner judge a restaurant's hygiene. The page starts with a city and a map, then a search by name or id. Filters cover area, cuisine, grade, and whether the last inspection had no serious violation. The card shows the street, the last inspection, and reviews written in this app. Each city has its own model. The page does not show a percentage, and it does not show a closing list for the kitchen.

The last inspection is a set of rows: grade, score, date, how old it is, the result, whether recent visits are getting cleaner or worse, the area, and hours when they are known. A line under that box gives the city's grade and score range. New York's cuisine comes from the inspection file. The other cities use a nearby OpenStreetMap name match, or the restaurant name when the name itself says the cuisine. Austin's recent-visit row follows the score: falling, rising, or about the same. Its card does not list violation codes.

Codes are explained one by one. They are not grouped into illness, the room, or paperwork. A nearby line counts the same cuisine in the same area and ranks this grade among them. An inspection history lists this restaurant's own visits, newest first, and a short account written from those visits. The account names problems cited on more than one listed visit, problems that appear only on the latest visit, and whether that visit is the best or worst of the list. One visit stays a single visit. The card does not show a hygiene brief or the probability.

| City id | A serious problem in that sentence |
|---|---|
| `new_york` | The next cycle inspection includes a critical violation |
| `chicago` | The next result is Fail |
| `king_county` | The next inspection includes a serious violation |
| `los_angeles` | The next inspection includes a serious violation |
| `boston` | The next result is a fail |
| `san_francisco` | The next status is Conditional Pass or Closure |
| `austin` | The next routine score is below 90. The history uses the scores and does not mention codes. |

## Results

The tables below score the model behind the decision sentence. They are written by `scripts/record_results.py` from `artifacts/{city}/metrics.json`, and the cutoff comes from `artifacts/{city}/cutoff.json`. The diner page does not show these numbers. A city stays out of the table until those files exist. Repeat last visit is the baseline row in every city.

<!-- results:start -->
### New York

Next cycle inspection includes a critical violation

Cutoff 2026-05-07. Test window 2026-05-08 through 2026-10-15. 8615 test visits.

| Model | PR-AUC | Brier | Top-decile capture |
|---|---:|---:|---:|
| Repeat last visit | 0.902 | 0.183 | 0.100 |
| Logistic regression | 0.934 | 0.092 | 0.107 |
| LightGBM | 0.949 | 0.085 | 0.109 |

On PR-AUC, LightGBM is ahead of repeat last visit.

### Chicago

Next inspection result is Fail

Cutoff 2023-09-19. Test window 2023-09-20 through 2026-10-16. 28100 test visits.

| Model | PR-AUC | Brier | Top-decile capture |
|---|---:|---:|---:|
| Repeat last visit | 0.186 | 0.368 | 0.062 |
| Logistic regression | 0.288 | 0.154 | 0.173 |
| LightGBM | 0.306 | 0.150 | 0.184 |

On PR-AUC, LightGBM is ahead of repeat last visit.

### King County

Next inspection includes a serious violation

Cutoff 2025-12-01. Test window 2025-12-02 through 2026-10-17. 11485 test visits.

| Model | PR-AUC | Brier | Top-decile capture |
|---|---:|---:|---:|
| Repeat last visit | 0.412 | 0.277 | 0.193 |
| Logistic regression | 0.689 | 0.142 | 0.280 |
| LightGBM | 0.702 | 0.137 | 0.281 |

On PR-AUC, LightGBM is ahead of repeat last visit.

### Los Angeles County

Next inspection includes a serious violation

Cutoff 2026-04-07. Test window 2026-04-08 through 2026-09-30. 10449 test visits.

| Model | PR-AUC | Brier | Top-decile capture |
|---|---:|---:|---:|
| Repeat last visit | 0.384 | 0.349 | 0.139 |
| Logistic regression | 0.506 | 0.210 | 0.177 |
| LightGBM | 0.520 | 0.211 | 0.179 |

On PR-AUC, LightGBM is ahead of repeat last visit.

### Boston

Next inspection result is a fail

Cutoff 2023-11-09. Test window 2023-11-10 through 2026-10-16. 31112 test visits.

| Model | PR-AUC | Brier | Top-decile capture |
|---|---:|---:|---:|
| Repeat last visit | 0.407 | 0.657 | 0.061 |
| Logistic regression | 0.737 | 0.196 | 0.188 |
| LightGBM | 0.773 | 0.190 | 0.198 |

On PR-AUC, LightGBM is ahead of repeat last visit.

### San Francisco

Next inspection status is Conditional Pass or Closure

Cutoff 2026-01-09. Test window 2026-01-12 through 2026-10-15. 2513 test visits.

| Model | PR-AUC | Brier | Top-decile capture |
|---|---:|---:|---:|
| Repeat last visit | 0.037 | 0.059 | 0.111 |
| Logistic regression | 0.063 | 0.045 | 0.200 |
| LightGBM | 0.070 | 0.035 | 0.233 |

On PR-AUC, LightGBM is ahead of repeat last visit.

### Austin

Next routine inspection scores below 90

Cutoff 2026-04-01. Test window 2026-04-02 through 2026-09-24. 2725 test visits.

| Model | PR-AUC | Brier | Top-decile capture |
|---|---:|---:|---:|
| Repeat last visit | 0.576 | 0.209 | 0.204 |
| Logistic regression | 0.754 | 0.141 | 0.262 |
| LightGBM | 0.764 | 0.139 | 0.268 |

On PR-AUC, LightGBM is ahead of repeat last visit.
<!-- results:end -->

## Folder structure

```
README.md
AGENTS.md
pyproject.toml
.env.example
.gitignore

data/raw/{city}/                         # gitignored extracts
data/processed/{city}/                   # inspections, examples, codebook

src/nextvisit/
  domain.py
  cities/                                # one adapter per health department
    base.py
    new_york.py
    chicago.py
    king_county.py
    los_angeles.py
    boston.py
    san_francisco.py
    austin.py
  places.py                              # one row per restaurant, cuisine join, peer count
  history.py                             # recent-visit trend and Austin score direction
  peers.py                               # same cuisine in the same area
  cuisines.py                            # OpenStreetMap and name cuisine match
  osm.py                                 # hours, and a cuisine lookup for one place
  geocode.py                             # coordinates when the file has none
  accounts.py                            # login and reviews
  prepare/features.py                    # features must predate the target visit
  prepare/split.py                       # time cutoff per city
  model/baseline.py                      # repeat the previous visit
  model/train.py
  model/evaluate.py
  brief/generate.py                      # unused diner brief; the page calls generate_history
  brief/history.py                       # account written from the listed visits
  brief/faithfulness.py
  workorder/generate.py                  # not shown on the diner page
  workorder/faithfulness.py
  api/main.py                            # GET /cities, facets, search, map, and one restaurant

tests/
scripts/download.py
scripts/prepare.py
scripts/train.py
scripts/record_results.py              # README table from metrics.json
scripts/match_cuisines.py              # cuisine parquet for cities without one
scripts/geocode_missing.py

artifacts/{city}/                        # gitignored model.joblib, metrics.json, cutoff.json

web/                                     # map, search, filters, and the diner card
  src/ResultCard.tsx
  src/reading.ts                         # age, trend, scale, nearby line
```

## Status

Download, prepare, and train are built for all seven cities. A lookup shows the last inspection as labeled rows, the grade and score range, the recent-visit trend, the nearby comparison when cuisine and area exist, the inspection history, and reviews. Codes are read one by one. The problem-kind grouping is not on the page. Do not invent a history, a trend, a peer line, or a cuisine when the record does not support it. An unknown city id still raises `NotImplementedError`.

## Commands

```bash
uv sync
uv run pytest
uv run python scripts/record_results.py
uv run uvicorn nextvisit.api.main:app --reload
```

From `web/`: `npm install` then `npm run dev`.

Copy `.env.example` to `.env` before a hygiene-brief call. Training does not need that key.
