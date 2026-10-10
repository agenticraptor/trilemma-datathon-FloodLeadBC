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

### D-04.3 — F2–F5: scorecard corrections, README wording, and the final-run reader (Oct 10, 02:45–02:52 UTC)

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

## Work log

- `19:36` — `git checkout main && git pull` → `8c04afb`; branch `stage-04-model`. The Stage 3 part-2 worktree was removed (its branch is merged). Read the prompt and the inputs above.

- `19:38–19:41` — Draft PR #7 opened. F1 (D-04.1, D-04.2): cause found in the archived payload; margin fetch and test; production re-fetch (9 → 13 rows); trust table unchanged; the Jan 1 gap measured.

- `19:45–19:52` — F2–F5 (D-04.3). Production scorecard build 3 and web deployed from PR #7 (`.deployed-commit` `fb4c77d`).

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
