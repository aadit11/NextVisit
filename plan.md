# Nextvisit development plan

Build one city until a lookup returns a real probability, then repeat the adapter for the other cities. Do not train a shared model. Do not invent a score when a file or a history is missing.

What already exists: the city registry, the leakage check, the time split, the repeat-last-visit baseline, the work-order faithfulness check, empty data folders, and an API that lists cities and returns 501 for a restaurant.

## 1. Environment

1. Install Python 3.12 and `uv`.
2. From the `NextVisit` repo root, run `uv sync`.
3. Run `uv run pytest`. The current tests must pass before new work: city registry, leakage, time split, baseline, faithfulness, and Austin's empty work order.
4. Copy `.env.example` to `.env`. Leave the work-order keys empty until step 8.

Done when `uv run pytest` is green on a clean checkout.

## 2. New York download

1. Implement `scripts/download.py` for `--city new_york` only.
2. Page the SODA endpoint in `src/nextvisit/cities/new_york.py` (`43nn-pn8j`).
3. Keep `camis`, name, borough, cuisine, inspection date, inspection type, violation code, violation description, critical flag, score, grade, latitude, longitude, and zip. Drop `phone` before the file is written.
4. Write `data/raw/new_york/inspections.parquet`. Do not commit it.

Done when a second run overwrites the parquet, the file has no phone column, and the script still raises `NotImplementedError` for every other city.

## 3. Collapse New York inspections

1. Keep rows whose `inspection_type` starts with `Cycle Inspection`.
2. Drop `inspection_date` of `1900-01-01`.
3. Collapse violation rows to one inspection per `camis` + inspection date.
4. Mark the inspection positive when any row has `critical_flag` of `Critical`.
5. Write `data/processed/new_york/inspections.parquet`.
6. Build `data/processed/new_york/codebook.parquet` from distinct violation code and official description.

Done when a fixture with two violations on one date becomes one inspection, an uninspected permit disappears, and `tests/test_collapse.py` covers that fixture.

## 4. Examples and the time split

1. Sort each `camis` by inspection date.
2. Create an example only when a cycle inspection has a later cycle inspection. The later visit is the target. The label is that visit's positive flag.
3. Features may use cuisine, borough, days since the previous cycle inspection, prior violation counts and recency, whether prior visits were positive, and the previous visit's score and grade.
4. Call `assert_features_before_target` while building features. The target visit's score, grade, and violation codes stay out.
5. Restaurants with no earlier cycle inspection are not examples. Lookups for them abstain.
6. After the example table exists, choose one cutoff date and save it in `artifacts/new_york/cutoff.json`. `assign_split` sends target dates on or before that cutoff to train and later dates to test.
7. Write `data/processed/new_york/examples.parquet`.

Done when `tests/test_leakage.py` fails a same-day feature and `tests/test_split.py` matches the cutoff file.

## 5. Train and score New York

1. Fit three models on the training period only: `repeat_last_visit`, logistic regression, and LightGBM.
2. Calibrate LightGBM with `CalibratedClassifierCV` on training-period data only.
3. Score the test period with precision-recall AUC, Brier score, and the share of true positive visits captured in the top 10% of predicted risk.
4. Write all three models' metrics to `artifacts/new_york/metrics.json`. Write the calibrated LightGBM model to `artifacts/new_york/model.joblib`.
5. If LightGBM does not beat the baseline on precision-recall AUC, keep the baseline numbers in the file.

Done when `uv run python scripts/train.py --city new_york` finishes without a hand-typed metric, and both artifact files exist and are gitignored.

## 6. New York lookup

1. Replace the 501 response in `src/nextvisit/api/main.py` for a New York id that has history.
2. `GET /cities/new_york/restaurants/{camis}` returns the name, cuisine, calibrated probability, the label sentence from `CitySpec`, the violation codes that drove the score, and `abstained: false`.
3. A CAMIS with no prior cycle inspection returns `abstained: true`, no probability, and an empty code list.
4. An unknown CAMIS returns 404.

