# Stage 03 — Working in public, fair scoring, history and training sets

> Living document. Written while the stage is built, committed with the code. Newest work-log entries at the bottom.

| | |
|---|---|
| Branch | `stage-03-public` (PR 1), then `stage-03-history` from the merged `main` (PR 2) |
| Started | 2026-10-09 12:42 PT (19:42 UTC) |
| Finished | (fill at end) |
| Prompt | `docs/build/prompts/STAGE-03-public-history.md` |
| Status | in progress (part 1) |

## Goal

Tonight, people other than the author open FloodLead for the first time (Build Session 3, Oct 10 01:00 UTC). In 30 seconds they must be able to:
- find their gauge;
- see how close it is to a level that matters;
- see an honest track record;
- tell us what they think, without giving us personal data.

Honesty comes first. The current skill numbers are inflated by an approximate CRPS, so the fair CRPS is fixed before any skill number is shown again. Overnight (part 2), the data for the Stage 4 model is built:
- ECCC daily history;
- rainfall, observed and as-issued forecasts;
- the official NWS flood warnings that were actually issued;
- leakage-safe training sets with an event catalogue.

A pre-registered evaluation protocol is frozen before any model is trained. Stage 4 is then judged on held-out floods against persistence, the 3 h trend, the gauge-watch rule and the real NWS warnings, whatever the result.

## Inputs read

- `CLAUDE.md`, `AGENTS.md`:
  - every new source needs a usage-rights record before code depends on it;
  - no leakage: precipitation features use forecasts as issued;
  - personal data is encrypted and never in logs, the ledger or fixtures;
  - no performance claims without a run ID.
- `docs/build/prompts/STAGE-03-public-history.md`: two PRs (part 1 by ~23:30 UTC), F1–F5, part 1 items 1–7, part 2 items 1–7, 12 ACs. Start the part-2 downloads first. No reboot in this stage.
- `docs/build/PLAN.md`:
  - QA log: Stage 2 part 2 PASS (`a4b5b29`). The supervisor recomputed 19,677 entries and 12 USGS score groups.
  - Facts verified on Oct 9: IEM keeps the archived NRKW1 warnings for 2021 and 2025; the official lead was ≈ 6 h in Dec 2025 and ≈ 0 h in Nov 2021; live baselines do not beat pure persistence on median accuracy.
  - Human tasks: rainfall sources and the IEM archive were approved on Oct 9 ("approve all").
