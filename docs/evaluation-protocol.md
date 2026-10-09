# FloodLead BC — pre-registered evaluation protocol (Stage 4)

> **Status: FROZEN on 2026-10-09 (Stage 3 part 2), before any model was trained.** From now on this file changes only through dated amendments at the end, each logged in the stage doc. The supervisor reviews it before Stage 4 starts. The commit and sha256 of this frozen version are recorded in `docs/stages/STAGE-03-public-history.md`.
> Written by the build worker on Oct 9, 2026, after the supervisor's [Stage 3 addendum 1](build/prompts/STAGE-03-addendum-1.md) and the [status-quo review](research/fraser-valley-flood-warning-status-quo.md). Every target below is reported as **met or not met**, never tuned to pass.

## 1. What is being tested

FloodLead's value has three layers, and they are scored separately so that none takes credit for another:

1. **Relay:** existing official products pushed in farm terms.
2. **Automated observation:** gauge triggers, such as the SR 544 overflow gauge.
3. **Model skill:** calibrated probabilities and timing that no one else produces.

Layers 1 and 2 are model-free (`src/floodlead/relay.py`). Layer 3 is the Stage 4 model. A model result counts only as the improvement **over** layers 1–2.

**Stage 4 targets** (addendum 1, section 4), issued hourly:
- P(North Cedarville ≥ 148 ft) and P(≥ 150 ft) within 12, 24 and 48 h;
- P(overflow onset at SR 544) within 6, 12 and 24 h, and the onset time;
- North Cedarville level at 1–48 h (for level skill).

## 2. Data

- **Datasets:** `nooksack_hourly_honest_v1.csv.gz` and `nooksack_hourly_oracle_v1.csv.gz`, built by `floodlead history build datasets` (`src/floodlead/datasets.py`). The sha256 of each file, its row count and the build commit are pinned in section 11 when frozen.
- **Issue times:** hourly, 2004-10-01 to the build. Every feature is cut at issue time minus its source's measured publication latency:
  - USGS 60 min;
  - SNOTEL 120 min;
  - KBLI 20 min;
  - NWS products at their issuance time;
  - as-issued forecast rain only for valid hours it had been issued for (day 1 ≤ t + 18 h, day 2 ≤ t + 42 h).
- **Variants, never mixed:**
  - `honest`: past observations, plus as-issued forecast rain where it exists, from 2024-01-19 (Open-Meteo previous runs, measured);
  - `oracle`: adds future *observed* reanalysis rain. **It is an upper bound only and is labelled as such everywhere it appears.**
