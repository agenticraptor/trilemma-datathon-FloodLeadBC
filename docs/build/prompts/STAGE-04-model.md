# Stage 4 prompt: the model, tested once on floods it never saw

| PR | Branch | Title | Target |
|---|---|---|---|
| 1 | `stage-04-model` | `Stage 04: the model, tested once` | Checkpoint (item 5) by **Oct 10, 15:00 UTC**; PR ready by **Oct 10, 21:00 UTC** |

## Stage 3 part 2 QA (supervisor, Oct 10 ~02:45 UTC): PASS, PR #6 merged as `0dab2d1`

**Verified independently:**
- **Protocol.** The frozen protocol is unchanged (`ecdefe0b…abad`). The three amendments only append, and their hashes match your report.
- **Trust table.** It equals the supervisor's own count, alert by alert, for every tier.
- **Archive test.** It holds all 18 warning events and whole calendar years.
- **Loader.** The Stage 4 loader rejects held-out and live years.
- **Leakage.** The leakage design and its poisoning test were read line by line.
- **Official scorecard.** Spot-checked against the archive: 2021 forecast 148.9 ft against 150.76 ft observed; 2025 forecast 148.4 ft against 150.44 ft; "major" issued 7.7 h and 0.8 h after the overflow began.
- **AIFS rainfall.** The supervisor's own request confirmed that AIFS day-1 and day-2 values exist for Dec 2025: 144 of 144 hours at Wells Creek.
- **Scorecard page.** 1280 and 375 px, two locales, 0 console errors, no sideways scroll.
- **Tests.** `ruff` clean; `pytest` 154 passed with the DB tests.

**A finding from the QA that changes how we talk about NWS.** The scorecard's "low bias for big floods" comes from sorting warnings by how big the flood turned out. Any forecast looks low for the biggest outcomes when sorted that way. Sorted by what was forecast, across the 28 North Cedarville warnings that have both crests:
- the observed crest = 15.2 + 0.89 × the first forecast, with a 95% interval on the slope of 0.35–1.44;
- the typical miss is 1.19 ft either way;
- when the first forecast was ≥ 148 ft (10 warnings), the river came in **lower 8 times**, and about 2 ft higher twice (2021 and 2025).

So the honest gap is **the missing range**, not a bias to correct. The supervisor has corrected `brief.md` and the status-quo review. Fixes F3 and F4 below carry the correction into the scorecard and the README.

