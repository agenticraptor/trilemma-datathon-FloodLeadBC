# Evaluation — FloodLead BC

No performance number in this repo is claimed in advance. Every number comes from the experiments below, and the live ledger lets anyone recompute them.

## Questions we must answer

1. Does the model give more hours of warning than the official advisory, at a similar or lower false-alarm rate?
2. Are its probabilities honest (calibrated)?
3. Does it beat "what people do today" (looking at the gauge chart and extrapolating)?

## Offline: walk-forward backtest

| Item | Design |
|---|---|
| Split | Expanding window by water year: train ≤ Y, test Y+1, rolling 2005 → 2025 |
| Holdout | November 2021 atmospheric river (Sumas, Vedder, Chilliwack, Coquihalla) untouched until the final run |
| Grouping | Extra basin-grouped split to test transfer to gauges not seen in training |
| Leakage controls | Precipitation features use forecasts as issued; where unavailable for old years, the "oracle-weather" variant is reported separately. Observations lagged by real publication latency. No revised values as features. |
| Thresholds | Generic 2-year return-period level per station, plus user-style levels |

## Online: live public ledger (running since 2026-10-08 20:00Z)

Spec: [`docs/ledger-spec.md`](docs/ledger-spec.md). Decisions: `docs/stages/STAGE-02-ledger-app.md` (D-02.7 to D-02.14).

- **Cadence.** Every hour, for every gauge with a non-sentinel level observation newer than 3 h (≈ 426 of ~440): `base_time` = top of the UTC hour, run at HH:15.
  - Horizons are 1, 3, 6, 12, 18, 24, 36 and 48 h (`valid_at = base_time + h`); a horizon with `valid_at − created_at` < 30 min is dropped.
  - A run more than 30 min late writes a `gap` entry instead. Forecasts are never backdated and gaps are never filled.
- **Leakage.** Only observations with `ts ≤ created_at` and `first_seen_at ≤ created_at` are used. Each forecast records `input_hash` and its error library's hash.
- **Stale inputs.** A forecast is flagged `stale_inputs` when `created_at − data_as_of` exceeds the source's green lag threshold: 150 min for ECCC, 120 min for USGS. This replaces the earlier "> 30 min" rule, which assumed a much faster feed than ECCC's measured 40–90 min. Stale forecasts are issued and recorded, but left out of the default score summary and suppressed from alerts.
- **Ledger.** One global append-only chain, `entry_hash = sha256(prev_hash + "\n" + canonical)`. It is enforced by database triggers on insert and rejects UPDATE, DELETE and TRUNCATE.
  - This is tamper-evident, not tamper-proof: a superuser can disable triggers.
  - Each hour the anchor job commits that hour's entries (`ledger/entries/YYYY/MM/DD/HH.jsonl.gz`) and a `heads.txt` line to the `ledger` branch of this repository. The track record therefore survives the VM.
  - `scripts/verify_ledger.py --source github` verifies the chain from those files alone.
- **NOAA official forecasts** go into the same chain unmodified (`official_forecast` entries, one per fetch that brought new points).

## Baselines (same scoring code)

Both live baselines use the same uncertainty method: point path + the same model's empirical error paths from the station's own history, sampled across past origins and indexed by lead from `data_as_of`. The libraries are:
- ECCC: the trailing 30 days;
- USGS: the trailing 30 days plus the same season (± 30 days) in every prior year.

