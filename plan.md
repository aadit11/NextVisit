# Nextvisit development plan

Build one city until a diner can open a restaurant and judge its hygiene, then repeat the adapter for the other cities. Do not train a shared model. Do not invent a visit, a grade, or a code when the file does not have it. Do not show a closing list or a percentage on the diner page.

The last inspection stays the health department's record. Around it, the page shows how old that inspection is, whether recent visits are getting cleaner or worse, what kind of problem the codes describe, and how this place compares with the same cuisine in the same area. Two model outputs sit under that: a short hygiene brief that may use only those facts, and a sentence from the city's existing model about whether the next inspection is likely to find a serious problem again.

What already exists: the city registry, the leakage check, the time split, the repeat-last-visit baseline, the work-order faithfulness check, empty data folders, and an API that lists cities and returns 501 for a restaurant.

## 1. Environment

1. Install Python 3.12 and `uv`.
2. From the `NextVisit` repo root, run `uv sync`.
3. Run `uv run pytest`. The current tests must pass before new work: city registry, leakage, time split, baseline, faithfulness, and Austin's empty work order.
4. Copy `.env.example` to `.env`. Leave the brief keys empty until step 7.

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
2. Create an example only when a cycle inspection has a later cycle inspection. The later visit is the target. The label is that visit's positive flag: a critical violation on the next cycle inspection.
3. Features may use cuisine, borough, days since the previous cycle inspection, prior violation counts and recency, whether prior visits were positive, and the previous visit's score and grade.
4. Call `assert_features_before_target` while building features. The target visit's score, grade, and violation codes stay out.
5. Restaurants with no earlier cycle inspection are not examples. Lookups for them have no decision sentence.
6. After the example table exists, choose one cutoff date and save it in `artifacts/new_york/cutoff.json`. `assign_split` sends target dates on or before that cutoff to train and later dates to test.
7. Write `data/processed/new_york/examples.parquet`.

Done when `tests/test_leakage.py` fails a same-day feature and `tests/test_split.py` matches the cutoff file.

## 5. Train and score New York

1. Fit three models on the training period only: `repeat_last_visit`, logistic regression, and LightGBM. `repeat_last_visit` predicts the previous visit's outcome.
2. Calibrate LightGBM with `CalibratedClassifierCV` on training-period data only.
3. Score the test period with precision-recall AUC, Brier score, and the share of true positive visits captured in the top 10% of predicted risk.
4. Write all three models' metrics to `artifacts/new_york/metrics.json`. Write the calibrated LightGBM model to `artifacts/new_york/model.joblib`.
5. If LightGBM does not beat the baseline on precision-recall AUC, keep the baseline numbers in the file.
6. The diner page never shows the probability. It shows one sentence: the next inspection is likely to find a serious problem again, or it is likely to come back clean. The sentence is omitted when the lookup abstains.

Done when `uv run python scripts/train.py --city new_york` finishes without a hand-typed metric, and both artifact files exist and are gitignored.

## 6. New York lookup

1. Replace the 501 response in `src/nextvisit/api/main.py` for a New York id that has history.
2. `GET /cities/new_york/restaurants/{camis}` returns the name, cuisine, and the last inspection from the file: date, grade, score, and violation codes. It also returns the inspection age, the trend of recent visits (`cleaner`, `steady`, or `worse`), the problem kind for those codes, the peer comparison, the decision sentence, and `abstained: false`.
3. The problem kind is one of `illness`, `room`, or `paperwork`. Illness covers pests, food temperature, handwashing, and contaminated food. Room covers plumbing, restrooms, and garbage. Everything else on the record is paperwork, including equipment the diner does not see. A kind is returned only when a code on the record falls in it.
4. The peer comparison counts restaurants of the same cuisine in the same area and says whether this last grade is better than most, typical, or worse than most. It is a count, not a model.
5. A CAMIS with no prior cycle inspection returns `abstained: true` and no decision sentence. The last inspection is still returned when the file has one.
6. An unknown CAMIS returns 404.
7. The response does not include a probability and does not include a work order.