Done when a real CAMIS from the processed file returns a probability between 0 and 1, and a `1900-01-01` permit abstains.

## 7. Closing work order

1. Implement the hosted call in `src/nextvisit/workorder/generate.py` for cities with `has_work_order` true.
2. Send only the cuisine, the predicted codes, and the official descriptions for those codes.
3. Require JSON items with `station`, `violation_code`, `source_span`, and `step`. Stations stay inside the set in `faithfulness.py`.
4. Run `faithfulness_errors` before the API returns the order. On failure, return the probability and the codes with an empty work order and a reason, not a rewritten paragraph.
5. For New York, `require_cuisine` is true because `cuisine_in_source` is true.
6. Read `WORKORDER_API_KEY`, `WORKORDER_BASE_URL`, and `WORKORDER_MODEL` from the environment. `pytest` and training must still pass with those unset.

Done when `tests/test_faithfulness.py` still rejects an extra code and a span that is not in the codebook, and one live New York lookup shows a step that contains both the cuisine and an exact official span.

## 8. Web page for New York

1. In `web/`, run `npm install` and `npm run dev`.
2. Load cities from `GET /cities`.
3. On submit, call `GET /cities/{city}/restaurants/{id}` and render the probability, the label sentence, the codes, and the work order.
4. Render abstain as a finished state: the name and the line "No score. This restaurant has no completed inspection to learn from."
5. Render an empty Austin work order without treating it as an error. Austin's button path can wait until step 10, but the empty-order state should already be visible in the component.

Done when a New York CAMIS typed into the page matches the API JSON.

## 9. Repeat the adapter, one city at a time

Finish the same download, collapse, example, train, and lookup path for each city before starting the next. Use that city's label from its `CitySpec`. Keep a separate cutoff, metrics file, and `model.joblib`.

Do them in this order:

1. **Chicago.** One row per inspection in the source, violations packed in text. Label: next result is Fail. Parse violation numbers and comments into the codebook. No cuisine field, so the work-order step does not have to contain a cuisine name.
2. **King County.** One row per violation, 2021 onward. Label: the next inspection includes a violation the county marks as serious. Confirm the serious-class values from the file before coding them.
3. **Los Angeles County.** Join the inspections file and the violations file on the inspection id. Leave out Pasadena, Long Beach, and Vernon. Label: the next inspection includes a serious points violation, using the county's own point rule from the file.
4. **Boston.** Label: the next inspection result is a fail. Violation description and level come from the inspection rows.
5. **San Francisco.** Label: the next status is Conditional Pass or Closure. Build a work order only when the row includes official wording for the code. Otherwise return the probability, the codes, and an empty work order.

Done when each city has its own metrics file, a held-out test split, and one real id that returns a probability. `scripts/download.py --city all` and `scripts/train.py --city all` complete.

## 10. Austin

1. Download the scores file. The restaurant id is `facility_id`. Keep routine inspections.
2. Label: the next routine score is below 90.
3. Train and serve the probability the same way as the other cities.
4. Do not call the work-order model. `build_work_order("austin", ...)` stays an empty list.

Done when `tests/test_austin_abstains_work_order.py` still passes and an Austin facility id returns a probability with an empty work order.

## 11. Name search

1. Add `GET /cities/{city}/restaurants?q=` that returns a short list of name, id, and area for that city only.
2. The page shows those rows. Choosing one loads the lookup from step 6.
3. Match on the city's own name field. Do not search across cities in one query.

Done when two restaurants that share a name in the same city appear as two rows, and a name from another city does not appear.

## 12. Record the results

1. After all seven metrics files exist, add a results table to `README.md` by reading those files. Do not type the numbers in by hand.
2. State the cutoff date and the test window next to each city.
3. Leave a baseline row in every city, including a city where LightGBM loses.

Done when the README table changes when `artifacts/{city}/metrics.json` changes, and a fresh `uv run pytest` is green.
