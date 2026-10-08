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
| ECCC Datamart hourly CSVs are ~1 h behind (p50 61 min, p90 91 min, 30 stations sampled); all 429 BC files rewritten at :31 each hour (**corrected in Stage 1:** rewritten every 30 min, at :01 and :31) | `dd.weather.gc.ca/today/hydrometric/csv/BC/hourly/` | Primary live source: poll Datamart hourly files (Stage 1 polls every 5 min) |
| Datamart `daily` files hold 30 days of 5-min data (8,626 rows for 08MH001) | Same tree, `/daily/` | 30-day backfill source; anything older is lost unless archived |
| USGS 15-min data for the Nooksack is ~45 min behind; North Cedarville (12210700) has stage since 2007-10-01, flow since 2004-10-15 | USGS site catalog + IV service | Sub-daily training history covering the 2009, 2021 and 2025 floods |
| Nov 15, 2021 peak at Nooksack River at Everson (12211200): 52,300 cfs at 13:40 PST | USGS IV query | Independent cross-check value for the backfill |
| NOAA NWRFC publishes an official 7-day forecast for Nooksack at North Cedarville (NWPS `NRKW1`), 6-hourly points, plus official flood stages (action 144.8 ft, minor 146.5, moderate 148, major 150) | `api.water.noaa.gov/nwps/v1/gauges/NRKW1` | Official thresholds and an official forecast to score against, live |
| NOAA stage and USGS gage height share a datum (both ~138.0 ft on Oct 7) | Same-time readings | Thresholds apply directly to USGS data |
| The Nooksack overflow at Everson flooded Sumas Prairie in 2021 and Dec 2025 | City of Abbotsford bulletins | The US gauges are core, not optional |

## Facts the supervisor verified during Stage 1 QA (Oct 8, 2026, 00:00–00:20 UTC)

| Finding | Evidence | Consequence |
|---|---|---|
| `today/hydrometric/…` returns 404 for a few minutes after 00:00 UTC; the ECCC run at 00:03:50Z failed and recovered by 00:07Z | `/v1/health` and `ingest_runs` | Stage 2 fix F1: fall back to the dated directory `/YYYYMMDD/WXO-DD/hydrometric/csv/BC/…` |
| The 30-day `daily/` files are written once a day (~08:19Z on Oct 7); for ~8 h after midnight only yesterday's dated `daily/` directory exists | Listings of `today/` and the dated directories | Anything reading `daily/` needs the same fallback |
| Each ECCC refresh rewrites ~570k unchanged rows (≈ 14 GB/day of WAL) | Stage 1 measurements | Stage 2 fix F2 (moved forward from Stage 8) |
| The overflow toward Sumas Prairie (USGS 12211195, Overflow at SR 544) first appeared when North Cedarville stood at ~147.5 ft: 4 h 55 min after it crossed minor stage in Nov 2021 (21:30Z → 02:25Z) and 4 h 30 min after in Dec 2025 (20:15Z → 00:45Z) | Public API queries of the backfilled USGS data | The first piece of demonstrable value: the Build Session 2 demo path. Two events only; Stage 2 recomputes it for every event in the record |
| NOAA can add points to an existing issuance (NRKW1 15:36Z issuance went from 29 to 30 points); the archive keeps the first-fetched value per point | `/v1/official-forecasts/NRKW1` vs api.water.noaa.gov | Correct as built; the ledger must record later-added points too |

## Value realism (what the supervisor will keep honest)