- `docs/stages/STAGE-02-ledger-app.md`:
  - D-02.13 (the quantile-score CRPS, its 19 % bias);
  - D-02.17 (`persistence-naive`);
  - D-02.18 (NOAA's 7-day cut);
  - open issues: no skill claim yet; step-change and tidal flags needed; DB memory (1,150 chunks in 2.5 GiB); scorer runtime growth.
- `evaluation.md` line 56 says the quantile score "ranks models". That is wrong for probabilistic-vs-point comparisons (the supervisor's F1): the score favours a spread forecast over a point forecast by ≈ 19 %.
- `data-contract.md`: record 2 (ECCC historical hydrometric, OGC API + HYDAT, OGL-Canada) already covers the daily history and annual peaks. No record yet for ECCC climate, NCEI, SNOTEL, Open-Meteo or IEM.
- **State at start (19:42 UTC):**
  - all 4 services up 16 h (since the 03:50Z reboot);
  - health green (issuer, scorer, anchor);
  - disk 21.7 % used.

## Plan

Part 1 (PR 1, `stage-03-public`, ready by ~23:30 UTC). Lean, in the prompt's priority order:

0. **Start the part-2 downloads first.**
   - Check each new source's terms; write their usage-rights records in `data-contract.md`.
   - Write one paced, resumable download command per source, as `floodlead history <source>`: every raw payload goes into the raw archive, with a manifest table recording what was fetched.
   - Run them as one-off `backfill` compose services (`restart: "no"`), recording start time, rate and finish time.
   - Parsing into tables happens in part 2.
1. **F1 fair CRPS.**
   - Rebuild a piecewise-linear CDF from the stored quantiles, with a documented tail rule, and integrate it exactly.
   - Bias table on synthetic forecasts (normal, log-normal, under- and over-dispersed).
   - Keep the quantile score as a secondary column; add MAE-of-median skill vs naive; add naive to `/v1/scores/official`.
   - Recompute all stored scores; correct `evaluation.md`; 19 quantiles for future models.
2. **Feedback.**
   - `POST /v1/feedback`, stored append-only with the text encrypted (key in `.env`), with a rate limit and size limits.
   - The in-app box, a GitHub issue template, and `floodlead feedback list`.
   - Health shows counts only.
3. **Fraser Valley gauges** on the home page: latest level, data age, and the position against the typical yearly peak.
4. **Typical yearly peak.**
   - Median annual instantaneous peak level, from ECCC `hydrometric-annual-peaks`, with datum checks.
   - Stored with provenance, and put in the ledger (a new model card) before first use.
5. **Help panel and `#/track-record`.** Fair skill vs pure persistence with n, stations, days and the run ID, plus honest framing.
6. **README** "Build Session 3 — working in public".
7. **F4 replay refresh-ahead, F3 `statement_timeout`, F2 reboot evidence.**

Then mark PR 1 ready and print the STAGE REPORT (part 1).

Part 2 (PR 2, `stage-03-history`, Oct 10 ~12:00 UTC):
- parse the downloads into new tables;
- NWS warning timelines;
- upstream links;
- the training sets (`honest` and `oracle`);
- the event catalogue;
- the frozen `docs/evaluation-protocol.md` (after the supervisor's addendum).

## Decisions

### D-03.1 — History downloads: archive raw first, parse later; one paced, resumable task list per source

- **Context:** Part 2 needs decades of ECCC daily data, rainfall and the NWS warning archive. The prompt asks to start the downloads at the very beginning, while part 1 is built, as one-off compose services that are paced and resumable.
- **Options considered:**
  - (a) download and parse in one step into tables;
  - (b) download every payload unchanged into the raw archive, with a manifest table, and parse later from the archive.
- **Choice:** (b).
  - `floodlead history download <source…>` runs a fixed task list per source. Tasks are one station-year, one product-year, or one OGC page; follow-up pages are queued from each page's `numberReturned`.
  - Each response goes through `archive.store` (gzip, sha256, `raw_objects`) and a row in a new `history_downloads` table, keyed by `(source, key)`. Tasks already `ok` or `empty` are skipped, so a run can stop and restart at any time.
  - Pacing per source, well under the published limits:
    - ECCC OGC API: 1 request/s;
    - IEM: 1 request / 2 s;
    - SNOTEL: 1 request / 2 s;
    - NCEI: 1 request / 3 s;
    - Open-Meteo: 1 request / 30 s, ≈ 52 calls/min against a limit of 600 (each point-year counts as ≈ 26 calls).
  - Runs as `docker compose run -d --name hist-… backfill floodlead history download …`. The `backfill` service has `restart: "no"`.
- **Why:**
  - The downloads start within the first hour and need no parser decisions yet.
  - Parsing bugs can be fixed and re-run without refetching.
  - The raw payloads stay as the evidence for every parsed number, as in Stage 1.
- **Reversibility / cost:**
  - Downloads are additive and idempotent.
  - Archive cost: about 2 MB per OGC page or station-year (uncompressed), compressed on disk.
- **Follow-ups:** part 2 writes the parsers into new history tables (never `observations`, F3).

### D-03.2 — Usage-rights records for the new sources, checked the same day

- **Context:** AGENTS.md requires a record before code depends on a source. The prompt adds: check the current terms yourself, and record the URL and the date.
- **Choice:** five records in `data-contract.md`, each naming the page fetched on 2026-10-09:
  - ECCC climate-hourly: ECCC Data Servers End-use Licence v2.1.1 on this route; OGL-Canada on open.canada.ca.
  - NCEI Global Hourly: **US stations only**. The readme states that non-US ISD data fall under WMO Resolution 40, so Canadian stations come from ECCC directly.
  - NRCS SNOTEL: a US Government work. The NRCS policy pages returned 404 that day; the record says so.
  - Open-Meteo: CC BY 4.0, and the free API is **non-commercial**. A commercial FloodLead needs a paid plan or a swap. Marked 🟡.
  - IEM: "in the public domain and may be used freely by anyone for any lawful purpose".
- **Why:** each record shows exactly what was checked, and what could not be checked.
- **Reversibility / cost:** the Open-Meteo dependency is the only non-commercial one. It stays a training input, and its replacement path is written down.
- **Follow-ups:** measure each source's publication latency (part 2, item 2).

### D-03.3 — Which stations and points the downloads cover

- **Context:** the task lists need concrete stations and points.
- **Probes (19:55–20:05Z):**
  - **ECCC annual peaks, BC:** 37,806 rows (level and flow, maximum and minimum).
  - **ECCC daily means:** for example 08MH029 has 30,367 days, ending 2024-12-31 (approved HYDAT).
  - **ECCC hourly climate stations** in the bbox −122.8 … −121.2, 48.9 … 49.5:
    - Abbotsford A (3 IDs, 1953 → now);
    - Hope (4 IDs);
    - Pitt Meadows CS;
    - White Rock CS.
  - **ISD stations** within 48.6–49.1N, −122.8 … −121.3: KBLI is the only US one with long history.
  - **SNOTEL in the Nooksack:**
    - Wells Creek 909 (NF, 1995);
    - MF Nooksack 1011 (2002);
    - Elbow Lake 910 (SF, 1995).
    - Hourly data were present on 2021-11-13.
  - **Open-Meteo:**
    - reanalysis returned data;
    - historical forecast: no data on 2016-01-10, data on 2021-03-20 and 2022-06-01;
    - previous runs: `previous_day1/2` empty on 2023-06-01, present on 2024-02-01.
- **Choice:**
  - all BC real-time ECCC stations for daily means; all BC annual peaks;
  - the 8 climate IDs listed;
  - KBLI;
  - the 3 SNOTEL sites;
  - 8 basin points (4 Nooksack, 4 Fraser Valley; `history/tasks.py`):
    - Open-Meteo reanalysis from 2004;
    - historical forecast from 2020;
    - previous runs from 2023.
  - The years before each start date are requested anyway and recorded as found (empty or null), which also measures the start dates.
- **Reversibility / cost:** adding a point or station later is one more task; nothing is lost.

### D-03.4 — Fair CRPS: rebuild the CDF from the quantiles, exponential tails, exact integral (F1)

- **Context:** the quantile score is exact for a point forecast, but about 19 % low for a spread forecast. So every CRPSS against `persistence-naive` was inflated (the supervisor's F1). The live ECCC h1 CRPSS of +0.30 sat next to a median that was worse than naive.
- **Options considered:**
  - (a) a piecewise-linear CDF between quantiles, with these tail rules:
    - point masses at the 0.05/0.95 quantiles;
    - linear extension of the edge slope down to F = 0 and up to 1;
    - exponential tails with the edge segment's density;
  - (b) fit a parametric distribution (normal or skew-normal) to the quantiles;
  - (c) keep the quantile score and rescale it.
- **Measured** (prototype, 3,000 truth draws per case, 7 levels; bias against the exact CRPS of the true forecast distribution):

  | Case | exp tails | linear tails | point masses | quantile score |
  |---|---|---|---|---|
  | calibrated normal | +0.0 % | +0.1 % | +0.2 % | −19.4 % |
  | log-normal (s = 0.5) | +0.1 % | +0.2 % | +0.3 % | −18.0 % |
  | under-dispersed (sd 0.5 vs 1) | −0.2 % | +0.2 % | +0.7 % | −14.5 % |
  | over-dispersed (sd 2 vs 1) | +1.2 % | +1.2 % | +1.0 % | −12.6 % |

  With 19 levels, all three tail rules are within ±0.4 %.
- **Choice:** (a) with **exponential tails**:
  - `F(x) = τ₁·exp(λ(x − q₁))` below q₁, with `λ = f₁/τ₁`, and symmetrically above q_K;
  - every piece is integrated in closed form (`src/floodlead/crps.py`);
  - a zero-width edge segment becomes a point mass, so a point forecast gives exactly |y − q|.
- **Why:**
  - the smallest bias in the skewed and under-dispersed cases;
  - exact and deterministic: no sampling, and no distribution family assumed (b would favour models whose shape matches the family);
  - (c) cannot fix the point-vs-spread asymmetry, which is the actual problem.
- **Kept:**
  - `crps_qs` (the quantile score) as a secondary column, in `/v1/scores/summary` as `mean_crps_qs_m`;
  - MAE-of-median skill against both references (`mae_skill`, `paired_mae`);
  - `persistence-naive` in `/v1/scores/official` (naive rows now carry their persistence-v1 row's NOAA point).
- **Reversibility / cost:** scores are derived. `floodlead score --recompute-crps` rebuilds `crps` and `crps_qs` from the ledger and the stored truth, idempotently (tested).
- **Follow-ups:** future model versions store 19 quantiles (evaluation.md).

### D-03.5 — Migration 007 (`crps_qs` column) after a dump of the score tables

- **Context:** F1 adds a column to two existing tables and recreates the `all_scores` view. CLAUDE.md requires a `pg_dump` before any migration that touches existing tables.
- **Choice:**
  - `pg_dump -Fc` of the 4 score tables (`forecast_scores`, `forecast_scores_naive`, `score_summaries`, `scorer_runs`) to `/srv/floodlead/backups/pre-007-score-tables-20261009T1955Z.dump`: 2,501,219 B, mode 0440, `pg_restore --list` shows 4 TABLE DATA entries.
  - Not the whole database (4.8 GB): the migration touches only these tables, and they are derived data.
  - Then `ALTER TABLE … ADD COLUMN crps_qs`, and `CREATE OR REPLACE VIEW all_scores`. The view was created with `SELECT *` and would otherwise miss the new column.
- **Reversibility / cost:**
  - Adding a nullable column is instant.
  - The values are recomputed from the ledger, so the dump is the belt-and-braces copy.

## Work log

- `12:42` — `git checkout main && git pull` → `bd3d092`. Branch `stage-03-public`. Read the prompt and the inputs above.
- `12:44` — **F2 reboot evidence** (the reboot was run at the end of Stage 2):
  ```
  $ uptime -s
  2026-10-09 03:50:03
  $ last -x reboot | head -3
  reboot   system boot  7.0.0-1013-gcp   Fri Oct  9 03:50   still running
  reboot   system boot  7.0.0-1013-gcp   Wed Oct  7 20:28 - 03:49 (1+07:21)
  reboot   system boot  7.0.0-1011-gcp   Mon Oct  5 23:59 - 20:27 (1+20:27)
  $ docker ps --format '{{.Names}} {{.Status}}'
  floodlead-api-1 Up 16 hours (healthy)
  floodlead-ingest-1 Up 16 hours
  floodlead-caddy-1 Up 16 hours
  floodlead-db-1 Up 16 hours (healthy)
  ```
  - The VM booted at 03:50:03Z, and all four containers came back on their own (`restart: unless-stopped`).
  - The supervisor's QA found 23 consecutive hourly issuances with 0 gaps across the reboot, so the 04:00Z base time was issued on time.

- `12:44–12:49` — Draft PR #5 opened. Terms pages fetched and the probes above run (D-03.2, D-03.3).
  - Wrote `migrations/006_history_downloads.sql` (a new table only), `src/floodlead/history/{download,tasks,cli}.py`, `archive.read`, and the five records in `data-contract.md` (inputs 8–11).
  - Task counts:
    - `eccc-peaks` 1+ pages;
    - `eccc-daily` 1 page per station, + follow-ups;
    - `eccc-climate` 122;
    - `iem-nws` 46;
    - `ncei` 23;
    - `snotel` 23;
    - `openmeteo-archive` 184, `-histfc` 56, `-prevruns` 32 (≈ 7,100 Open-Meteo calls in total).

- `12:50` — **Downloads started** (`docker compose run -d --name hist-{eccc,us,openmeteo} backfill floodlead history download …`, image `7e91866`), after `floodlead migrate` → `006_history_downloads.sql`. 19:50:03Z.
  - `iem-nws` finished at 19:51:39Z: 46 requests, 13,034,726 B, 0 errors.
  - `eccc-peaks`: 4 pages (37,806 rows), 21.9 MB.
- `12:51–12:55` — **F1 fair CRPS** (D-03.4).
  - `src/floodlead/crps.py` and `tests/test_crps.py`: point forecast = AE; tied edges; equality with a numerical integral of the same CDF; bias tables.
  - Scorer: `crps` is now fair, `crps_qs` is kept, plus MAE skill; naive rows carry NOAA points; `recompute_crps`.
  - `pytest -q -s tests/test_crps.py`:
    ```
    7 levels  calibrated normal                fair +0.0 %   quantile score -19.3 %
    7 levels  log-normal (s=0.5)               fair +0.0 %   quantile score -18.2 %
    7 levels  under-dispersed (sd 0.5 vs 1)    fair -0.2 %   quantile score -14.2 %
    7 levels  over-dispersed (sd 2 vs 1)       fair +1.2 %   quantile score -12.9 %
    19 levels (all four cases)                 fair +0.0 … +0.1 %
    ```
  - Full suite → **102 passed**, 4 deselected. Test fixtures now truncate `history_downloads` with `raw_objects` (new FK).
  - `evaluation.md` corrected: the "ranks models" sentence is withdrawn.
- `12:55` — Score tables dumped before migration 007 (D-03.5).

- `12:56` — Migration 007 applied on production (`floodlead migrate` → `007_crps_qs.sql`).
  - **First recompute failed and rolled back:** `psycopg.ProgrammingError: can't change 'autocommit' now: connection in transaction status INTRANS`, after 37.2 s. The chunk updates had run inside the first statement's implicit transaction, so the error rolled all of them back. Nothing changed on production.
  - The test had passed only because the pooled connection was reused from an earlier `scorer.run`, which leaves autocommit on.
  - Fix: autocommit is set before the first statement. The test now uses a fresh pool, as production does: **it fails without the fix and passes with it**.

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

- (filled at end of each part)
