# Stage 04 — The Nooksack model, tested once on floods it never saw

> Living document. Written while the stage is built, committed with the code. Newest work-log entries at the bottom.

| | |
|---|---|
| Branch | `stage-04-model` |
| Started | 2026-10-09 19:36 PT (2026-10-10 02:36 UTC) |
| Finished | (fill at end) |
| Prompt | `docs/build/prompts/STAGE-04-model.md`; the contract is `docs/evaluation-protocol.md`, the frozen text plus amendments 1–3 (4 added in this stage) |
| Status | in progress |

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

### D-04.9 — Scoring definitions, fixed before any development result (Oct 10, 03:25 UTC)

- **Outcomes** are the frozen dataset's `y_minor/moderate/major_{H}h` and `y_overflow_{H}h`, not re-derived.
- **Overflow within 6 h** uses the 6-h level quantiles. Amendment 4 has no 6-h window target, and on a rising river the 6-h level is the 6-h maximum. Rows with water already flowing are excluded, because their target is undefined.
- **Alerts (§4, §5):**
  - a hit is an alert issued before the crossing and at most 48 h before it;
  - an alert re-arms only after the probability drops below p\*;
  - (p\*, k) is chosen per §5 on pooled validation predictions; ties go to the lower FAR, then the higher p\*.
- **NWS-derived comparator:** scored on all rows (0 when no warning is in force) and, for T3, on the rows with a North Cedarville warning in force (§10).
- **T6 "met"** uses the point skill (> 0 on both scores), with the year-bootstrap interval shown beside it.
- **Isotonic calibration:** if the leave-one-validation-year-out check on ≥ 148 ft within 24 h lowers the Brier score, isotonic maps are fitted on the pooled validation predictions for the **148 ft** probabilities at 12, 24 and 48 h. Otherwise everything stays raw. The 150-ft probabilities always stay raw: development has 0 events there, so an isotonic map would set them to 0. Overflow probabilities stay raw.

## Work log

- `19:36` — `git checkout main && git pull` → `8c04afb`; branch `stage-04-model`. The Stage 3 part-2 worktree was removed (its branch is merged). Read the prompt and the inputs above.

- `19:38–19:41` — Draft PR #7 opened. F1 (D-04.1, D-04.2): cause found in the archived payload; margin fetch and test; production re-fetch (9 → 13 rows); trust table unchanged; the Jan 1 gap measured.

- `19:38–19:43` — F2–F5 (D-04.3). Production scorecard build 3 and web deployed from PR #7 (`.deployed-commit` `fb4c77d`).

- `19:44–19:45` — Amendment 4 committed (`216907f`, 02:44:38Z) before any model code existed. F6 (D-04.5).

- `19:45–20:16` — Dependencies (D-04.6), model core and tests (`8bee4d4`), timing probes (D-04.7), inputs pinned (D-04.8), development fit command and loader tests (`e57eb5d`).
  - `docker run --cpus 1.0 --memory 3g --cpu-shares 128 … floodlead model dev-fit --targets d_6,d_12,d_24,m_24 --candidate lgb:G+R:sub --candidate lgb:G+R:full` and the same with `linear:G+R:sub` and `linear:G+R:full`;
  - launched 03:16:37Z into `/srv/floodlead/models/dev-20261010T0316/`.

- `20:16–20:25` — Scoring module and tests (`3d99776`); D-04.9 written before any development result.

## Measurements

| What | Value | How measured | When |
|---|---|---|---|

## Acceptance criteria

| AC | Result | Evidence |
|---|---|---|

## Contract files changed

| File | What changed | Why |
|---|---|---|

## Open issues and handoff to next stage

- (filled at the end)
