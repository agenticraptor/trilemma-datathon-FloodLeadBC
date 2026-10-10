# Stage 04 — The Nooksack model, tested once on floods it never saw

> Living document. Written while the stage is built, committed with the code. Newest work-log entries at the bottom.

| | |
|---|---|
| Branch | `stage-04-model` |
| Started | 2026-10-09 19:36 PT (2026-10-10 02:36 UTC) |
| Finished | (fill at end) |
| Prompt | `docs/build/prompts/STAGE-04-model.md`; the contract is `docs/evaluation-protocol.md`, the frozen text plus amendments 1–3 (4 added in this stage) |
| Status | checkpoint reached 2026-10-10 09:31 UTC; waiting for the supervisor's go before the final run |

## Goal

Build the hourly Nooksack model the frozen protocol describes:
- North Cedarville level quantiles at 1–48 h;
- P(≥ 148 ft) and P(≥ 150 ft) within 12/24/48 h, read from the window maximum's distribution;
- P(overflow onset at SR 544) within 6/12/24 h, and its time.

Choose everything by walk-forward on development years only. Fix the final models publicly in the ledger before any held-out row is scored. Then run the held-out test once (WY2022, WY2026, the live period) against pure persistence, the 3 h trend, the gauge-watch rule, NWS as issued and the relay tiers, and report it whatever it shows.

The relay (trust table) and the official scorecard already stand on their own; the model has to earn its place on top of them. **A model that loses is a legitimate, publishable result.**

## Inputs read

- **`docs/build/prompts/STAGE-04-model.md`:**
  - fixes F1–F5 (F6 optional);
  - amendment 4 before any fit;
  - development, a checkpoint with a ledger card, the final run after the supervisor's go, R1;
  - VM safety: training containers capped at `--cpus 1.0 --memory 3g`;
  - targets: checkpoint by 15:00Z, PR by 21:00Z.
- **The supervisor's QA finding:** the "low bias for big floods" comes from sorting warnings by outcome. Sorted by forecast, the observed crest = 15.2 + 0.89 × the first forecast (slope 95 % CI 0.35–1.44); the typical miss is 1.19 ft; when the first forecast was ≥ 148 ft, 8 of 10 came in lower. **The honest gap is the missing range, not a bias.** F3 and F4 carry this into the scorecard and the README.
- **`docs/evaluation-protocol.md`:** frozen at `45367d1` (`ecdefe0b…abad`); amendments 1–3, now `c78bed9f…ec7c`. Its main points:
  - development years WY2005–2025 except 2022;
  - the A2 final-run folds;
  - T1–T6;
  - §2.1: 0 development events at ≥ 150 ft, 5 at ≥ 148 ft, 3 overflows;
  - relay v2 is in-sample;
  - R0–R3.
- **`src/floodlead/train_data.py`** (`development_rows`, `walk_forward_folds`, `final_run_folds`), `docs/data/features-nooksack-v1.md`, `trust-v2.json` and `catalogue-v1.json`.
- **`evaluation.md`:** 19 quantiles for new models; the kill criteria (BSS ≥ 0.10 at 12 h; ECE ≤ 0.05; FAR not worse than the advisory).
- **`docs/build/PLAN.md`:**
  - go/no-go: GO, a tiered relay that states its odds; the model is a candidate upgrade to Prepare;
  - cut order: precipitation forecasts are cut first.
- **What to expect, written down now:**
  - the forks lead North Cedarville by only ~4–5 h, so beyond ~6 h skill has to come from rain;
  - as-issued forecast rain exists only from 2024-01-19, so the honest model has no forecast rain in most training years, and NWS (which uses forecast rain) is likely hard to beat at 12–48 h;
  - the held-out years hold the two largest floods on record at North Cedarville, so the final run tests extrapolation.

## Plan

1. Stage doc, then a draft PR.
2. F1–F5, then F6 if time allows:
   - F1: SR 544 re-fetch, Nov 13–15, 2015, with before and after counts; the trust table re-checked;
   - F2: the "after the crest" timing shown as "—";
   - F3: the forecast-conditioned scorecard view (regression, ≥ 148 ft outcomes, the long-lead sentence), reproducing the supervisor's numbers;
   - F4: README wording;
   - F5: `final_training_rows()` with tests.
3. **Amendment 4** (dated, own commit, sha256 here), before any fit:
   - NWS columns are comparators, not inputs;
   - Δ-level and window-maximum targets;
   - 19 quantiles;
   - crossing probabilities from M_H's CDF;
   - the overflow model from P(M_H ≥ L);
   - the families compared, the ablation groups, the re-run rule.
4. **Development:** walk-forward folds only, every fit logging its training years, with ablations, fit times and peak memory. Train in capped one-off containers, and check `/v1/track-record` for gaps after each long job.
5. **Development report:** `docs/data/stage4-development-v1.json`, labelled "development, used to choose the model; not the result".
6. **Checkpoint:**
   - final models per A2 via `final_training_rows()`;
   - `stage4-final-manifest-v1.json`;
   - a ledger `model_card` with the manifest sha256;
   - the 10-line status.
   - **STOP.** While waiting: R1, F6, the doc.
7. **After the go:** one final-run command, one run ID → `stage4-results-v1.json`; the §11 table; T1–T6 met or not met; every held-out event; the kill-criteria decision.
8. README results section, the STAGE REPORT, and PR ready by 21:00Z.