1. **`persistence-naive`** (pure persistence, the **headline baseline** for skill and for Demo Day): the level at `data_as_of` as a point forecast at every horizon, so its CRPS is the absolute error. The scorer computes it from the `persistence-v1` entries, where the value is already fixed; no extra ledger entries are needed.
2. **`persistence-v1`** — **not** "the level stays the same". It is the current level **plus the station's typical historical change over that lead**, from empirical error paths, so its median can drift (08MH001 at 20:00Z: 1.515 m at `data_as_of`, q50 1.5135 m at 1 h). Its model card was corrected on Oct 8 (same parameters).
3. **`trend3h-v1`** — what a person watching the chart does: least-squares slope over the 3 h ending at `data_as_of` (≥ 50 % of the window's points required), applied for at most **6 h** and then held. The 6 h cap stops the 48 h trend from becoming a strawman.
4. **NOAA NWS official forecast** (NRKW1, NKSW1), compared on matched pairs (below).
5. RFC advisory level mapped to a probability *(planned)*.
6. RFC CLEVER / COFFEE where published *(planned)*.
7. Google Flood Hub where it covers the gauge *(planned)*.

## Live scoring rules (`src/floodlead/scorer.py`, hourly at HH:40)

- **Settling:** a horizon is scored once `valid_at` is ≥ 3 h old.
- **Level truth:** the observation at `valid_at`, else the nearest within ±10 min, else `no_truth` (counted, never imputed).
- **Event truth:** max over `(data_as_of, valid_at]`, the same window as `qmax` and `p_exceed`. It includes the feed-latency gap the forecaster could not see. Fewer than 80 % of the window's points → `insufficient_truth`.
- **Rescoring:** scores are rewritten when a truth observation is revised.
- **CRPS (fair, from Stage 3; D-03.4):** each forecast's CDF is rebuilt from its stored quantiles and the CRPS is integrated exactly (`src/floodlead/crps.py`).
  - Between quantiles the CDF is linear. Beyond the 0.05 and 0.95 quantiles it has exponential tails with the density of the edge segment.
  - For a point forecast, such as `persistence-naive`, it is exactly the absolute error.
  - Measured bias against the exact CRPS of the underlying distribution, with 7 levels (`tests/test_crps.py`): calibrated normal +0.0 %, log-normal +0.0 %, under-dispersed −0.2 %, over-dispersed +1.2 %. With 19 levels it is within ±0.1 %.
  - **Correction (Oct 9).** Until Stage 3 the CRPS was approximated by the quantile score (2 × mean pinball loss over the 7 levels). This file said it "ranks models". That was wrong whenever a spread forecast is compared with a point forecast:
    - the quantile score is exact for a point forecast, but 13–19 % below the CRPS of a spread forecast;
    - so every CRPSS of `persistence-v1` or `trend3h-v1` against `persistence-naive` was inflated.
    - The quantile score is kept only as a secondary column (`crps_qs`). All stored scores were recomputed (scorer run in the stage doc).
- **Future models store 19 quantiles** (0.05 … 0.95 in steps of 0.05), so the rebuilt CDF is tight. The existing `persistence-v1` and `trend3h-v1` keep their 7 levels; their cards are not changed.
- **Skill:** on **paired samples only** (same station, base time and horizon, both scored, neither stale), against **both** `persistence-v1` and `persistence-naive`:
  - CRPSS (fair);
  - **MAE skill of the median** (`1 − MAE / MAE_ref`, point against point);
  - BSS.
  - "Too few events to judge" is shown instead of a skill number below 30 events.
  - The headline comparison is against pure persistence (`persistence-naive`). A model that does not beat it on both fair CRPS and median MAE has no skill to claim.
- **NOAA matched comparison** (includes `persistence-naive` from Stage 3):
  - base times at 00/06/12/18Z and horizons that are multiples of 6 h;
  - NOAA's latest issuance whose points were fetched by our `created_at`, compared at the same `valid_at`;
  - metrics: absolute error, and Brier with p ∈ {0, 1} for the official categories; NOAA's own lead (`valid_at − issuedTime`) is reported, since NOAA issues about once a day.
- **Summary:** materialised after every scorer run with its `scorer_run_id`: `GET /v1/scores/summary`, `GET /v1/scores/official`. No performance number appears in the docs or UI except as output of this scorer, with its run ID.

## Metrics

| Metric | What it tells you |
|---|---|
| Brier score and Brier skill score vs persistence | Accuracy of crossing probabilities |
| Reliability diagram, expected calibration error (ECE) | Whether "70%" means 70% |
| CRPS (fair: exact integral of the CDF rebuilt from the stored quantiles; D-03.4) and MAE of the median | Accuracy of the level forecast; both against pure persistence |
| Hit rate, false-alarm ratio | Alert usefulness |
| Median lead time gained over advisory | The headline value |
| Feed lag p95, alert-to-call p95 | System reliability |

## Thresholds and kill criteria

| Gate | Pass | If it fails |
|---|---|---|
| Skill | Brier skill score vs persistence ≥ 0.10 at 12 h | Ship "gauge watch + trend" mode only and say so publicly |
| Calibration | ECE ≤ 0.05 per horizon | Recalibrate; if still failing, show levels only, no probabilities |
| False alarms | FAR no worse than the advisory baseline at equal lead time | Raise default risk threshold |
| Ingest SLO | 99% within 10 min | Switch to HTTPS polling |
| Alert SLO | p95 < 60 s | Disable contact fan-out until fixed |

## Rollback triggers

- Any build where ECE regresses above 0.05 fails CI.
- Any forecast issued with stale inputs (input age above the source's green lag: 150 min ECCC, 120 min USGS) is flagged in the ledger, left out of the default score summary and suppressed from alerts.
- A model version that underperforms persistence on the live ledger for 48 consecutive hours is rolled back.

## Demo Day numbers to show

1. Live skill vs pure persistence (`persistence-naive`) and trend at 12 h and 24 h, from the ledger.
2. Live reliability curve.
3. Lead time gained in the 2021 replay.
4. False-alarm ratio per season from the backtest.
5. Ingest and alert SLOs achieved.
