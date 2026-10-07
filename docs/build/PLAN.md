# FloodLead BC — build plan (Oct 7 → Oct 13, 2026)

## Roles and the QA loop

| Role | Who | Does |
|---|---|---|
| Worker | Claude Code on the GCP VM | Builds each stage, documents every decision while building, opens a PR, prints a STAGE REPORT |
| Supervisor / QA | Claude (separate session) | Writes stage prompts, independently verifies each stage, decides PASS or FIX, merges |
| Human | Pranay | Relays prompts and reports, holds credentials, approves anything that touches money or people |

```text
prompt ──► worker builds (stage doc grows with every commit) ──► PR + STAGE REPORT
   ▲                                                                   │
   │                                                                   ▼
next prompt ◄── PASS (merge) ◄── supervisor QA ──► FIX prompt ──► worker
```

**What the supervisor checks at every stage**

1. Pulls the branch and runs `ruff` and `pytest` independently.
2. Reads the stage doc's git history (it must have grown across commits, not appear at the end).
3. Hits the public endpoints and cross-checks numbers against the original sources (ECCC, USGS, NOAA).
4. Asks the value question for the stage (below): is this actually delivering what a farmer needs, or only code?

## Facts the supervisor verified before Stage 1 (Oct 7, 2026)

| Finding | Evidence | Consequence |
|---|---|---|
| ECCC OGC API real-time data is ~4 h behind (p50 245 min across 416 BC stations) | Queried `hydrometric-realtime` for BC, last 6 h | Do **not** use it as the live source |
| ECCC Datamart hourly CSVs are ~1 h behind (p50 61 min, p90 91 min, 30 stations sampled); all 429 BC files rewritten at :31 each hour | `dd.weather.gc.ca/today/hydrometric/csv/BC/hourly/` | Primary live source: poll Datamart hourly files after :31 |
| Datamart `daily` files hold 30 days of 5-min data (8,626 rows for 08MH001) | Same tree, `/daily/` | 30-day backfill source; anything older is lost unless archived |
| USGS 15-min data for the Nooksack is ~45 min behind; North Cedarville (12210700) has stage since 2007-10-01, flow since 2004-10-15 | USGS site catalog + IV service | Sub-daily training history covering the 2009, 2021 and 2025 floods |
| Nov 15, 2021 peak at Nooksack River at Everson (12211200): 52,300 cfs at 13:40 PST | USGS IV query | Independent cross-check value for the backfill |
| NOAA NWRFC publishes an official 7-day forecast for Nooksack at North Cedarville (NWPS `NRKW1`), 6-hourly points, plus official flood stages (action 144.8 ft, minor 146.5, moderate 148, major 150) | `api.water.noaa.gov/nwps/v1/gauges/NRKW1` | Official thresholds and an official forecast to score against, live |
| NOAA stage and USGS gage height share a datum (both ~138.0 ft on Oct 7) | Same-time readings | Thresholds apply directly to USGS data |
| The Nooksack overflow at Everson flooded Sumas Prairie in 2021 and Dec 2025 | City of Abbotsford bulletins | The US gauges are core, not optional |

## Value realism (what the supervisor will keep honest)

- **Effective lead time = forecast horizon − data latency.** With ~1 h latency, a "6 h" forecast gives ~5 h of real warning. Every forecast stores `data_as_of`; the UI shows it.
- **October may stay dry.** Live exceedance events may not happen before Demo Day. Live proof will rest on level-forecast accuracy (CRPS vs persistence and vs NOAA's official forecast); event proof rests on replays of 2021 and 2025.
- **History is uneven.** BC gauges have only daily history (decades). The Nooksack system has 15-min history since 2007. Sub-daily models are realistic for the Nooksack; BC gauges get a daily model.
- **No archive of past official forecasts was found.** The official-forecast comparison is live-only, from the day archiving starts. Say so.

## Stages

| # | Stage | Target | Value question the supervisor asks |
|---|---|---|---|
| 0 | Human setup: GCP project, VM, bucket, Claude Code, GitHub access | Oct 7, ~45 min | Can the worker build and deploy without blocking on access? |
| 1 | Foundation + live archive: ingest ECCC Datamart (all BC), USGS Nooksack/Sumas, NOAA official forecasts; raw archive to GCS; backfills; minimal public read API | Oct 7, before Build Session 2 (18:00) | Is data that disappears after 30 days now being kept, fresh to ~1 h, and verifiable from outside? |
| 2 | Forecast ledger + baselines: hourly persistence/trend forecasts, NOAA official forecast archived, hash-chained append-only ledger, scoring | Oct 7 night | Is every forecast fixed in time before the truth arrives, and scored honestly? |
| 3 | History, thresholds, training sets: daily history (BC), 15-min history (Nooksack), official and station thresholds, upstream links, leakage-safe datasets | Oct 8 AM | Do the labels and features reflect what was knowable at forecast time? |
| 4 | Models, walk-forward evaluation, calibration, 2021/2025 replays; kill-criteria verdict in `evaluation.md` | Oct 8 PM | Does the model beat persistence and trend honestly, and by how many hours at official flood stages? |
| 5 | Live model in the ledger, scored against baselines and NOAA | Oct 9 AM | Is the live model at least as good as the baselines on live data? |
| 6 | Web app ("Working in Public"): map, gauge page with forecast fan, thresholds, official forecast, data-as-of, live scores, ledger verification, attribution, disclaimers | Oct 9, before Build Session 3 (18:00) | Can a farmer understand their risk in 30 seconds without help? |
| 7 | Opt-in alerts: a user sets a level; with their consent, the app calls/texts them and, after they approve, notifies helpers who opted in; consent log, rate limits, replay/demo mode | Oct 9 PM – Oct 10 | Does the right person get the right message at the right time, and only with consent? |
| 8 | Hardening: CI, monitoring and feed-lag alerts, backups, security review, cost guard, registry metadata | Oct 10–11 | Will it keep running unattended through Demo Day? |
| 9 | Demo readiness: replay-at-speed, final numbers, README results, demo runbook, fallback recording, farmer interview findings | Oct 11–12 | Can the value be shown in 4 minutes with real numbers? |
| 10 | Freeze + Demo Day runbook | Oct 13 (freeze at noon) | Nothing changes after noon except the ledger growing |

**Cut order if behind:** precipitation forecasts → calendar holds → non-English voice → challenger models → pooled BC daily model (keep the Nooksack model).

## Key dates

| When (PT) | What |
|---|---|
| Oct 7, 18:00 | Build Session 2. Mentors check the repo ~24 h later |
| Oct 9, 18:00 | Build Session 3 — deployed product others can use |
| Oct 13, 12:00 | Model and code freeze |
| Oct 13, 18:00 | Demo Day, 410 W Georgia St |