## Decisions

### D-04.1 — F1: re-fetch the SR 544 record start with a request margin (Oct 10, 02:40 UTC)

- **Cause found:** the archived NWIS IV payload of the original backfill (`raw_objects` 1647, `startDT=2015-11-14T08:15Z`) starts at **01:15 PST (09:15Z)**. NWIS answered a winter `…Z` start time one hour late.
  - Today USGS's OGC v0 API holds all 13 records of Nov 14 from 08:15Z, and so does NWIS when asked in PST.
- **Fix:**
  - `fetch_nwis_window(..., request_margin=…)` asks from start − margin and keeps only [start, end);
  - `floodlead backfill usgs-window --site … --start … --end …` is a forced re-fetch with a 1-day margin that ignores recorded chunks;
  - `tests/test_usgs_refetch.py` checks the requested `startDT` and the window filter.
- **Production (02:41Z):** SR 544, [2015-11-13, 2015-11-16) went **9 → 13 rows**. The 4 missing readings (08:15–09:00Z: 3.59, 3.73, 3.80, 3.83 ft) are present now; the payload held 13 rows in the window.
- **Trust table rebuilt** (`/srv/floodlead/datasets/f1/trust.json`) against `trust-v2.json`: **no number changed**. The episodes are identical; the record start is now 08:15Z, and the excluded record-start episode starts 08:15Z.

### D-04.2 — The same NWIS shift left a systematic gap on every Jan 1 (reported; fix deferred)

- Backfill chunks start on Jan 1 and Jul 1 (UTC). The winter ones lost the first hour.
- On the continuous USGS gauges, the Jan 1 readings at 00:00–00:45Z are missing in nearly every year, 2005–2026:
  - North Cedarville 84 of 88;
  - MF, SF, Everson and Ferndale 88 of 88;
  - NF 76 of 88.
  - The Jul 1 boundaries (summer time) are complete.
  - The intermittent overflow gauges report only while water flows, so their absence is expected.
- **Impact:** about 4 readings per site per year (≈ 0.01 % of rows). The frozen datasets (pinned sha256) are **not** rebuilt. A row whose target hour falls in such a gap has an empty target; features use the latest reading within 2 h.
- **Fix later (Stage 5):** a bulk re-fetch with the margin, about 7 continuous sites × 22 years ≈ 154 NWIS requests. The pinned datasets stay as they are.

### D-04.3 — F2–F5: scorecard corrections, README wording, and the final-run reader (Oct 10, 02:38–02:43 UTC)