- **Rain inputs measured unusable or unavailable live:** Abbotsford A hourly precipitation (0 % in ECCC's archive); NCEI's KBLI copy (no records from the last 7 days); the reanalysis (oracle only). KBLI enters `honest` as a stand-in for the live NWS METAR feed of the same observations.
- **Revisions:** the gauge history is USGS-approved data, revised after the fact. It is not exactly what was visible live, and every row is labelled `data_status`.
  - This departs from evaluation.md's "no revised values as features", because no as-seen archive exists before Oct 2026.
  - The live ledger (from 2026-10-08) is the only fully as-seen test, and it is reported separately.
- **Splits by water year (Oct–Sep):**
  - **Walk-forward development:** train on WY2005…WY(k−1), validate on WY k, for k = 2016…2025 except 2022.
    - All model choices, hyperparameters, calibration and the alert rule are made on these validation years only.
    - The SR 544 overflow gauge exists from WY2016 (record begins 2015-11-14), so overflow targets are validated on WY2016–2025.
  - **Held out until one final run:**
    - **WY2022 (Nov 2021 flood);**
    - **WY2026 (Dec 2025 flood);**
    - the live period from Oct 2026.
    - They are run once, with the frozen model and rule, and reported whatever they show.
- **Events:** the event catalogue (`catalogue.json`, sha256 pinned in section 11):
  - every North Cedarville minor-stage event (runs ≥ 146.5 ft, merged when under 48 h apart);
  - its crossings and crest;
  - the SR 544 onset;
  - the first NWS warning and its forecast times.

### 2.1 How many events there are (from the frozen catalogue), and what that allows

| Threshold at North Cedarville | Development events (WY2008–2021, 2023–2025) | Held-out events (WY2022, WY2026) |
|---|---|---|
| Minor (146.5 ft) | 16 | 4 |
| Moderate (≥ 148 ft) | 5: Jan 2009, Dec 2010, Nov 2015, Nov 2017, Feb 2020 | 2: Nov 2021, Dec 2025 |
| Major (≥ 150 ft) | **0** | 2: Nov 2021, Dec 2025 |
| SR 544 overflow (gauge operating) | 3: Nov 2015, Nov 2017, Feb 2020 | 4: Nov 14 2021, Nov 28 2021, Dec 2025, Mar 2026 |

As hourly rows (`scripts/check_datasets.py`), the counts of positive y_major_24h / y_moderate_24h / y_overflow_12h are: development 0 / 161 / 50; held-out 56 / 91 / 70.

Consequences, fixed now:
- **P(≥ 150 ft) cannot be learned or calibrated on development data.** There is no positive example.
  - The model must derive it from its level distribution (forecast quantiles of the crest), never from a classifier trained on 150-ft labels.
  - Its calibration cannot be checked before the final run. At the final run it rests on 2 events and is reported descriptively. It is never claimed as "reliable".
- **Overflow and ≥ 148 ft alert rules are chosen on 3 and 5 development events respectively.** Every event-based rate carries its exact binomial interval: 3 of 3 has a 95 % lower bound of 0.29.
- The held-out years contain more large events than the development years. This is stated next to every held-out result.

## 3. Comparators (all scored on the same rows and events)

1. **Pure persistence:** the level at the cut-off, held flat (point forecast).
2. **3-hour trend:** the last 3 h slope, applied for at most 6 h, then held (`trend3h-v1`).
3. **Gauge-watch rule:** overflow follows the minor stage at North Cedarville (the replay's onset statistics, D-02.4).
4. **Official NWS warnings as issued:** NWS-derived probabilities, 1 when the forecast crest of the product in force at the issue time is at or above the threshold, else 0. Its forecast flood-begin and crest times serve as timing forecasts.
5. **Relay rules** (`relay.py`), alone, pre-registered here as built on Oct 9:
   - **heads-up:** an NWS flood watch naming Whatcom, issued from 7 days before the minor crossing to its end;
   - **prepare:** an NRKW1 warning forecasting ≥ minor (severity 1–3 or crest ≥ 146.5 ft), or an NWS warning segment naming the Everson overflow, issued from 72 h before the minor crossing to its end;
   - **move:** the SR 544 overflow onset, or North Cedarville ≥ 146.5 ft and rising.
   - A minor event without overflow counts as a false alarm for every tier that fired.
   - BC River Forecast Centre watches cannot be replayed (not archived; licence yellow) and are named as a later comparator.

## 4. Metrics

- **Level skill against pure persistence**, at 6, 12 and 24 h:
  - fair CRPS (`src/floodlead/crps.py`) and MAE of the median;
  - overall, and on **rising limbs** (rows where North Cedarville rose ≥ 0.5 ft in the 3 h before the cut-off).
- **Crossing probabilities** (148 and 150 ft within 12, 24 and 48 h; overflow within 6, 12 and 24 h):
  - Brier score and Brier skill score against each comparator;
  - reliability diagram with 10 bins and ECE.
- **Hours of warning**, per event: first alert time before the observed crossing of minor, moderate and major, and before the overflow onset. Reported as median and range, with n events.
- **False alarms per season:** alerts (after the persistence rule below) with no crossing within the target window, per water year, over all walk-forward validation years.
- **Event-based rates (POD, FAR):**
  - a hit is an alert issued before the observed crossing and no more than 48 h before it;
  - **exact (Clopper–Pearson) 95 % binomial intervals on every event-based rate**;
  - 5 of 5 still means a lower bound of about 0.48, and 10 of 10 about 0.69.

## 5. Alert rule (chosen on validation years only)

An alert for threshold X fires at the first issue time when P(X within H) ≥ p\* for k consecutive hourly issuances.
- (p\*, k) is chosen from p\* ∈ {0.1, 0.2, …, 0.9} and k ∈ {1, 2, 3}.
- The choice maximises the median hours of warning, subject to FAR ≤ 0.5 for the prepare tier (148 ft, H = 24 h) and FAR ≤ 0.2 for the move tier (overflow onset, H = 12 h), pooled over the validation years.
- If no (p\*, k) meets the FAR limit, the rule with the lowest FAR is reported, and the target is **not met**.

## 6. Targets: the review's bar (each reported as met or not met)

| # | Target | Bar |
|---|---|---|
| T1 | Prepare tier | Fires ≥ 24 h before water reaches the border **and** ≥ 6 h before the City of Abbotsford's alert, in most overflow events; FAR ≤ 0.5 |
| T2 | Move tier | ≥ 12 h before water reaches the farm's zone; POD ≥ 0.8 and FAR ≤ 0.2 |
| T3 | Crest probabilities, North Cedarville ≥ 148 and ≥ 150 ft within 12/24/48 h | No systematic low bias, i.e. mean forecast probability ≥ observed frequency within the 95 % bootstrap interval; reliable (ECE ≤ 0.05); BSS > 0 against NWS-derived probabilities across **all** archived warnings, not just 2021 and 2025 |
| T4 | Overflow onset timing at 1–12 h | Skill > 0 against persistence and trend at every lead; smaller median onset-timing error than the NWS issued forecasts |
| T5 | Level skill (evaluation.md kill criterion) | BSS against persistence ≥ 0.10 at 12 h; ECE ≤ 0.05 per horizon |

**Water at the border:**
- no agency recorded when the water crossed in 2021 or 2025;
- USGS Sumas River near Sumas (12214500) has no data for Nov 2021;
- the Emerson Rd gauge record starts in Jan 2024 and was offline on Oct 9, 2026.

So T1 and T2 use labelled **ranges** from analogues (for 2025, a crossing 10–20 h after the overflow onset). They are scored against both ends, and no accuracy is claimed unless at least 3 events have verifiable arrival times.

## 7. Ablations (each scored with the same metrics)

1. Relay rules only.
2. Gauges only (North Cedarville, upstream forks, Everson, overflow).
3. Plus observed rain (SNOTEL, KBLI).
4. Plus as-issued forecast rain (from 2024-01-19 only, so on fewer events; stated).
5. Oracle (future observed rain): an upper bound, labelled.

## 8. Uncertainty

- Bootstrap by water year (1,000 resamples) for the continuous scores.
- Bootstrap by event for event-based rates, plus the exact binomial intervals.

## 9. Kill criteria (evaluation.md)

- If T5's skill gate fails, FloodLead ships the "gauge watch + relay" mode only and says so publicly.
- If calibration fails, it shows levels only, with no probabilities.
- If FAR is worse than the advisory baseline at equal lead, the default threshold is raised.

## 10. Validity limits (stated with every result)

- **The 2026 SR 544 bridge** (WSDOT, replacing the culvert "to let more floodwater through") changes the overflow relation. Overflow results fitted before it may not hold after it.
- **The Emerson Rd overflow gauge** (record from Jan 2024) was offline on Oct 9, 2026.
- **Large overflows are rare:** officials cite 1990, 2020, 2021 and 2025. Every event-based number rests on a handful of events, and its interval is shown.
- **NWS flood stages** are today's values. Older products were judged against stages that may have differed.
- **NWS-derived probabilities are 0/1**, so a Brier comparison favours any calibrated forecaster. This is stated with T3. "Across all archived warnings" means the walk-forward out-of-sample predictions for WY2016–2025 plus the held-out run, at every hourly issuance with a North Cedarville warning in force (0.2 % of rows).
- **The North Cedarville level record** in our history begins in WY2008. Earlier rows have gauge features but no North Cedarville level.

## 11. Reporting: the exact table published, whatever it shows

For each target (T1–T5) and each ablation, one row:

| Target | Variant | Period / events (n) | FloodLead | Pure persistence | 3 h trend | Gauge-watch | NWS as issued | Relay only | 95 % interval | Met? |
|---|---|---|---|---|---|---|---|---|---|---|

- Every event is listed with its times, including the events where FloodLead does worse.
- Held-out results (WY2022, WY2026, live) are shown separately from walk-forward results.

**Frozen inputs** (built 2026-10-09 22:45–23:03Z by image `floodlead-app:part2` at commit `f502b4924e6bd36e2ecebb85c9506adf96080dd5`; on the VM in `/srv/floodlead/datasets`; checked by `scripts/check_datasets.py` → 0 violations):

| File | Rows | sha256 |
|---|---|---|
| `nooksack_hourly_honest_v1.csv.gz` | 193,007 (136 columns) | `e0d165a99afd0103d209be37284efebe7878d85ba7426e07ce0c10a78e81549d` |
| `nooksack_hourly_oracle_v1.csv.gz` | 193,007 (140 columns) | `5ffea66a3cfed2fa9ea075e4a6114db8fedd7d3eece10852c6a60329e7400054` |
| `fraser_valley_daily_honest_v1.csv.gz` | 93,805 | `88a4e92ae51b83c279efb7ca306de22fecf64252b7796dd780661034d2a0f6bf` |
| `fraser_valley_daily_oracle_v1.csv.gz` | 93,805 | `63356ef750fb951a84cf16b333364358176a15f51425b4ae30c833baa64ee5cb` |
| `docs/data/catalogue-v1.json` (event catalogue) | 20 Nooksack events; BC typical-peak crossings | `0cbc83dbef5ac66a54bb17b3daef2a7184b8591cc1ce5314d5f803c09722bca9` |
| `docs/data/relay-v1.json` (relay replay) | 13 events | `28671f8d05b363e7841f1cc63148bd49feff91c0ca8459809840daec23d76667` |

Water years: held out are WY2022 (Oct 2021–Sep 2022) and WY2026 (Oct 2025–Sep 2026, including the live period to date). The development years are all others from WY2005 (from WY2008 for North Cedarville level; from WY2016 for the overflow).

## Amendments

(none)
