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

### Amendment 1 — 2026-10-10 (supervisor review A1–A3, A5, A7, A8)

Added after the supervisor's review of the frozen text (`docs/build/prompts/STAGE-03-protocol-review.md`). No model had been trained. The frozen text above is unchanged; where this amendment differs from it, this amendment applies.

**A1. Training never sees held-out or live rows.**
- **Development years** are WY2005–WY2025 except WY2022.
  - Every training fold, every calibration fit and every choice of (p\*, k) uses development years only.
  - In walk-forward, validation year k is trained on development years before k. For k ≥ 2023 this **excludes WY2022**; the frozen §2 wording "WY2005…WY(k−1)" would have included it.
- **Held out:** WY2022, WY2026, and **WY2027 onward as the live period**.
  - Correction to §11: the live period from Oct 1, 2026 belongs to WY2027, not WY2026.
- **The frozen files are not rebuilt; their sha256 values stand.** They flag only WY2022 and WY2026 as `holdout`, so the 167 hourly rows of Oct 1–7, 2026 (WY2027) carry `holdout = false`. Every Stage 4 read therefore goes through `src/floodlead/train_data.py`:
  - it selects rows by water year;
  - it raises `HeldOutRowError` when a held-out or live year is requested, or reaches a training or calibration set;
  - it raises on a development row flagged `holdout`.
  - `tests/test_train_data.py` checks that it rejects WY2022, WY2026 and WY ≥ 2027.
  - On the frozen honest file it reads 175,320 development rows, 8,760 in each held-out year, and 167 live rows.

**A2. How the final run is trained**, fixed now as if the system had been live:
- WY2022 is scored by a model trained on WY2005–WY2021.
- WY2026 is scored by a model trained on WY2005–WY2025, **including WY2022**: a live system would have had the 2021 flood by December 2025.
- The live period (WY2027) is scored by the WY2026 model.
- Features, hyperparameters, the calibration method and (p\*, k) are frozen from the walk-forward folds. Nothing is chosen on WY2022 or WY2026. The folds are `train_data.final_run_folds()`.