- **F2.** The "after the crest" bin now carries `crest_time_mae_h = null` and `crest_time_note` ("not a forecast: issued after the observed crest"). The page shows "—" with the note.
- **F3.** `scorecard.forecast_conditioned()`, in `/v1/official-scorecard` (`summary.<point>.forecast_conditioned`), the page ("Sorted by what was forecast") and the README. It uses OLS with a t-based slope interval: a t quantile from the regularised incomplete beta, checked at 2.0555 for 26 df and 2.306 for 8 df.
  - **It reproduces the supervisor's QA numbers exactly:**
    - n = 28 warnings with both crests;
    - observed = 15.15 + 0.895 × the first forecast;
    - slope 95 % CI 0.35–1.44;
    - residual SD 1.19 ft (the supervisor's "typical miss");
    - first forecast ≥ 148 ft: 10 warnings, **8 lower, 2 higher** (2021 +1.86 ft, 2025 +2.04 ft); error mean −0.63 ft, range −3.10 to +2.04 ft.
  - The long-lead sentence sits under the lead table.
  - Production scorecard rebuilt: build 3, which includes the F1 records.
- **F4.** README: "13–19 %" in place of "about 19 %". The "about 2 ft low" sentence now adds that, sorted by forecast, the first crest was higher than the outcome in 8 of 10 moderate-or-worse forecasts.
- **F5.** `train_data.final_training_rows(path, fold)` and `check_final_rows()` allow exactly `final_run_folds()[fold]`. Tests:
  - WY2026 and WY ≥ 2027 are refused in every fold;
  - WY2022 is refused in `heldout_wy2022`, and allowed in `heldout_wy2026` and `live`;
  - a static test allows callers only in `train_data.py` and the final-run module, `model_final.py`.

### D-04.4 — Amendment 4: the Stage 4 design, fixed before any model is fitted (Oct 10, 02:45 UTC)

- **Context:** the prompt requires amendment 4 in its own commit, before any fit. No model code exists yet on this branch.
- **Fixed, in brief:**
  - NWS columns are comparators, never inputs.
  - The targets are level changes at the 8 ledger horizons and window maxima M_12, M_24 and M_48.
  - 19 sorted quantiles.
  - Crossing probabilities come from M_H's CDF (`crps.py` tails). An isotonic map is allowed only if it wins a leave-one-validation-year-out Brier check.
  - Overflow probability is the mean of P(M_H ≥ L_j) over the 3 development onsets, with a ≤ 3-input logistic as the only alternative.
  - Two families, (a) linear quantile regression and (b) LightGBM quantiles, with fixed hyperparameters and an optional quiet-row subsample. The selection criterion is written in advance: pooled validation fair CRPS over 6/12/24 h, Brier as the tie-break.
  - Feature groups G, G+R (primary), G+R+F (scored on WY2024–2025 and WY2026 only) and oracle.
  - (p\*, k) chosen on validation.
  - The re-run rule, the checkpoint and ledger card, and the compute limits.
- **Why:** every choice that could be tuned towards the held-out answer is fixed now, while no model has been fitted.
- **sha256 of the protocol after amendment 4: `fd6ecb6eee0ec0ee2fb3103ce73287b00f159d7634286347acdefffefcb103ab`.**

### D-04.5 — F6: VACUUM (ANALYZE) of the rain tables (Oct 10, 02:44:46–02:45:01 UTC)

- **Ran:** `VACUUM (ANALYZE) rain_hourly` and `VACUUM (ANALYZE) openmeteo_hourly` (never FULL).

| Table | Total size before → after | Dead tuples before → after |
|---|---|---|
| `rain_hourly` | 394,485,760 B → 394,485,760 B | 150,397 → 0 |
| `openmeteo_hourly` | 552,804,352 B → 552,804,352 B | 6,895 → 6,869 |

- Plain VACUUM marks the dead space reusable without returning it to the OS, so the sizes did not change.
- **Deviation:** the prompt said to run it outside HH:10–HH:45. It started at 02:44:46, **14 s inside that window**, because I misread the clock. No production job was running: the 02:40 scorer had finished at 02:40:14, and the next issuance was 03:15. The 03:15 issuance was checked afterwards (work log).

### D-04.6 — Dependencies: LightGBM, scikit-learn and pandas; libgomp1 in the image (Oct 10, 02:46–02:55 UTC)

- **Added** `lightgbm>=4.5` (4.7.0), `scikit-learn>=1.5` (1.9.1) and `pandas>=2.2` (3.0.6) to `pyproject.toml` and `uv.lock`, in the commit that first uses them (`8bee4d4`).
- **LightGBM needs the OpenMP runtime.** The Dockerfile now installs `libgomp1`, and it is also installed on the host for tests.
  - The host install hung on an interactive `needrestart` dialog ("pending kernel upgrade 7.0.0-1013 → 1014"). The dialog was closed; the package was already installed.
  - **The VM was not rebooted** (it is production). A reboot to load the new kernel is the human's call.

### D-04.7 — Compute plan from measured fit times (Oct 10, 03:00–03:16 UTC)

- **Measured** in a capped container (1 CPU, 3 GB), for one target and one fold (WY2005–2020 → 2021), 7 levels:

| Fit | Rows | Time |
|---|---|---|
| LightGBM, quiet-row subsample | 33,605 | 30.8 s |
| LightGBM, all rows | 111,696 | 69.7 s |
| Linear QR, HiGHS dual simplex (sklearn's default) | 30,000 | **571.5 s** |
| Linear QR, HiGHS interior point (`highs-ipm`) | 30,000 | 16.3 s per quantile |

  Peak RSS was 917 MB, mostly the loaded dataset.
- **Choices:**
  1. **Linear QR uses `highs-ipm`.** It solves the same linear program, and keeps the pre-registered 30,000 rows.
  2. **Selection runs only the criterion's targets** (`d_6`, `d_12`, `d_24`, `m_24`; amendment 4, item 6) for every family and subsample candidate. Only the winner is refitted on all 11 targets.
  3. **Ablations (G, oracle) fit the 6 metric targets** (`d_6`, `d_12`, `d_24`, `m_12`, `m_24`, `m_48`). The 1/3/18/36/48 h levels are needed only for issuing, not for T1–T6.
  4. **G+R+F runs only the folds that validate WY2024 and WY2025.** In earlier folds its forecast-rain columns are all empty, so it equals G+R there.
  5. **Two capped containers in parallel**, each `--cpus 1.0 --memory 3g --cpu-shares 128`. The low CPU weight lets the issuer and scorer win any contention. The track record is checked after each hour of training.
- **Why:** with every candidate on every target, the budget would run past the 15:00 checkpoint. None of these choices touches a held-out row, and every candidate is still reported.

### D-04.8 — Development inputs pinned (`docs/data/stage4-inputs-v1.json`, Oct 10, 03:12 UTC)

- **Onset levels L_j:** the replay's North Cedarville level at each development SR 544 onset:
  - 2015-11-18 06:45Z: 147.92 ft;
  - 2017-11-23 19:25Z: 147.60 ft;
  - 2020-02-01 16:55Z: 148.44 ft;
  - median **147.92 ft**.
  - The 2015-11-14 record is the gauge's first record, not an onset it saw begin, so it is excluded, as in the trust table.
- **Validation events:** 3 at ≥ 148 ft (2015-11-18, 2017-11-23, 2020-02-01) and the 3 onsets above. The 2009 and 2010 ≥ 148 ft events lie in training-only years, so they have no out-of-sample prediction and are listed as such.
- **Written down before any result:** the held-out onsets in the replay sit at 146.2–147.6 ft, below every development L_j. The default overflow model will therefore tend to be late or low on held-out data. That is the pre-registered model; it is not tuned.

### D-04.9 — Scoring definitions, fixed before any development result (Oct 10, 03:22 UTC)

- **Outcomes** are the frozen dataset's `y_minor/moderate/major_{H}h` and `y_overflow_{H}h`, not re-derived.
- **Overflow within 6 h** uses the 6-h level quantiles. Amendment 4 has no 6-h window target, and on a rising river the 6-h level is the 6-h maximum. Rows with water already flowing are excluded, because their target is undefined.
- **Alerts (§4, §5):**
  - a hit is an alert issued before the crossing and at most 48 h before it;
  - an alert re-arms only after the probability drops below p\*;
  - (p\*, k) is chosen per §5 on pooled validation predictions; ties go to the lower FAR, then the higher p\*.
- **NWS-derived comparator:** scored on all rows (0 when no warning is in force) and, for T3, on the rows with a North Cedarville warning in force (§10).
- **T6 "met"** uses the point skill (> 0 on both scores), with the year-bootstrap interval shown beside it.
- **Isotonic calibration:** if the leave-one-validation-year-out check on ≥ 148 ft within 24 h lowers the Brier score, isotonic maps are fitted on the pooled validation predictions for the **148 ft** probabilities at 12, 24 and 48 h. Otherwise everything stays raw. The 150-ft probabilities always stay raw: development has 0 events there, so an isotonic map would set them to 0. Overflow probabilities stay raw.

### D-04.10 — R1, the AI-rainfall case study: one event, descriptive (Oct 10, 03:23–03:25 UTC)

- **Run as fixed in amendment 3, with no new API calls.**
  - Forecasts: R0's cached Previous Runs payloads (`/srv/floodlead/datasets/r0/{909,910,1011}.json`, sha256 values in the output).
  - Truth: the SNOTEL hourly totals from `rain_hourly`, exported with constant bounds (Dec 7–13, 2025) to `/srv/floodlead/datasets/r1/snotel_truth.csv`.
  - Command: `python3 scripts/r1_case_study.py /srv/floodlead/datasets/r0 /srv/floodlead/datasets/r1/snotel_truth.csv docs/data/r1-case-study.json`.
- **Windows:** the hours ending 21:00Z Dec 9 … 20:00Z Dec 10 (24 h) and 21:00Z Dec 8 … 20:00Z Dec 10 (48 h), before North Cedarville's minor crossing at 20:15Z. Both sources label an hour by its end.
- **24 h results.** Forecast ÷ SNOTEL gauge total across the three sites; gauge totals were 81.3, 109.2 and 104.1 mm:

| Model | Day-1 lead | Day-2 lead |
|---|---|---|
| ECMWF AIFS (AI) | 0.48–0.70 | 0.45–0.66 |
| ECMWF IFS | 0.49–0.79 | 0.43–0.69 |
| GEM HRDPS | 0.95–1.17 | no values (run too short) |
| NCEP HRRR | 0.99–1.31 | no values (run too short) |
| NCEP NBM | 0.99–1.28 | 0.49–0.59 |

- **Heaviest-6-h timing errors** in the 24 h window: −4 to +7 h.
  - In the 48 h window, some models show errors near 36 h. The window holds two bursts (Dec 8 21Z–Dec 9 08Z and Dec 10), and those forecasts put their heaviest 6 h in the other burst.
- **In plain words:** at the three gauges, the two global 0.25° models (AIFS and IFS) forecast about half to three quarters of the rain that fell in the 24 h before the minor crossing. The kilometre-scale models were close at day 1.
  - **This is one storm at three gauges: no skill or ranking is claimed.** The label is "one event, descriptive".
  - Caveats:
    - SNOTEL gauges under-catch and report in 2.54 mm steps.
    - AIFS is 6-hourly information. The cache shows 6-hour steps, e.g. 1.1 mm/h held for 6 h.
    - Sites 910 and 1011 share an ECMWF cell, so their AIFS and IFS values are identical.
  - Per amendment 3, this changes nothing in the product before Demo Day.

### D-04.11 — What the checkpoint fixes, decided before any development result (Oct 10, 03:29 UTC)

- **Artifacts** (`model_final.plan`), all with the chosen family and subsample setting, and all trained through `final_training_rows()`:
  - **primary G+R:** all 11 targets, for both A2 folds: `heldout_wy2022` (WY2005–2021) and `heldout_wy2026` (WY2005–2025, which includes WY2022). The live period uses the `heldout_wy2026` artifacts, as `final_run_folds()['live']` has the same years;
  - **ablations G and oracle:** the 6 metric targets, for both folds;
  - **ablation G+R+F:** the 6 metric targets, for `heldout_wy2026` only. Forecast rain exists from 2024-01-19, so WY2022 has none.
  - The §11 table has one row per ablation, so the ablations' models must be fixed before the test as well.
- **(p\*, k):** each variant gets its own §5 choice on its pooled validation predictions.
  - G+R+F has no validation event in WY2024–2025 (the 3 ≥ 148 ft events and 3 onsets are in WY2016, 2018 and 2020), so it **uses the primary's rule**, and the manifest says so.
- **Calibration:** per D-04.9. If adopted, it applies to the primary's 148-ft probabilities only, because the maps are fitted on the primary's validation predictions.
- **The manifest** records:
  - the code commit, protocol sha256, dataset and input-file sha256 values;
  - the configuration, features per group, onset levels, (p\*, k) per variant, calibration and every artifact's sha256 and training years.
  - Its sha256 goes into a ledger `model_card` (`floodlead-nooksack-v1`). That card is appended once (`model ledger-card` refuses a second) and anchored at the next HH:30.
- **The final run** (written while waiting for the go, never run before it) refuses to start if any dataset or artifact hash differs from the manifest.

### D-04.12 — The model chosen on validation: LightGBM quantiles on all rows (`lgb_GR_full`) (Oct 10, 05:50 UTC)

- **The rule** (amendment 4, item 6, fixed before any fit): the lowest pooled validation fair CRPS, averaged over 6/12/24 h, among the G+R candidates; within 1 %, the lower Brier for ≥ 148 ft within 24 h.
- **The four candidates.** All fitted on the same 9 walk-forward folds, WY2016–2025 minus 2022; 78,912 validation rows. Output: `/srv/floodlead/models/dev-20261010T0316/selection.json`.

| Candidate | Fair CRPS, 6/12/24 h mean (ft) | Brier, ≥ 148 ft within 24 h |
|---|---|---|
| **`lgb_GR_full`**, LightGBM, all rows | **0.08977** | **0.00088** |
| `lgb_GR_sub`, LightGBM, quiet rows subsampled | 0.09017 | 0.00089 |
| `linear_GR_full`, linear QR, 30k rows | 0.11707 | 0.00096 |
| `linear_GR_sub`, linear QR, 30k rows from the subsample | 0.12780 | 0.00093 |

- **Chosen: `lgb_GR_full`.**
  - It has the lowest CRPS. LightGBM-sub is within 1 % (+0.4 %), so the tie-break applies, and `lgb_GR_full` also has the lower Brier.
  - **The quiet-row subsample is not kept:** it did not win, per amendment 4.
  - The linear family lost by 30–42 % in CRPS. Its 24 h median-MAE skill was near zero: 0.02 (−0.02 to 0.06) for linear-sub.
- **Consequences:**
  - LightGBM-full's remaining targets (started speculatively at 05:03) are now the real completion run.
  - The ablations G, oracle and G+R+F use LightGBM-full; they started at 05:50Z.
  - The final models are trained with LightGBM-full.

### D-04.13 — Development report for the chosen model: development (walk-forward), used to choose the model; not the result (Oct 10, 07:02 UTC)

- **What was scored:** `lgb_GR_full`, all 11 targets, merged from the selection run and the completion run. Pooled over the 9 validation years, 78,912 rows; intervals bootstrapped by water year (1,000) or exact binomial.
- **Output:** `/srv/floodlead/models/dev-20261010T0316/chosen.json`. It goes into `docs/data/stage4-development-v1.json` with the ablations.

| Target | Development value | 95 % interval | Bar | Met on development? |
|---|---|---|---|---|
| T6, level at 6 / 12 / 24 h, all rows: fair CRPSS vs pure persistence | 0.771 / 0.625 / 0.453 | 0.760–0.780 / 0.616–0.635 / 0.443–0.461 | > 0 | yes |
| T6, the same: median-MAE skill | 0.688 / 0.503 / 0.303 | 0.676–0.700 / 0.491–0.515 / 0.291–0.317 | > 0 | yes |
| T6, rising limbs (n ≈ 880): CRPSS / MAE skill at 6, 12, 24 h | 0.75/0.67, 0.58/0.44, 0.56/0.42 | all lower bounds ≥ 0.36 | > 0 | yes |
| T5, P(≥ 148 ft within 12 h): BSS vs persistence | 0.157 | **−0.145 to 0.436** | ≥ 0.10; ECE ≤ 0.05 | **on the point estimate only**; ECE 0.0000–0.0014 for every crossing target |
| T3, ≥ 148 ft within 12 / 24 / 48 h: mean p − observed frequency | −0.0002 / −0.0006 / −0.0013 | upper bound +0.0001 in each | interval not entirely below 0 | yes, narrowly |
| T3, the same: BSS vs NWS-derived on the 181 warning-in-force rows | 0.57 / 0.58 / 0.57 | lower bounds 0.05 / 0.13 / 0.15 | > 0 | yes |
| T3, ≥ 150 ft | — | — | — | **not assessable**: 0 development events |
| T4, overflow onset within 6 / 12 / 24 h: BSS vs persistence (no onset) and vs the trend | 0.31 / 0.40 / 0.23 and 0.70 / 0.61 / 0.41 | vs trend lower bounds 0.41 / 0.32 / 0.20 | > 0 | yes |
| T4, onset timing in the 12 h before the 3 onsets (36 issuances) | median abs error 1.5 h, but only **11 of 36** issuances predicted an onset within 12 h; trend 2.4 h (19 of 36); persistence 1.3 h (6 of 36) | — | smaller than NWS | NWS issues no onset forecast (see the event table) |
| T1, prepare: P(≥ 148 ft within 24 h) ≥ 0.5 for 2 h | 2 alerts; 1 of 3 events caught before the crossing (2020: 3.25 h); FAR 0.5 | POD 0.008–0.906, FAR 0.013–0.987 | FAR ≤ 0.5 and ≥ 24 h before the border | FAR part met. **Timing not assessable** (no verifiable arrival times, §6) |
| T2, move: P(overflow within 12 h) ≥ 0.5, 1 h | 5 alerts; 3 of 3 onsets caught; FAR 0.2; median 4.75 h before onset | POD 0.29–1.00, FAR 0.005–0.716 | POD ≥ 0.8, FAR ≤ 0.2 | POD/FAR part met. Timing not assessable |

- **Calibration:**
  - The leave-one-validation-year-out isotonic check gave a Brier of 0.000966, against 0.000884 raw, so it **lost**. The raw CDF probabilities are used, per D-04.9.
  - Reliability diagrams (10 bins) are in the report file.
- **(p\*, k) chosen per §5:**
  - prepare **(0.5, 2)**: of the rules meeting FAR ≤ 0.5, the longest median warning;
  - move **(0.5, 1)**.
  - Both rest on 3 validation events each, so the intervals are very wide, and are shown.
- **The development events, one by one.** "Relay v1 move" is the North Cedarville minor-stage crossing.

| Event | Model prepare (h before ≥ 148 ft) | Model move (h before onset) | Relay v1 move (h before onset) | Max P(≥ 148 ft within 24 h) in the 48 h before |
|---|---|---|---|---|
| 2015-11-18 | none | 4.75 | 6.00 | 0.59 |
| 2017-11-23 | 17:00Z, 1.25 h **after** the crossing (a false alarm under §4) | 3.42 | 6.42 | 0.34 |
| 2020-02-01 | 3.25 | 6.92 | 5.17 | 0.94 |
| 2009-01-07, 2010-12-12 | training-only years: no out-of-sample prediction | | | |

- **The move tier's one false alarm** (2015-11-13 23:00Z) came 9 h before the 2015-11-14 overflow, whose start the gauge did not record because its record began during it (excluded per D-04.8). It is counted as a false alarm, conservatively.
- **Plain reading:**
  - Level forecasts beat persistence clearly at every horizon.
  - Probabilities are well calibrated on the rare high levels that development has (≤ 148.85 ft).
  - Prepare caught 1 of the 3 validation ≥ 148 ft events in advance.
  - The overflow-onset model is mostly late or silent in the hours before onset (11 of 36 issuances).
  - Development has nothing at ≥ 150 ft. The held-out years hold the two largest floods on record, so the final run tests extrapolation (D-04.8).

### D-04.14 — The checkpoint: final manifest committed before any held-out row is scored (Oct 10, 09:23 UTC)

- **Development report** `docs/data/stage4-development-v1.json`, sha256 `8163205d62305b3c4e76684e1a7a6f6f1a35a89a10178924eebedad0b190c995`.
  - Built by `model dev-score` at `514ec15`. It is labelled "development (walk-forward), used to choose the model; not the result".
  - It holds all 7 candidates and ablations, plus the chosen model scored on the G+R+F rows (WY2024–2025).

| Variant (LightGBM, all rows) | Rows | Fair CRPS, 6/12/24 h mean | CRPSS vs persistence at 6 / 12 / 24 h | T5 BSS at 12 h (95 % interval) | Prepare (p\*, k) | Move (p\*, k) |
|---|---|---|---|---|---|---|
| **G+R (chosen)** | 78,912 | 0.0898 | 0.771 / 0.625 / 0.453 | 0.157 (−0.145 to 0.436) | (0.5, 2) | (0.5, 1) |
| G, gauges only | 78,912 | 0.0948 | 0.752 / 0.594 / 0.432 | 0.187 (−0.066 to 0.408) | (0.6, 2) | (0.3, 2) |
| oracle, future rain known (upper bound) | 78,912 | 0.0610 | 0.786 / 0.721 / 0.670 | 0.246 (−0.036 to 0.610) | (0.5, 2) | (0.5, 2) |
| G+R+F, WY2024–2025 only | 17,544 | 0.0778 | 0.787 / 0.641 / 0.505 | not assessable (0 events) | the primary's | the primary's |
| G+R on the same WY2024–2025 rows | 17,544 | 0.0826 | 0.786 / 0.633 / 0.460 | not assessable | — | — |

- **What the ablations say (development):**
  - Observed rain improves level CRPS by about 5 % over gauges alone.
  - Knowing the future rain (oracle) would cut it by about a third, mostly at 24 h.
  - As-issued forecast rain cut it by about 6 % on WY2024–2025, a period with no ≥ 148 ft event.
- **Manifest** `docs/data/stage4-final-manifest-v1.json`, **sha256 `1127595c5c8b57b19231c9b9b2ba1b71504dd909434f265b49e89c8581f39f4c`**.
  - Built by `model manifest` with the training image (`floodlead-app:s4`, code commit `df5134c`).
  - It records:
    - the protocol sha256 `fd6ecb6e…03ab` (amendments 1–4);
    - the dataset sha256 values (honest `e0d165a9…549d`, oracle `5ffea66a…0054`);
    - the inputs file sha256;
    - the configuration;
    - the features per group;
    - the onset levels;
    - (p\*, k) per variant;
    - calibration: **not used** (D-04.13);
    - all 7 artifacts with sha256 and training years.

### D-04.15 — The model card in the public ledger: seq 32517, anchored 09:30:01Z (Oct 10, 09:23–09:31 UTC)

- **Command:** `floodlead model ledger-card --manifest docs/data/stage4-final-manifest-v1.json`, in a one-off container with image `floodlead-app:s4` (`df5134c`).
- **Entry:**
  - **seq 32517**, `model_card`, model `floodlead-nooksack-v1`;
  - created 2026-10-10T09:23:40.573Z;
  - entry hash `970c70990e803bbe1da87b5b9173135b1bc7d62831fd20ac0b063beba457b927`.
  - `params`: `manifest_sha256` = `1127595c…f39f4c`, `protocol_sha256` = `fd6ecb6e…03ab`, `code_commit_trained` = `df5134c…`, `status` = "fixed before any held-out row is scored; not issued live until Stage 5".
  - `params_hash` `099fe8ef…2534`.
- **Anchor:**
  - 2026-10-10T09:30:01.99Z, ledger-branch commit `fa255a4f3515b53b78bc9fee1a35b2ddb82c98e1`, `ledger/entries/2026/10/10/09.jsonl.gz`. The anchor head was seq 32517.
  - Checked with `git show origin/ledger:…/09.jsonl.gz | zcat`: the entry is present, with the same hash.
- **The checkpoint is complete.** No held-out or live row has been scored by any Stage 4 model.
  - The development code loads development years only (`load_dev`).
  - The final run has not been executed; it needs `--supervisor-go`.
  - Training read held-out years only as A2 allows: WY2022 in the WY2026 models, by design.

## Work log

- `19:36` — `git checkout main && git pull` → `8c04afb`; branch `stage-04-model`. The Stage 3 part-2 worktree was removed (its branch is merged). Read the prompt and the inputs above.

- `19:38–19:41` — Draft PR #7 opened. F1 (D-04.1, D-04.2): cause found in the archived payload; margin fetch and test; production re-fetch (9 → 13 rows); trust table unchanged; the Jan 1 gap measured.

- `19:38–19:43` — F2–F5 (D-04.3). Production scorecard build 3 and web deployed from PR #7 (`.deployed-commit` `fb4c77d`).

- `19:44–19:45` — Amendment 4 committed (`216907f`, 02:44:38Z) before any model code existed. F6 (D-04.5).

- `19:45–20:16` — Dependencies (D-04.6), model core and tests (`8bee4d4`), timing probes (D-04.7), inputs pinned (D-04.8), development fit command and loader tests (`e57eb5d`).
  - `docker run --cpus 1.0 --memory 3g --cpu-shares 128 … floodlead model dev-fit --targets d_6,d_12,d_24,m_24 --candidate lgb:G+R:sub --candidate lgb:G+R:full` and the same with `linear:G+R:sub` and `linear:G+R:full`;
  - launched 03:16:37Z into `/srv/floodlead/models/dev-20261010T0316/`.

- `20:16–20:22` — Scoring module and tests (`3d99776`); D-04.9 written before any development result.

- `20:22–20:25` — R1 (D-04.10) from the R0 cache: 0 API calls, output `docs/data/r1-case-study.json`. Track record at 03:23Z: 32 issuances, 0 gaps; the 03:15 issuance took 101.6 s (written 03:16:42Z).

- `20:25–20:29` — Final-model code: `model_final.py`, the only caller of `final_training_rows()`; artifacts, manifest and ledger card; tests including hash refusal (`b9f8bc9`). D-04.11.

- `20:33–22:03` — Selection fits (D-04.7):
  - **LightGBM-sub** finished 03:49Z;
  - **LightGBM-full** finished 04:59Z;
  - **linear-sub** finished 04:29Z;
  - **linear-full** is running.
  - **The 04:15 issuance under full training load** was written at 04:16:39Z in 98.5 s. Seq 28240; 0 gaps.
  - **Scored** (`model dev-score`, pooled validation over WY2016–2025 minus 2022; fair CRPS averaged over 6/12/24 h, then the Brier for ≥ 148 ft within 24 h):
    - `lgb_GR_full` 0.08977 (0.00088);
    - `lgb_GR_sub` 0.09017 (0.00089);
    - `linear_GR_sub` 0.1278 (0.00093).
  - **05:03Z:** started LightGBM-full's remaining targets (`d_1`, `d_3`, `d_18`, `d_36`, `d_48`, `m_12`, `m_48`) in the free container (`s4-complete`, image `floodlead-app:s4` at `df5134c`). This is **speculative**: the choice is final only once linear-full is scored. If linear-full won, this run would be reported as an extra run, and the winner would be completed instead.

- `22:47–22:50` — linear-full finished at 05:47:56Z and was scored; the choice is LightGBM-full (D-04.12). Ablations started at 05:50Z (`s4-abl`): G+R+F on folds 2024–2025, then G and oracle on all folds, each with 6 metric targets. Track record at 05:33Z: 34 issuances, 0 gaps.

- `23:58–00:02` — The completion run finished at 06:58:49Z. Merged predictions → `chosen/preds-lgb_GR_full.npz` (11 targets). Scored (D-04.13). **Primary final models started at 06:59Z:** `model final-train --family lgb --only GR_heldout_wy2022,GR_heldout_wy2026` → `/srv/floodlead/models/final-20261010T0659/`, image `floodlead-app:s4` (`df5134c`).

- `00:02–00:55` — **Primary final models** (`final-20261010T0659`), through `final_training_rows()`:
  - `GR_heldout_wy2022.pkl`: WY2005–2021 (17 years), 149,016 rows, 1,493 s, 953 MB; sha256 `d3468c05…`.
  - `GR_heldout_wy2026.pkl`: WY2005–2025 (21 years, **including WY2022**), 184,080 rows, 1,751 s, 1,441 MB; sha256 `ab42dbd1…`.
  - Ablation final models started at 07:54:42Z (`s4-final-abl`).
  - Ablation development: G+R+F (2 folds) and G (9 folds) are done; oracle is running.
  - Track record at 07:54Z: 36 issuances, 0 gaps.

- `00:55–02:13` — **All 7 final artifacts** are in `/srv/floodlead/models/final-20261010T0659/`. Each was trained through `final_training_rows()` with image `floodlead-app:s4` (`df5134c`), and each sha256 was re-checked against `artifacts.jsonl`:

| Artifact | Variant | Training WY | Targets | Rows | Fit | Peak RSS | sha256 |
|---|---|---|---|---|---|---|---|
| `GR_heldout_wy2022.pkl` | G+R | 2005–2021 (17 years) | 11 | 149,016 | 1493 s | 953 MB | `d3468c052b8b7fc5…` |
| `GR_heldout_wy2026.pkl` | G+R | 2005–2025 (21 years, incl. 2022) | 11 | 184,080 | 1751 s | 1441 MB | `ab42dbd1d877a8c2…` |
| `G_heldout_wy2022.pkl` | G | 2005–2021 (17 years) | 6 | 149,016 | 758 s | 953 MB | `510e5ddfb5abcc7b…` |
| `oracle_heldout_wy2022.pkl` | oracle | 2005–2021 (17 years) | 6 | 149,016 | 854 s | 1522 MB | `c23b9e17268fe143…` |
| `G_heldout_wy2026.pkl` | G | 2005–2025 (21 years, incl. 2022) | 6 | 184,080 | 692 s | 1522 MB | `846e2986d33f7926…` |
| `oracle_heldout_wy2026.pkl` | oracle | 2005–2025 (21 years, incl. 2022) | 6 | 184,080 | 1088 s | 1762 MB | `b4a4be8bca65c782…` |
| `GRF_heldout_wy2026.pkl` | G+R+F | 2005–2025 (21 years, incl. 2022) | 6 | 184,080 | 962 s | 1762 MB | `fb94ac0d61eac0d2…` |

- `02:13–02:24` — The oracle ablation's development finished at 09:19Z. Full development report built (2 min 38 s, 1 CPU). Manifest built with the training image and copied into `docs/data/`; host paths are recorded.

- `02:23–02:31` — Model card appended (seq 32517) and anchored at 09:30:01Z (D-04.15). Track record at 09:30Z: 38 issuances, 0 gaps. **STOP:** waiting for the supervisor's go. R1 is done (D-04.10) and F6 is done (D-04.5).

## Measurements

| What | Value | How measured | When |
|---|---|---|---|
| SR 544 rows, Nov 13–16, 2015 (F1) | 9 → 13 | `backfill usgs-window` counts | 02:41Z |
| Trust table after F1 | unchanged | rebuilt vs `trust-v2.json` | 02:42Z |
| `rain_hourly` dead tuples (F6) | 150,397 → 0; size 394,485,760 B unchanged | `pg_stat_user_tables`, `pg_total_relation_size` | 02:44–02:45Z |
| One LightGBM fit, 1 target × 7 levels, sub / full | 30.8 s / 69.7 s (33,605 / 111,696 rows) | capped probe | 02:55–03:07Z |
| One linear QR fit, 30k rows, 1 quantile, dual simplex / IPM | 571.5 s for 7 levels / 16.3 s for 1 level | capped probe | 03:07–03:09Z |
| Peak RSS of a fitting container | 917–940 MB | `getrusage` in the fit log | 03:19Z |
| LightGBM-sub fold time, 4 targets, two containers in parallel | 153–201 s | fit log | 03:19–03:29Z |
| Linear-sub fold time, 4 targets | 346–380 s | fit log | 03:22–03:29Z |
| Issuance runtime while training | 101.6 s (03:15, start of training); 98.5 s (04:15, two fitting containers) | ingest log | 03:16Z, 04:16Z |
| LightGBM-full fold time, 4 targets, two containers in parallel | 326–490 s | fit log | 04:01–04:59Z |
| `model dev-score`, 3 candidates (1 CPU) | about 2 min | wall clock | 04:59–05:01Z |
| Final model fit, 11 targets, WY2005–2021 / WY2005–2025 | 1,493 s / 1,751 s; peak 953 / 1,441 MB | artifacts.jsonl | 07:24Z / 07:54Z |
| Final artifact size | about 47 MB per 11-target pickle | `ls -l` | 07:24Z |
| LightGBM-full fold, 7 targets (completion run) | 536–890 s | fit log | 05:12–06:58Z |
| LightGBM-full fold, 6 targets (ablation G) | 324–614 s | fit log | 06:25–07:35Z |

## Acceptance criteria

| AC | Result | Evidence |
|---|---|---|

## Contract files changed

| File | What changed | Why |
|---|---|---|
| `README.md` | "13–19 %" wording; the forecast-conditioned view ("Sorted by what was forecast"); the long-lead sentence; 8 of 10 moderate-or-worse first crests came in lower (D-04.3) | F3, F4: the supervisor's QA finding |
| `docs/evaluation-protocol.md` | Amendment 4 appended; the frozen text and amendments 1–3 unchanged (D-04.4) | Stage 4 design fixed before any fit |
| `Dockerfile`, `pyproject.toml`, `uv.lock` | `libgomp1`; LightGBM, scikit-learn and pandas (D-04.6) | Model training |
| `docs/data/stage4-inputs-v1.json` (new) | Validation events and onset levels from frozen sources (D-04.8) | Inputs pinned before any fit |
| `docs/data/r1-case-study.json` (new) | R1 output (D-04.10) | Amendment 3 |

## Open issues and handoff to next stage

- (filled at the end)
