# Nextvisit

Nextvisit helps a diner judge a restaurant's hygiene. The page starts with a city and a map, then a search by name or id. Filters cover area, cuisine, grade, and whether the last inspection had no serious violation. The card shows the street, the last inspection, and reviews written in this app. Each city has its own model. The page does not show a percentage, and it does not show a closing list for the kitchen.

The last inspection is a set of rows: grade, score, date, how old it is, the result, whether recent visits are getting cleaner or worse, the area, and hours when they are known. A line under that box gives the city's grade and score range. New York's cuisine comes from the inspection file. The other cities use a nearby OpenStreetMap name match, or the restaurant name when the name itself says the cuisine. Austin's recent-visit row follows the score: falling, rising, or about the same. Its card does not list violation codes.

Codes are explained one by one. They are not grouped into illness, the room, or paperwork. A nearby line counts the same cuisine in the same area and ranks this grade among them. Under that count, the card lists up to three of those restaurants with the name, last grade, and distance. A restaurant with a worse last grade or a worse last inspection stays off that list. The city's model chooses among the rest when the next inspection looks cleaner; otherwise the list is the nearest remaining places with coordinates. Choosing one draws a path on the map from the open restaurant to that place. An inspection history lists this restaurant's own visits, newest first, and a short account written from those visits. Above the violation codes, a summary counts the latest visit's rules and names which of those codes were cited before, which were added, and which earlier citations did not return. The account names problems cited on more than one listed visit, problems that appear only on the latest visit, and whether that visit is the best or worst of the list. One visit stays a single visit. The card does not show a hygiene brief or the probability.

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

The tables below score the model behind the decision sentence. They are written by `scripts/record_results.py` from `artifacts/{city}/metrics.json`, and the cutoff comes from `artifacts/{city}/cutoff.json`. The same script writes the notes under the tables. Weak-result notes read the metrics and the test rows. The ablation reads `artifacts/{city}/ablation.json`. The clean-previous slice reads `artifacts/{city}/slices.json`. `scripts/analyze.py` writes those two files and does not replace the saved model. The diner page does not show these numbers. A city stays out of the table until those files exist. Repeat last visit is the baseline row in every city.

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

<!-- analysis:start -->
### Where a higher PR-AUC still leaves a weak result

New York: LightGBM top-decile capture is 0.109 against 0.100 for repeat last visit. The label sticks, so the gain is the Brier score, 0.085 against 0.183.

Los Angeles County: logistic regression Brier is 0.210 and LightGBM Brier is 0.211. The tree does not improve calibration over logistic regression.

San Francisco: PR-AUC is 0.070. The test positive rate is 0.036. Top-decile capture is 0.233 against 0.111 for repeat last visit.

### Features removed one group at a time

Each row refits calibrated LightGBM on the same time split with that group removed. Change is that refit minus the full refit. A negative change means removing the group lowered PR-AUC.

#### New York

| Group removed | Columns | PR-AUC | Change |
|---|---|---:|---:|
| Full refit |  | 0.949 |  |
| Last outcome | previous_positive | 0.949 | +0.000 |
| Recency | days_since_previous, days_since_last_positive | 0.942 | -0.007 |
| History counts | prior_inspection_count, prior_positive_count, prior_violation_count, previous_violation_count | 0.947 | -0.002 |
| Severity | previous_score, previous_grade | 0.948 | -0.001 |
| Place | cuisine, borough | 0.944 | -0.004 |

#### Chicago

| Group removed | Columns | PR-AUC | Change |
|---|---|---:|---:|
| Full refit |  | 0.306 |  |
| Last outcome | previous_positive | 0.308 | +0.001 |
| Recency | days_since_previous, days_since_last_positive | 0.291 | -0.015 |
| History counts | prior_inspection_count, prior_positive_count, prior_violation_count, previous_violation_count | 0.271 | -0.036 |
| Place | facility_type, risk, zip | 0.308 | +0.001 |

#### King County

| Group removed | Columns | PR-AUC | Change |
|---|---|---:|---:|
| Full refit |  | 0.702 |  |
| Last outcome | previous_positive | 0.697 | -0.005 |
| Recency | days_since_previous, days_since_last_positive | 0.698 | -0.005 |
| History counts | prior_inspection_count, prior_positive_count, prior_violation_count, previous_violation_count | 0.690 | -0.012 |
| Severity | previous_score, previous_grade | 0.600 | -0.102 |
| Place | risk, zip | 0.684 | -0.019 |

