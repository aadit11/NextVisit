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

artifacts/{city}/                        # gitignored model.joblib, metrics.json, cutoff.json

web/                                     # city, then name or id
```

## Status

This commit is the folder structure and the rules that do not depend on a download: the city registry, the time split, the leakage check, the repeat-last-visit baseline, and the work-order faithfulness check. Download, example building, and model fitting are the next phases. `GET /cities/{city}/restaurants/{id}` returns 501 until a model artifact exists.

## Commands

```bash
uv sync
uv run pytest
uv run uvicorn nextvisit.api.main:app --reload
```

From `web/`: `npm install` then `npm run dev`.

Copy `.env.example` to `.env` before a work-order call. Training does not need that key.