Done when a real CAMIS returns the age, trend, problem kind, peer line, and decision sentence from the file and the model, and a `1900-01-01` permit abstains with no decision sentence.

## 7. Hygiene brief

1. Implement one hosted call in `src/nextvisit/brief/generate.py`. The diner page does not show a closing work order.
2. Send only facts already computed for this restaurant: the inspection date, grade, score, trend, problem kinds, peer comparison, and the official code text on the record.
3. Require a short brief of a few sentences. A date, grade, score, trend, kind, or code in the brief must appear in those facts.
4. Run that check before the API returns the brief. On failure, return an empty brief and a reason, not a rewritten paragraph.
5. Read `BRIEF_API_KEY`, `BRIEF_BASE_URL`, and `BRIEF_MODEL` from the environment. `pytest` and training must still pass with those unset.

Done when a brief that mentions a pest problem the record does not contain is rejected, and one live New York lookup shows a brief that a diner can read.

## 8. Web page for New York

1. In `web/`, run `npm install` and `npm run dev`.
2. Load cities from `GET /cities`.
3. On submit, call `GET /cities/{city}/restaurants/{id}` and render the last inspection, its age, the trend, the problem kind, the peer comparison, the hygiene brief, and the decision sentence. Do not render a percentage or a closing list.
4. Render abstain as a finished state: the name, the last inspection when the file has one, and no decision sentence.
5. Keep the violation codes on the card, with the plain reading of each code, under the brief.

Done when a New York CAMIS typed into the page matches the API JSON.

## 9. Repeat the adapter, one city at a time

Finish the same download, collapse, example, train, and diner lookup for each city before starting the next. Keep a separate cutoff, metrics file, and `model.joblib`. The decision sentence uses that city's own meaning of a serious problem. The page still does not show the probability.

Do them in this order:

1. **Chicago.** One row per inspection in the source, violations packed in text. A serious problem in the sentence is a Fail. Parse violation numbers and comments into the codebook.
2. **King County.** One row per violation, 2021 onward. A serious problem is a violation the county marks as serious.
3. **Los Angeles County.** Join the inspections file and the violations file on the inspection id. Leave out Pasadena, Long Beach, and Vernon. A serious problem is a serious points violation, using the county's own point rule from the file.
4. **Boston.** A serious problem is a fail. Violation description and level come from the inspection rows.
5. **San Francisco.** A serious problem is a Conditional Pass or a Closure. The brief may quote official wording only when the row includes it.

Done when each city has its own metrics file, a held-out test split, and one real id whose page shows the age, trend, peer line, brief, and decision sentence. `scripts/download.py --city all` and `scripts/train.py --city all` complete.

## 10. Austin

1. Download the scores file. The restaurant id is `facility_id`. Keep routine inspections.
2. A serious problem in the decision sentence is a next routine score below 90. The page shows the sentence, not the probability.
3. The brief uses the last score, how old it is, and whether recent scores are falling. It does not mention violation codes.
4. The card follows the score and does not list violation codes.

Done when an Austin facility id shows the score, its age, the score trend, and a decision sentence with no codes.

## 11. Name search

1. Add `GET /cities/{city}/restaurants?q=` that returns a short list of name, id, and area for that city only.
2. The page shows those rows. Choosing one loads the lookup from step 6.
3. Match on the city's own name field. Do not search across cities in one query.

Done when two restaurants that share a name in the same city appear as two rows, and a name from another city does not appear.

## 12. Record the results

1. Keep the results table in `README.md` as the score of the model behind the decision sentence. Read it from `artifacts/{city}/metrics.json`. The columns stay precision-recall AUC, Brier, and top-decile capture. Do not type the numbers in by hand. The diner page does not print this table.
2. State the cutoff date and the test window next to each city.
3. Leave a baseline row in every city, including a city where LightGBM loses.

Done when the README table changes when `artifacts/{city}/metrics.json` changes, and a fresh `uv run pytest` is green.
