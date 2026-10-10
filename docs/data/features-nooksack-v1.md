# Nooksack hourly training set v1: features, targets and why each is available at issue time

Built by `floodlead history build datasets` (`src/floodlead/datasets.py`, D-03.17). Files, row counts and sha256 are in the stage doc (part 2) and `/srv/floodlead/datasets/datasets.json` on the VM. They are not committed: about 0.3 GB.

One row per hourly **issue time t** (UTC, on the hour), 2004-10-01 → 48 h before the build. Two files, never mixed:

- `nooksack_hourly_honest_v1.csv.gz`: only information available at t;
- `nooksack_hourly_oracle_v1.csv.gz`: the same columns plus future observed rain. **It is an upper bound only.**

## Publication latency used (cut-off = t − latency)

| Source | Latency used | Measured | Notes |
|---|---|---|---|
| USGS 15-min stage (North Cedarville, NF, MF, SF, Everson, Ferndale, SR 544 overflow) | 60 min | newest value 14–52 min old (Stage 1, Oct 7) | History is USGS-approved (revised) data; `data_status` marks it |
| NRCS SNOTEL hourly (909, 910, 1011) | 120 min | newest hour-ending value 40 and 41 min old (probes 20:40Z and 21:40Z, Oct 9; more probes overnight) | Conservative until more probes are summarised |
| KBLI hourly METAR (NCEI history) | 20 min | NCEI's copy is **not live**: no records in the last 7 days at either probe | Live use needs the NWS METAR feed, a new source to add with its own record in Stage 5. The same observations, so the history stands in for it |
| NWS warning products (NRKW1 FL.W) | at issuance | IEM archive, product time from the WMO heading | The comparator, not a model input in the ablations that exclude it |
| Open-Meteo previous runs (as-issued forecast rain) | issue-time rule | start dates measured: day 1 from 2024-01-19, day 2 from 2024-01-20 | Day-1 values only for valid hours ≤ t + 18 h; day-2 values only for valid hours ≤ t + 42 h |
| Open-Meteo reanalysis (ERA5 family) | — | reanalysis lag is days; the recent "archive" hours are model-filled (probe) | **Oracle only:** future rain over (t, t + H] |
| ECCC hourly climate (Abbotsford, Hope, Pitt Meadows, White Rock) | not used in v1 | Abbotsford: 0 % hourly precipitation; newest hour ~14 h old | Fraser Valley daily set only (Hope, Pitt Meadows daily sums) |

## Columns (honest)

| Column(s) | Meaning | Source, cut-off |
|---|---|---|
| `issue_time`, `wy`, `holdout`, `variant`, `data_status` | Issue time, water year (Oct–Sep), held-out flag (WY2022, WY2026), variant, approved history or provisional live archive | — |
| `{g}_lvl` for g in nc, nf, mf, sf, everson, ferndale | Latest stage (ft) at or before t − 60 min (within 2 h) | USGS, t − 60 min |
| `{g}_d1h`, `_d3h`, `_d6h`, `_d12h` | Stage change over the last 1, 3, 6 and 12 h before the cut-off | USGS, t − 60 min |
| `{g}_max24h` | Highest stage in the 24 h before the cut-off | USGS, t − 60 min |
| `nc_mean7d`, `nc_mean30d` | North Cedarville mean stage over 7 and 30 days (antecedent wetness) | USGS, t − 60 min |
| `asof_usgs` | Newest USGS timestamp used (the leakage test checks it ≤ t − 60 min) | — |
| `overflow_lvl`, `overflow_flowing` | SR 544 overflow stage, and whether water was flowing (any record before 2026-10-01; ≥ 3.6 ft after). NaN before the gauge began (2015-11-14) | USGS, t − 60 min |
| `snotel_p{1,3,6,12,24,48,72}h` | Mean over the 3 SNOTEL sites of the precipitation in the last N hours (mm; hourly increments of the accumulation) | SNOTEL, t − 120 min |
| `snotel_swe_mm`, `snotel_swe_d24h` | Snow water equivalent, and its 24 h change (snowmelt or accumulation) | SNOTEL, t − 120 min |
| `asof_snotel` | Newest SNOTEL timestamp used | — |
| `kbli_p{1,3,6,24,72}h` | Bellingham airport precipitation in the last N hours (mm) | KBLI, t − 20 min |
| `asof_kbli` | Newest KBLI hour used | — |
| `fc_rain_0_18h`, `fc_rain_18_42h` | As-issued basin-mean forecast rain for (t, t+18 h] (day 1) and (t+18, t+42 h] (day 2); NaN before 2024-01-19 | Open-Meteo previous runs, issue-time rule |
| `doy_sin`, `doy_cos` | Season | — |
| `nws_in_force`, `nws_issued_at`, `nws_crest_ft`, `nws_severity` | The latest North Cedarville flood-warning product issued at or before t whose event was still in force | NWS via IEM, at issuance |
| `nws_p_ge_148`, `nws_p_ge_150` | NWS-derived probabilities: 1 if that product's forecast crest is at or above 148 / 150 ft, else 0 (0 when none in force) | as above |

**Oracle only:** `oracle_future_rain_{6,12,24,48}h`, the basin-mean reanalysis rain over (t, t + H]. It is **not** available at t.

## Targets

| Column(s) | Meaning |
|---|---|
| `y_lvl_h1` … `y_lvl_h48` | North Cedarville stage (ft) at t + h, the 15-min reading at or up to 10 min before t + h |
| `y_minor_{6,12,24,48}h`, `y_moderate_…`, `y_major_…` | 1 if North Cedarville reaches 146.5, 148 or 150 ft in (t, t + H] |
| `y_overflow_{6,12,24}h`, `y_overflow_onset_h` | 1 if SR 544 overflow water begins in (t, t + H], and the hours to onset. NaN before the gauge, or when water was already flowing at the cut-off |

Note: 148 ft = NWS moderate and 150 ft = major at North Cedarville, so `y_moderate_*` and `y_major_*` are the Stage 4 crest-probability targets (addendum 1, section 4).

## Revisions

- **History:** the history is approved data, revised after the fact. It is not what a live forecaster saw: provisional values can differ, especially at flood peaks.
- **Live archive:** from 2026-10-07, FloodLead's own archive keeps the provisional values as first seen. The live ledger is the only fully as-seen test.
- **Protocol:** `docs/evaluation-protocol.md` states this limit.

## Fraser Valley daily set v1

`fraser_valley_daily_{honest,oracle}_v1.csv.gz` has one row per gauge and day, for the 7 Fraser Valley gauges, from ECCC daily means (HYDAT, approved, to 2024).
- **Features:**
  - level on days d, d−1, d−2 and d−7;
  - upstream gauges' levels on d and d−1;
  - daily rain at Hope and Pitt Meadows (where reported);
  - season.
- **Targets:** daily mean on d+1 to d+3, and whether any of them reaches the typical yearly peak.
- **Oracle:** adds the next 3 days of reanalysis rain at the basin point.
- **Sub-daily:** the 5-min live data since Sep 2026 are in `observations`; sub-daily travel times cannot be learned from daily history.