**Fixes carried into this stage** (do them first; each is small):
- **F1. SR 544 record start.** Re-fetch Nov 13–15, 2015 for USGS 12211195. The backfill lacks the 4 records from 08:15 to 09:00Z on Nov 14. Record the before and after counts. No trust-table number should change; if one does, report it.
- **F2. Scorecard "after the crest" bin.** Its crest-timing value (288 h) is meaningless. Show "—" with a one-line note, in both the API and the app.
- **F3. Scorecard, the forecast-conditioned view.** Add it to `/v1/official-scorecard`, the page and the README table, computed by code (your numbers must reproduce the supervisor's or explain the difference):
  - the regression of the observed crest on the first forecast: slope, 95% interval, residual SD, n;
  - what happened when the first forecast was ≥ 148 ft: n, how many came in lower, how many higher, the mean and range of the error;
  - one sentence under the lead table: "Warnings issued 24–48 h before the crest exist mainly for the largest floods, so this bin's low bias partly reflects which floods had long warnings."
- **F4. README wording.**
  - The old quantile score was "13–19 %" low, not "about 19 %".
  - Wherever the README says the first crests were "about 2 ft low", add that, sorted by what was forecast, the first crest was higher than the outcome in 8 of 10 moderate-or-worse forecasts.
- **F5. Final-run reader.** `train_data.development_rows()` rightly refuses WY2022, but amendment 1 (A2) trains the WY2026 and live model on WY2005–WY2025, which includes WY2022.
  - Add `final_training_rows(path, fold)`, which allows exactly `final_run_folds()[fold]` and nothing else.
  - Test it: it refuses WY2026 and WY ≥ 2027 in every fold, and WY2022 in the `heldout_wy2022` fold.
  - Only the final-run command may call it.
- **F6 (optional). Housekeeping.** `VACUUM (ANALYZE)` the rain tables (never `FULL`), outside HH:10–HH:45. Record the sizes before and after.

## Mission

Build the Nooksack hourly model that the frozen protocol describes (`docs/evaluation-protocol.md` with amendments 1–3).
- Choose everything on development years only, by walk-forward.
- Commit the final models publicly **before** any held-out row is scored.
- Then run the held-out test **once**, and report what it shows. That includes the case where the model loses to the relay, to persistence or to NWS.

The relay (trust table) and the official scorecard already stand on their own. The model has to earn its place on top of them.

## Read first

1. `docs/evaluation-protocol.md`, the frozen text and amendments 1–3. **It is the contract.** Where this prompt and the protocol disagree, the protocol wins. Tell the supervisor.
2. `docs/data/features-nooksack-v1.md`, `src/floodlead/train_data.py`, `docs/data/trust-v2.json`, `docs/data/catalogue-v1.json`.
3. `evaluation.md`: 19 quantiles for new models, and the kill criteria.
4. `docs/build/PLAN.md`: the "Go/no-go" section and the cut order.

## What to expect (write it down now, so nobody is surprised later)

- The Nooksack forks lead North Cedarville by only about 4–5 h (your upstream analysis). Beyond about 6 h, skill has to come from rain.
- As-issued forecast rain exists only from 2024-01-19. So the main honest model has **no forecast rain in most training years**. NWS forecasts use forecast rain, so expect NWS to be hard to beat at 12–48 h.
- Development years hold 5 events at ≥ 148 ft, 3 overflows and **0** at ≥ 150 ft. The held-out years hold the two largest floods on record at North Cedarville, so the final run tests extrapolation.
- A model that loses is a legitimate, publishable result. Say so in the plan.

## Production safety for training (the VM is production)

The e2-standard-2 VM (2 vCPU, 8 GB) also runs the database, ingest, the hourly issuer and the API.
- **Containers.** Train only in one-off containers capped at `--cpus 1.0 --memory 3g` (or the compose equivalent). Read the datasets read-only from `/srv/floodlead/datasets`. Write models to a new directory, `/srv/floodlead/models/<run_id>/`. Never overwrite.
- **After every long job**, check `/v1/track-record`: 0 gaps, and the issuance runtimes in the issuer log. If an hourly issuance is missed or delayed past HH:30, stop training, record it and fix the limits before going on.
- **Dependencies** (for example `lightgbm`, `scikit-learn`) go into `pyproject.toml` and `uv.lock`, in the same commit as their first use.

## Order of work

### 1. Branch and stage doc

`stage-04-model` from main (`0dab2d1` or later). The stage doc comes first, then F1–F5.

### 2. Amendment 4: design choices fixed before any training

This is a dated amendment to the protocol, in its own commit, with its sha256 in the stage doc, made before any model is fitted. It fixes:

- **NWS inputs.** NWS-derived columns (`nws_*`) are comparators, **not inputs to the primary model**. That keeps "model vs NWS" a fair comparison. A post-processing variant "plus NWS products" may be added as one extra ablation, labelled as such.
- **Targets.**
  - North Cedarville level at the ledger horizons (1, 3, 6, 12, 18, 24, 36, 48 h), modelled as the change from the latest reading (`y_lvl_h − nc_lvl`).
  - The **window maximum** M_H = max of `y_lvl_h1…h_H` for H ∈ {12, 24, 48}, modelled the same way (`M_H − nc_lvl`).
  - Both are derived from the frozen files' columns; nothing is rebuilt.
- **Quantiles.** 19 levels, 0.05…0.95, sorted to prevent crossing.
- **Crossing probabilities.** P(≥ 148 ft) and P(≥ 150 ft) within H are read from the predictive CDF of M_H: piecewise linear, with the exponential tails of `crps.py`. Never from a classifier trained on 150 ft labels (protocol §2.1). Any calibration map is fitted on pooled walk-forward validation predictions only.
- **Overflow onset (the model's move tier).** With 3 development overflows, no high-capacity classifier is allowed.
  - **Default:** P(onset within H) = P(M_H ≥ L). L is the North Cedarville level at onset, with its distribution taken from development episodes only.
  - **Alternative:** a logistic model with at most 3 inputs, chosen on validation.
  - The onset time is when the predicted median path first reaches the median L.
- **Model families compared on validation** (pick one, and log why):
  - **(a)** linear quantile regression on a small feature set;
  - **(b)** gradient boosting (for example LightGBM) for the median, plus residual quantiles conditioned on the predicted change and the recent rise, or quantile objectives at 7 levels interpolated to 19.
  - Down-weighting or subsampling quiet rows is allowed if it is chosen on validation.
- **Feature groups for the ablations (§7):**
  - gauges only;
  - plus observed rain (SNOTEL; KBLI with its live caveat);
  - plus as-issued forecast rain (WY2024–2025 validation and the held-out WY2026 only; say so with every number);
  - oracle (labelled as an upper bound).
- **Re-runs.** The final run happens once. A re-run needs a further dated amendment saying why, and **both** results are reported.
- **Checkpoint and ledger commitment** (item 5) before the final run.

### 3. Development (walk-forward on validation years only)

- **Folds.** Use `train_data.walk_forward_folds()`. Every fit and calibration step logs its training water years. A test asserts that no held-out or live year appears.
- **Fit**, on the folds:
  - the level and window-maximum models;
  - the crossing probabilities;
  - the overflow model;
  - the (p\*, k) alert rules for the prepare tier (148 ft within 24 h) and the move tier (overflow within 12 h), per §5.
- **Run the ablations.**
- **Measure fit times and peak memory.**

### 4. Development report

This is in the stage doc and in `docs/data/stage4-development-v1.json`, labelled "development (walk-forward), used to choose the model; not the result". It holds:
- T1–T6 on the validation years, with the protocol's intervals;
- reliability diagrams;
- per-event tables for every development event at ≥ 148 ft and every development overflow;
- every candidate tried, including the ones that lost.

### 5. Checkpoint (STOP before the final run)

1. **Train the final models** per amendment 1 (A2), with `final_training_rows()`:
   - WY2022 is scored by a model trained on WY2005–2021;
   - WY2026 and the live period are scored by a model trained on WY2005–2025.
2. **Commit `docs/data/stage4-final-manifest-v1.json`.** It holds:
   - the code commit;
   - the dataset sha256 values;
   - the chosen configuration and features;
   - (p\*, k);
   - the calibration maps;
   - each model artifact's sha256 and its training years.
3. **Record the manifest in the ledger** as a new `model_card` entry (for example `floodlead-nooksack-v1`) with the manifest's sha256. Record the ledger seq and the anchor time in the stage doc. This is the public proof that the model was fixed before the test.
4. **Send the human a 10-line checkpoint status for the supervisor:**
   - the development T1–T6 table;
   - the chosen model;
   - (p\*, k);
   - the manifest and ledger seq.
5. **While you wait for the supervisor's "go":** do R1 (item 7), F6 and the stage doc. **Do not score any held-out row before the go.**

### 6. The final run (after the go)

- **One command, one run ID.** It writes `docs/data/stage4-results-v1.json` and refuses to run if the manifest's hashes do not match the artifacts.
- **It scores:**
  - WY2022;
  - WY2026;
  - the live period to date (WY2027), on the same rows and events as every comparator: pure persistence, the 3 h trend, the gauge-watch rule, NWS as issued, relay v1 and relay v2.
- **It reports:**
  - the protocol's §11 table;
  - T1–T6, each **met / not met** with its interval;
  - every held-out event listed: the Nov 14 2021, Nov 28 2021, Dec 10 2025 and Mar 20 2026 overflows, and every held-out minor event. For each, the times of the model's first prepare and move alerts, against relay v2, NWS's first warning and "major", the City's first alert and order (2021 and 2025 only), the overflow onset and the crest.
- **The kill-criteria decision (§9), written down:**
  - what ships in Stage 5: probabilities, levels only, or "gauge watch and relay" only;
  - why.

### 7. R1: the AI-rainfall case study (amendment 3)

- Run it as fixed in the amendment.
- Label it "one event, descriptive".
- It may run while you wait at the checkpoint.

### 8. Optional, if on schedule

- **R2**, the sensitivity study (amendment 3).
- **The Fraser Valley daily model.** This is cut first.

### 9. Results into the contracts

- **README:** a "Results (Stage 4)" section with the run ID and the §11 table, "what this does and does not show", and a link to the results file.
- **Nowhere else.** No performance claim goes in the README, the app or the brief unless it comes from the results file with its run ID.

## Tests

- **Loader:** no held-out or live rows in any development fit; `final_training_rows()` allows exactly the A2 folds.
- **Quantiles:** monotone; 19 levels; CRPS of the stored quantiles equals `crps.fair`.
- **Calibration:** fitted only on validation predictions. The test fails if a held-out row reaches it.
- **Manifest:** the final-run command refuses when an artifact hash differs from the manifest.
- **Crossing probabilities:** P(≥ X) read from M_H's CDF is monotone in X, and matches a brute-force check on a synthetic case.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| AC-1 | F1–F5 done (F6 optional) | diffs, counts, test output |
| AC-2 | Amendment 4 committed before any fit (commit order) | `git log` of the protocol and of the training code |
| AC-3 | Walk-forward development report: T1–T6 on validation years, with intervals, ablations and every candidate | `stage4-development-v1.json`, stage doc |
| AC-4 | Final models trained per A2; manifest committed; ledger model card recorded **before** the first held-out score | manifest commit, ledger seq and anchor, results file timestamps |
| AC-5 | One final run: §11 table, T1–T6 met / not met, every held-out event listed, the kill-criteria decision | `stage4-results-v1.json`, run ID |
| AC-6 | R1 case study reported as one event, descriptive (or a stated reason it was cut) | file and stage doc |
| AC-7 | Production unharmed: 0 missed issuances during training; resource caps stated | `/v1/track-record` gaps; issuer runtimes |
| AC-8 | README results section with the run ID; no claims elsewhere | link |
| AC-9 | `ruff` and `pytest` pass, with the DB tests run | output |
| AC-10 | ≥ 10 decisions; stage doc in most commits, spread across the stage; contract files updated | `git log --stat` |

## What the supervisor will check

- **Order of events:** the ledger card's seq and anchor come before the results file's first commit, and the artifact hashes match the manifest.
- **Training years:** in the logs, every fit's training years; no held-out year outside A2.
- **Scores:** a sample of held-out scores recomputed from the results file and the frozen datasets' rows.
- **Events:** the per-event times against the catalogue and the trust table.
- **Wording:** "development" and "result" are never mixed; oracle numbers are always labelled.

## Out of scope

- Live issuance of the model into the ledger (Stage 5).
- Alerts (Stage 7).
- New app pages beyond what F2–F3 need.

## When done

Push, then open the PR with the STAGE REPORT as its body. Do not merge. Print the STAGE REPORT as your final message.
