# Nextvisit

Nextvisit ranks a restaurant by the chance its next inspection goes badly, using that city's public inspection history. The search starts with a city. Each city has its own label, its own codebook, and its own model.

Seven jurisdictions are wired in:

| City id | Outcome the model ranks | Work order |
|---|---|---|
| `new_york` | Next cycle inspection includes a critical violation | Yes. Cuisine is in the file. |
| `chicago` | Next inspection result is Fail | Yes |
| `king_county` | Next inspection includes a serious violation | Yes |
| `los_angeles` | Next inspection includes a serious points violation | Yes |
| `boston` | Next inspection result is a fail | Yes |
| `san_francisco` | Next status is Conditional Pass or Closure | Yes, when the file includes the code text |
| `austin` | Next routine score is below 90 | No. The file has scores only. |

A language model is not part of the ranker. After the codes are chosen, one JSON call writes a closing work order for cities that publish violation text. Python rejects a step that cites another code or drops a span of the official description. Austin returns an empty work order.

## Results

Held-out scores below are written by `scripts/record_results.py`. Each number comes from `artifacts/{city}/metrics.json`, and the cutoff comes from `artifacts/{city}/cutoff.json`. A city stays out of the table until those files exist. Repeat last visit is the baseline row in every city.

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

Next inspection includes a violation the county marks as serious

Cutoff 2025-12-01. Test window 2025-12-02 through 2026-10-17. 11485 test visits.

| Model | PR-AUC | Brier | Top-decile capture |
|---|---:|---:|---:|
| Repeat last visit | 0.412 | 0.277 | 0.193 |
| Logistic regression | 0.689 | 0.142 | 0.280 |
| LightGBM | 0.702 | 0.137 | 0.281 |

On PR-AUC, LightGBM is ahead of repeat last visit.

### Los Angeles County

Next inspection includes a serious violation in the county points system

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
  prepare/features.py                    # features must predate the target visit
  prepare/split.py                       # time cutoff per city
  model/baseline.py                      # repeat the previous visit
  model/train.py
  model/evaluate.py
  workorder/generate.py
  workorder/faithfulness.py
  api/main.py                            # GET /cities and GET /cities/{city}/restaurants/{id}

tests/
scripts/download.py
scripts/prepare.py
scripts/train.py
scripts/record_results.py              # README table from metrics.json

artifacts/{city}/                        # gitignored model.joblib, metrics.json, cutoff.json

web/                                     # city, then name or id
```

## Status

A city is scored after its own download, prepare, and train steps. Until then, download and train raise `NotImplementedError`, and a lookup returns 501. The results table lists only cities whose metrics files are on disk.

## Commands

```bash
uv sync
uv run pytest
uv run python scripts/record_results.py
uv run uvicorn nextvisit.api.main:app --reload
```

From `web/`: `npm install` then `npm run dev`.

Copy `.env.example` to `.env` before a work-order call. Training does not need that key.