In King County, removing a group other than the last outcome changes PR-AUC by 0.010 or more: History counts (-0.012), Severity (-0.102), Place (-0.019).

#### Los Angeles County

| Group removed | Columns | PR-AUC | Change |
|---|---|---:|---:|
| Full refit |  | 0.520 |  |
| Last outcome | previous_positive | 0.518 | -0.001 |
| Recency | days_since_previous, days_since_last_positive | 0.518 | -0.002 |
| History counts | prior_inspection_count, prior_positive_count, prior_violation_count, previous_violation_count | 0.508 | -0.012 |
| Severity | previous_score, previous_grade | 0.523 | +0.003 |
| Place | zip, pe_description | 0.483 | -0.037 |

#### Boston

| Group removed | Columns | PR-AUC | Change |
|---|---|---:|---:|
| Full refit |  | 0.773 |  |
| Last outcome | previous_positive | 0.768 | -0.005 |
| Recency | days_since_previous, days_since_last_positive | 0.759 | -0.013 |
| History counts | prior_inspection_count, prior_positive_count, prior_violation_count, previous_violation_count | 0.725 | -0.048 |
| Place | zip, license_description | 0.773 | +0.000 |

In Boston, removing a group other than the last outcome changes PR-AUC by 0.010 or more: Recency (-0.013), History counts (-0.048).

#### San Francisco

| Group removed | Columns | PR-AUC | Change |
|---|---|---:|---:|
| Full refit |  | 0.070 |  |
| Last outcome | previous_positive | 0.066 | -0.004 |
| Recency | days_since_previous, days_since_last_positive | 0.057 | -0.013 |
| History counts | prior_inspection_count, prior_positive_count, prior_violation_count, previous_violation_count | 0.067 | -0.003 |
| Place | permit_type, neighborhood | 0.064 | -0.006 |

#### Austin

| Group removed | Columns | PR-AUC | Change |
|---|---|---:|---:|
| Full refit |  | 0.764 |  |
| Last outcome | previous_positive | 0.764 | +0.000 |
| Recency | days_since_previous, days_since_last_positive | 0.765 | +0.001 |
| History counts | prior_inspection_count, prior_positive_count | 0.747 | -0.017 |
| Severity | previous_score | 0.729 | -0.035 |
| Place | zip | 0.760 | -0.004 |

### Previous inspection was clean

The slice keeps test visits whose previous inspection was clean. Repeat last visit scores every one of those rows 0, so it has no ranking there. LightGBM is the saved city model. A city is listed when the slice has at least 200 rows and 30 serious visits.

The largest gap between LightGBM PR-AUC and the serious-visit rate is King County: PR-AUC 0.542 against a serious-visit rate of 0.190 on 8065 rows (1533 serious).

| City | Rows | Serious visits | Serious-visit rate | LightGBM PR-AUC | Gap | Top-decile capture |
|---|---:|---:|---:|---:|---:|---:|
| New York | 1024 | 844 | 0.824 | 0.896 | +0.072 | 0.115 |
| Chicago | 21841 | 4806 | 0.220 | 0.314 | +0.094 | 0.167 |
| King County | 8065 | 1533 | 0.190 | 0.542 | +0.351 | 0.333 |
| Los Angeles County | 8221 | 2492 | 0.303 | 0.465 | +0.162 | 0.186 |
| Boston | 16485 | 10010 | 0.607 | 0.838 | +0.231 | 0.153 |
| San Francisco | 2447 | 86 | 0.035 | 0.069 | +0.034 | 0.256 |
| Austin | 1862 | 311 | 0.167 | 0.408 | +0.241 | 0.257 |
<!-- analysis:end -->

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
  model/analysis.py                      # feature groups, weak-result rules, clean-previous slice
  brief/history.py                       # account and code summary written from the listed visits
  api/main.py                            # GET /cities, facets, search, map, and one restaurant

tests/
scripts/download.py
scripts/prepare.py
scripts/train.py
scripts/analyze.py                     # ablation and the clean-previous slice
scripts/record_results.py              # README table, weak-result notes, ablation, and slice
scripts/match_cuisines.py              # cuisine parquet for cities without one
scripts/geocode_missing.py

artifacts/{city}/                        # gitignored model.joblib, metrics.json, ablation.json, slices.json

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
uv run python scripts/analyze.py
uv run python scripts/record_results.py
uv run uvicorn nextvisit.api.main:app --reload
```

From `web/`: `npm install` then `npm run dev`.