**A3. T5 is crossing-probability skill; T6 is added for level skill.**
- **T5**, renamed "crossing-probability skill": Brier skill score ≥ 0.10 against persistence at 12 h, and ECE ≤ 0.05 per horizon (evaluation.md's kill criteria). It is a Brier score, not level skill.
- **T6, level skill (new):** fair CRPSS > 0 **and** median-MAE skill > 0 against pure persistence at 6, 12 and 24 h, overall and on rising limbs (§4's definition). This is evaluation.md's headline test: "A model that does not beat it on both fair CRPS and median MAE has no skill to claim."
- Both are reported as met or not met, with their bootstrap intervals (§8).

**A5. The model's tiers stay as frozen in §5.**
- Addendum 3's "Prepare-M" **is** §5's prepare tier: North Cedarville ≥ 148 ft within 24 h, with (p\*, k) chosen on validation years only.
- The model's move tier stays at overflow onset within 12 h.
- **No new model target is added.**
- Prepare-M is reported beside relay v2's NWS-based Prepare (amendment 2). It replaces it only if it wins under this protocol.

**A7. Two more validity limits**, added to §10:
- **SR 544's onset definition changed.**
  - The gauge has reported continuously since Oct 1, 2026, reading about 3.53 ft when no water flows. A live onset is therefore the first reading ≥ 3.6 ft.
  - Before that, the gauge reported only while water flowed, and the historical onset is the first record.
  - The two definitions differ, so live onset timing is compared with history only with this stated.
- **Relay v2 is in-sample** (amendment 2).

**A8. Wording.**
- **T3, "no systematic low bias":** the 95 % bootstrap interval of (mean forecast probability − observed frequency) must not lie entirely below 0.
- **T1:** the comparison with the City of Abbotsford's alert exists for **2 events only** (Nov 2021, Dec 2025). Every report of T1 says so.

### Amendment 2 — 2026-10-10 (relay v2; supervisor addendum 3 and review A4)

A second relay comparator, counted **by alert**, added before any model is trained. Relay v1 (§3 item 5, frozen at `45367d1` and pinned as `relay-v1.json`) stays as built.

**Relay v2 is descriptive and in-sample.**
- On Oct 9 the supervisor chose its Prepare tier and its 5.0 ft Move-now level after seeing every year, including the held-out ones.
- Its numbers are **never presented as held-out results**.
- The 5.0 ft level is labelled "chosen after seeing the data" everywhere. The 4.0 ft variant (the NWS minor stage at SR 544) was not chosen from the data, and is always reported beside it.

**Tiers** (addendum 3, section 1):

| Tier | One alert is | What the farmer does |
|---|---|---|
| Watch | each NWS flood watch event (FFASEW; VTEC FA.A or FL.A; one per phenomena, ETN and year) whose segment names Whatcom, at its NEW product | nothing costly |
| Heads-up | each NWS North Cedarville river flood warning event (FL.W, H-VTEC `NRKW1`; one per ETN and water year), at its NEW product | check fuel, trailers and contacts |
| Prepare | in each such event, the first product with H-VTEC severity ≥ 2 (moderate or worse forecast); at most one per event | line up trucks and a receiving farm; move young stock and equipment |
| Move now (provisional) | the first SR 544 reading ≥ 5.0 ft in an overflow episode (variant: ≥ 4.0 ft) | move milking herds and poultry |
| Everson overflow warning (descriptive row) | each areal flood warning event (FA.W) whose segment names Everson and overflow, at its NEW product | — |

**Counting rules** (fixed here, before the numbers are computed):
- **Record period:** from the first SR 544 record in our gauge history (2015-11-14 09:15Z; the USGS file starts at 08:15Z, under check per addendum 3 §6) to the build time.
  - Alerts issued before the record start are not counted.
  - An overflow episode whose warning event began before the record start is not counted. This is the 2015-11-14 episode, part of ETN 55, issued 2015-11-13 20:00Z.
- **Overflow episode:**
  - SR 544 records before 2026-10-01, or readings ≥ 3.6 ft from then on, grouped by gaps of more than 48 h;
  - onset = the first record, peak = the maximum;
  - **large** = peak ≥ 5.0 ft.
- **Window and outcomes:**
  - An alert's window runs from its event's first product − 12 h to its event's end + 24 h. The event's end is the latest VTEC end time among its products, or its last product if none has one.
  - An alert is **followed by an overflow** if an overflow onset lies in that window. **Large** means that overflow is large.
  - **Lead** = onset − alert time, listed per alert. A negative lead means the alert came after the onset.
  - Move-now alerts are scored against their own episode: always an overflow, by construction. Their lead is negative: the reading comes after the onset.
- **Missed overflow:** an overflow episode with no alert of that tier whose window contains its onset.
- **Precision:** followed / alerts, with an exact Clopper–Pearson 95 % interval.
- **Day or night:** at Abbotsford (`floodlead.sun`).
  - Move now always pushes.
  - Whether Prepare pushes at night is the farmer's choice (Stage 7).
- **Gauge missing:** if SR 544 is not reporting, the alert says so. A Move-now signal is never inferred.
- **2021 and 2025:** each tier's time against Abbotsford's first alert and first order, with the review's ranges. These are 2 events only (amendment 1, A8).

**The trust table** is a code output with a run ID (`floodlead history build trust`). It has one row per tier:
- alerts, and alerts per year;
- followed by any overflow, and by a large one;
- precision with its 95 % interval;
- overflows missed;
- the lead for each alert;
- the 2021 and 2025 comparisons.

**Every alert is listed with its outcome.** No rate is shown without its list, and alert wording takes its numbers from this table, never hard-coded (addendum 3, section 4).

**What relay v2 does not claim** (addendum 3, section 5):
- Its precision is the official warnings' precision.
- FloodLead adds delivery to the farmer's phone, farm terms and tiers, the odds on every alert, and a public record.
- A better forecast than NWS is claimed only if this protocol shows one.

**Re-check:** the 5.0 ft Move-now level is re-checked after the first overflow of the 2026–27 season, because the 2026 SR 544 bridge changes the hydraulics. This is stated here and in the alert help text (Stage 7).

**Reproducibility:** the supervisor's independent count (addendum 3, section 2) is reproduced by the code. Any difference is reported with both counts and the reason; neither is adjusted to match.

### Amendment 3 — 2026-10-10 (AI-rainfall case study; supervisor addendum 2, review A6)

Addendum 2's items T0–T3 are renamed **R0–R3**, so they do not clash with targets T1–T6. This case study is **one event, descriptive**. Whatever it shows, it **changes nothing in the product before Demo Day**. It is fixed here before any of its data is pulled.

**R0, availability (Stage 3 part 2):**
- Query the Open-Meteo Previous Runs API for precipitation over Dec 7–12, 2025, with the previous-day-1 and day-2 offsets, at the sample points below.
- Models: `ecmwf_aifs025_single`, `ecmwf_ifs025`, `gem_hrdps_continental`, `ncep_hrrr_conus`, `ncep_nbm_conus`. The exact names are checked against the Open-Meteo docs, and any substitution is recorded.
- Record which models return values at fixed leads.
- If AIFS returns none: record "AI rainfall not testable before Demo Day" and drop R1–R2.
- Calls are paced, cached on disk and counted. If the free tier refuses, the run waits for the daily reset and that is said; a paid plan needs the human's approval.

**Sample points:** the forecast grid cells containing the approved upper-basin rain gauges, i.e. the Nooksack SNOTEL sites:
- Wells Creek 909 (48.8661, −121.7898);
- Elbow Lake 910 (48.6909, −121.9089);
- MF Nooksack 1011 (48.8244, −121.9295).

Coordinates are from the NRCS AWDB station list, and each model's own grid cell is used.

**Windows:** 24 h and 48 h ending at North Cedarville's minor-stage crossing, 2025-12-10 20:15Z. In hourly totals these are the hours ending 21:00Z Dec 9 … 20:00Z Dec 10 (24 h), and 21:00Z Dec 8 … 20:00Z Dec 10 (48 h).

**Truth:** the hourly gauge totals at the same three SNOTEL sites (`rain_hourly`, the hourly increase of the accumulation). **Never IMERG.** SNOTEL storage gauges can under-catch in wind and snow; that is stated with the result.

**Outputs, per model, site and window:**
- the forecast total at the day-1 and day-2 lead, and the observed total;
- their ratio;
- the timing error (h) of the heaviest 6 h: the end of the highest 6-h running sum, forecast minus observed.

**Reporting:**
- every model is reported, including those that do badly or return nothing;
- the label is "one event, descriptive";
- AIFS is treated as 6-hourly information, because Open-Meteo interpolates it to hours.

**R1** (Stage 4, Oct 10–11, only if Stage 4 is on schedule): run the case study as fixed above. Precipitation forecasts are cut first if time runs short (PLAN.md).

**R2** (Stage 4, optional): plug each rain source into the Stage 4 model on the Dec 2025 holdout, without retraining. Every variant is reported, labelled "sensitivity, not skill".

**R3** (optional, after the core of part 2): the satellite timeline and flood-extent overlay from NRCan EGS flood polygons for 2021 and 2025.
- Its usage-rights record comes first.
- It is a zone layer on the replay page only, never a forecast input or a timing label.

**Not built or bought:**
- satellite segmentation pipelines;
- commercial imagery;
- vision-language models reading imagery;
- self-hosted AI weather models;
- Google WeatherNext access.

**After Demo Day** (roadmap only): a live shadow archive of AI and physics rainfall forecasts, logged as issued and scored storm by storm against basin gauges. AI rain becomes a model feature only after at least 30 scored wet days show lower 24 h and 48 h CRPS than HRDPS and NBM.

### Amendment 4 — 2026-10-10 (Stage 4 design choices, fixed before any model is fitted)

Added at the start of Stage 4 (`docs/build/prompts/STAGE-04-model.md`, item 2), **before any model was fitted**. Where the Stage 4 prompt and this protocol differ, the protocol wins.

**1. NWS inputs.**
- The NWS-derived columns (`nws_*`) are **comparators, not inputs** to the primary model. That keeps "model vs NWS" a fair comparison.
- A post-processing variant "plus NWS products" may be added as one extra ablation, labelled as such. It is not the primary model.

**2. Targets.** Both are derived from the frozen files' columns; nothing is rebuilt.
- **Level change:** North Cedarville at the ledger horizons h ∈ {1, 3, 6, 12, 18, 24, 36, 48}, as `y_lvl_h − nc_lvl` (`nc_lvl` is the latest reading at the feature cut-off).
- **Window maximum:** M_H = max(`y_lvl_h1` … `y_lvl_hH`) for H ∈ {12, 24, 48}, as `M_H − nc_lvl`. M_H is defined only when at least H − 2 of the H hourly targets exist.

**3. Quantiles.**
- 19 levels, 0.05 … 0.95.
- Each family fits its own levels and is interpolated linearly in level to the 19.
- The 19 values are sorted, so they never cross.
- Fair CRPS of the stored quantiles is computed with `crps.fair` (exponential tails).

**4. Crossing probabilities.**
- P(level ≥ X within H) = 1 − F_H(X − `nc_lvl`), where F_H is the predictive CDF of M_H − `nc_lvl`: piecewise linear between the 19 quantiles, with the exponential tails of `crps.py`. **Never from a classifier trained on threshold labels** (§2.1).
- A calibration map (isotonic, on the raw probability) is allowed only under two conditions:
  - it is fitted on pooled walk-forward validation predictions;
  - in a leave-one-validation-year-out check it lowers the Brier score for ≥ 148 ft within 24 h.
- Otherwise the raw CDF probabilities are used.

**5. Overflow onset (the model's move tier).** With 3 development overflows, no high-capacity classifier is allowed.
- **Default:** P(onset within H) = mean over the development episodes j of P(M_H ≥ L_j). L_j is the North Cedarville level at SR 544 onset in development episode j (Nov 2015, Nov 2017, Feb 2020, the replay's `cedarville_ft_at_onset`, the latest North Cedarville reading at or before the onset).
- **Onset time:** when the predicted median path (the median at 1, 3, 6 and 12 h, linearly interpolated) first reaches the median of the L_j.
- **Alternative:** a logistic model with at most 3 inputs (`nc_lvl`, `nc_d3h`, `snotel_p24h`), chosen on validation only if its pooled validation Brier for onset within 12 h is lower.
- The overflow targets are undefined when water was already flowing at the cut-off (as in the datasets).

**6. Model families compared on validation** (one is chosen, and the reason is logged):
- **(a)** Linear quantile regression on a small feature set: `nc_lvl`, `nc_d1h`, `nc_d3h`, `nc_d6h`, the three forks' `_d3h`, `snotel_p6h`, `snotel_p24h`, `kbli_p6h`, `doy_sin`, `doy_cos`.
  - Missing inputs are filled with their training medians.
  - Fitted at the 7 levels 0.05, 0.1, 0.25, 0.5, 0.75, 0.9 and 0.95 on a random subsample of at most 30,000 training rows per fold, with a fixed seed.
- **(b)** Gradient boosting (LightGBM, quantile objective) at the same 7 levels, on the feature group's columns, with fixed hyperparameters (200 trees, learning rate 0.05, 31 leaves, min 50 rows per leaf).
- **Quiet-row subsampling** (keep all rows with |`nc_d3h`| ≥ 0.1 ft or `nc_lvl` ≥ 144 ft, and 20 % of the others, fixed seed) is a candidate for both families. It is kept only if it wins on validation.
- **Selection criterion, fixed now:**
  - the lowest pooled validation fair CRPS, averaged over h ∈ {6, 12, 24} and over all rows;
  - tie-break (within 1 %): the lower Brier for ≥ 148 ft within 24 h.
  - Every candidate is reported, including the ones that lose.

**7. Feature groups for the ablations (§7).**
- **G**, gauges only: North Cedarville, the three forks, Everson and Ferndale (level, 1/3/6/12-h changes, 24-h max), `nc_mean7d`, `nc_mean30d`, `doy_sin`, `doy_cos`.
- **G+R**, plus observed rain: SNOTEL precipitation, SWE and its change, and KBLI (with its live caveat: needs the NWS METAR feed). **This is the primary model**, because its inputs exist in every year.
- **G+R+F**, plus as-issued forecast rain (`fc_rain_0_18h`, `fc_rain_18_42h`). The values exist only from 2024-01-19, so it is scored on validation WY2024–2025 and held-out WY2026 only, and every number says so.
- **Oracle** (G+R plus `oracle_future_rain_*`): an upper bound, always labelled.
- **Relay only:** the comparator rows (relay v1, relay v2).

**8. Alert rules.**
- (p\*, k) for the prepare tier (≥ 148 ft within 24 h) and the move tier (overflow within 12 h), chosen per §5 on pooled validation predictions only.
- Each event-based rate carries its exact interval.

**9. Re-runs.**
- The final run happens once.
- A re-run needs a further dated amendment saying why, and **both** results are reported.

**10. Checkpoint before the final run.**
- The final models are trained per A2 with `train_data.final_training_rows()`.
- Their manifest (`docs/data/stage4-final-manifest-v1.json`: code commit, dataset sha256 values, configuration, features, (p\*, k), calibration maps, artifact sha256 values and training years) is committed.
- Its sha256 is recorded in the ledger as a new `model_card` entry (`floodlead-nooksack-v1`) and anchored, before any held-out row is scored.

**11. Compute limits.**
- Training runs only in one-off containers capped at 1 CPU and 3 GB, reading the datasets read-only.
- Models are written to `/srv/floodlead/models/<run_id>/`, never overwritten.
- `/v1/track-record` is checked for gaps after each long job.