- **Effective lead time = forecast horizon − data latency.** With ~1 h latency, a "6 h" forecast gives ~5 h of real warning. Every forecast stores `data_as_of`; the UI shows it.
- **October may stay dry.** Live exceedance events may not happen before Demo Day. Live proof will rest on level-forecast accuracy (CRPS vs persistence and vs NOAA's official forecast); event proof rests on replays of 2021 and 2025.
- **History is uneven.** BC gauges have only daily history (decades). The Nooksack system has 15-min history since 2007. Sub-daily models are realistic for the Nooksack; BC gauges get a daily model.
- **No archive of past official forecasts was found.** The official-forecast comparison is live-only, from the day archiving starts. Say so.

## Stages

| # | Stage | Target | Value question the supervisor asks |
|---|---|---|---|
| 0 | Environment discovery on the existing VM (worker prompt `prompts/STAGE-00-environment.md`) | Oct 7, ~30 min | Can the worker build and deploy without blocking on access, and without disturbing anything already on the VM? |
| 1 | Foundation + live archive: ingest ECCC Datamart (all BC), USGS Nooksack/Sumas, NOAA official forecasts; raw archive on the VM disk (daily snapshots as the off-machine copy); backfills; minimal public read API | Oct 7, before Build Session 2 (18:00) | Is data that disappears after 30 days now being kept, fresh to ~1 h, and verifiable from outside? |
| 2 | Forecast ledger + baselines + first working app (prompt `prompts/STAGE-02-ledger-app.md`): hourly persistence/trend forecasts, NOAA issuances in a hash-chained append-only ledger anchored hourly to the `ledger` branch, scoring; the Build Session 2 app (Sumas Prairie overflow watch, 2021/2025 replay, snapshot mode); Stage 1 fixes F1–F3 | Oct 8 PM (started 12:30 PT): PR 1 (app + ledger) by ~16:30 PT so it is on `main` before the mentors look; PR 2 (scoring, anchors, verification) after ([addendum 1](prompts/STAGE-02-addendum-1.md)) | Is every forecast fixed in time before the truth arrives, and scored honestly? Can the first user get a useful answer from real data today? |
| 3 | History, thresholds, training sets: daily history (BC), 15-min history (Nooksack), official and station thresholds, upstream links, leakage-safe datasets | Oct 9 AM | Do the labels and features reflect what was knowable at forecast time? |
| 4 | Models, walk-forward evaluation, calibration, 2021/2025 replays; kill-criteria verdict in `evaluation.md` | Oct 9 PM → Oct 10 AM | Does the model beat persistence and trend honestly, and by how many hours at official flood stages? |
| 5 | Live model in the ledger, scored against baselines and NOAA | Oct 10 | Is the live model at least as good as the baselines on live data? |
| 6 | Web app for other users ("Working in Public"), growing the Stage 2 app: map, gauge pages with forecast fan, station thresholds, official forecast, data-as-of, live scores, ledger verification, attribution, disclaimers. For Build Session 3 (Oct 9, 18:00 PT) the deployed Stage 2 app plus Stage 3 thresholds is the product others use | Oct 10 | Can a farmer understand their risk in 30 seconds without help? |
| 7 | Opt-in alerts: a user sets a level; with their consent, the app calls/texts them and, after they approve, notifies helpers who opted in; consent log, rate limits, replay/demo mode | Oct 9 PM – Oct 10 | Does the right person get the right message at the right time, and only with consent? |
| 8 | Hardening: CI, monitoring and feed-lag alerts, backups, security review, cost guard, registry metadata | Oct 10–11 | Will it keep running unattended through Demo Day? |
| 9 | Demo readiness: replay-at-speed, final numbers, README results, demo runbook, fallback recording, farmer interview findings | Oct 11–12 | Can the value be shown in 4 minutes with real numbers? |
| 10 | Freeze + Demo Day runbook | Oct 13 (freeze at noon) | Nothing changes after noon except the ledger growing |

**Cut order if behind:** precipitation forecasts → calendar holds → non-English voice → challenger models → pooled BC daily model (keep the Nooksack model).

## QA log

| Stage | Verdict | Merged | What the supervisor verified independently | Carried forward |
|---|---|---|---|---|
| 0 | PASS | `296bb82` (PR #1) | Environment report vs VM facts; no secrets or internal identifiers in the committed doc | — |
| 1 | PASS | `fe8208f` (PR #2) | Health green for ECCC, USGS, NOAA; 10 of 10 ECCC rows equal the live files; NOAA NRKW1 issuance equal point for point (30/30); Everson 52,300 cfs and the 2021/2025 peaks present; sentinel and CORS edge cases; `ruff` clean; `pytest` 44 passed including the 18 DB tests (run against `timescale/timescaledb:2.30.2-pg16`); stage doc grew in 11/11 commits | F1 rollover fallback, F2 unchanged-row rewrites, F3 publish the URL → Stage 2. Human: VM reboot test (AC-9), USGS API key, snapshot schedule |

## Build Session 2 requirements (checklist) and where they are met

| Requirement | Where |
|---|---|
| Brief written in the author's own words before using an LLM | Not met as written: Pranay asked the supervisor to draft it. [`brief.md`](../../brief.md) is AI-drafted and labelled so |
| Demo path Problem → Action → Visible useful result, with value the app already creates | Stage 2 app: Sumas Prairie overflow watch + 2021/2025 replay |
| Real, permitted data; results supported by it | ECCC (OGL-Canada), USGS and NOAA (public domain); records in `data-contract.md` |
| Working local app, reproducible from the repo | Stage 2 snapshot mode (`python3 -m http.server -d web 8080`) and `docker compose up` |
| README: idea and choices, data, run locally, demo path, what works now and what remains | Stage 2, README "Build Session 2 — working app" |

## Human tasks

| Task | Why | Status |
|---|---|---|
| `brief.md` | Build Session 2 ownership check | Pranay asked the supervisor to write it (Oct 8). Committed to `main`, labelled as AI-drafted |
| Fine-grained GitHub token → `LEDGER_GITHUB_TOKEN` in `.env` | Hourly ledger anchors | done (Oct 8) |
| USGS API key → `USGS_API_KEY` in `.env` | Keyless USGS quota (1,000 requests/h) | done (Oct 8); ingest must be recreated to pick it up |
| Daily snapshot schedule on the boot disk | Off-machine copy of the archive and database | **Declined by the owner (Oct 8). Accepted risk:** a disk loss would lose the raw archive and database. Mitigation: the ledger entries themselves are published hourly to the `ledger` branch (Stage 2 addendum), so the live track record survives |
| VM reboot test (Stage 1 AC-9) | Unattended recovery | Moved to the worker: last step of Stage 2, after the PR is open; the supervisor verifies recovery from outside |
| Farmer outreach | Interviews for Demo Day | in progress |

## Key dates

| When (PT) | What |
|---|---|
| Oct 7, 18:00 | Build Session 2. Mentors check the repo ~24 h later |
| Oct 9, 18:00 | Build Session 3 — deployed product others can use |
| Oct 13, 12:00 | Model and code freeze |
| Oct 13, 18:00 | Demo Day, 410 W Georgia St |
