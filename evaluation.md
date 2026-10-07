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

## Online: live public ledger

- Every hourly forecast for every station, from the first day of ingestion, appended with a SHA-256 chain.
- The chain head is committed daily to `ledger/heads.txt` in this repo.
- Scores update as truth arrives; the summary endpoint shows skill vs every baseline.

## Baselines (same scoring code)

1. Persistence — level stays the same.
2. Linear trend extrapolation over the last 3 h — what a person watching the chart does.
3. RFC advisory level mapped to a probability.
4. RFC CLEVER / COFFEE where published.
5. Google Flood Hub where it covers the gauge.

## Metrics

| Metric | What it tells you |
|---|---|
| Brier score and Brier skill score vs persistence | Accuracy of crossing probabilities |
| Reliability diagram, expected calibration error (ECE) | Whether "70%" means 70% |
| CRPS (from P10/P50/P90) | Accuracy of the level forecast |
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
- Any forecast issued with stale inputs (> 30 min) is flagged in the ledger and suppressed from alerts.
- A model version that underperforms persistence on the live ledger for 48 consecutive hours is rolled back.

## Demo Day numbers to show

1. Live skill vs persistence and trend at 12 h and 24 h, from the ledger.
2. Live reliability curve.
3. Lead time gained in the 2021 replay.
4. False-alarm ratio per season from the backtest.
5. Ingest and alert SLOs achieved.
