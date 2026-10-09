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

### D-03.6 — Feedback: anonymous, text encrypted at rest, append-only; rate limits keyed on the real client IP

- **Context:** part 1 item 2. Build Session 3 visitors must be able to tell us what they think. AGENTS.md says personal data is encrypted, kept in Canada, and never in the ledger, logs or fixtures.
- **Choice:**
  - `POST /v1/feedback` takes `{route, station_id, useful, text ≤ 1,000 chars, app_version}`. Any other field is rejected, including names and emails.
    - Body ≤ 4,096 B, else 413. Control characters are stripped.
    - Response `202 {"status":"received"}`: the text is never echoed or rendered.
  - Table `feedback` (migration 008):
    - the text is a **Fernet token** (AES-128-CBC + HMAC-SHA256), with the key `FEEDBACK_KEY` in `.env`, generated on the VM and never printed;
    - `key_id` = the first 8 hex of sha256(key), for rotation;
    - **no IP address, name, email or phone is stored**;
    - UPDATE, DELETE and TRUNCATE are rejected by triggers.
  - Rate limits, in memory only:
    - per client IP: 5 per 10 min and 20 per day;
    - 300 per hour from everyone together.
  - Health shows counts only (`feedback.total`, `last_24h`, `yes`, `no`).
  - `floodlead feedback list` on the VM is the only reader. It escapes control characters, so no terminal sequences reach the output.
  - A GitHub issue form (`.github/ISSUE_TEMPLATE/feedback.yml`) for people who want a reply. It warns that issues are public.
- **Found and fixed on the way:** the general API rate limiter (Stage 1, 120/min) keyed on `request.client.host`. Behind Caddy that is Caddy's address, so **every visitor shared one bucket**. A dozen people at Build Session 3 could have exhausted it.
  - Both limiters now use `client_ip()`: X-Forwarded-For from a private-network peer. Caddy sets that header to the client address and ignores one sent by untrusted clients.
  - The test client stands in for Caddy in `tests/test_feedback.py`.
- **Why:** the minimum data that makes feedback useful, with no personal data by design. Encryption covers a visitor who types personal details anyway.
- **Reversibility / cost:**
  - `cryptography` is a new dependency (50.0.2).
  - Losing `FEEDBACK_KEY` makes the stored text unreadable (stated in the open issues). It lives only in `.env`, as the other secrets do.
- **Follow-ups:** retention period for feedback text (Stage 7, with the privacy policy).

### D-03.7 — Typical yearly peak: median annual instantaneous maximum level over 2005–2024, with a datum check

- **Context:** part 1 item 4. BC gauges have no official flood stages in our data. People need a level that matters, and it must be honest about what it is.
- **Choice (`src/floodlead/typical_peaks.py`, method `typical-peak-v1`):**
  - **Value:** the median of the annual instantaneous maximum *water level* (ECCC `hydrometric-annual-peaks`, HYDAT) over 2005–2024. Approved HYDAT ends in 2024, so this is the last 20 years.
    - At least 10 years are required.
    - Years marked "Ice Conditions" are left out.
    - The median is reached or exceeded in about half of years. That is the label's claim, and nothing stronger.
  - **Datum check:** a datum change makes old peaks meaningless against today's levels. Today's 30-day median live level (constant time bounds on `observations`) is compared with the daily mean levels (`eccc_daily`) for the same calendar days (Sep 10 – Oct 9) in the last 5 years that have them.
    - **Rejected** if the live median lies outside that range by more than max(0.5 m, half the range).
    - **Flagged** if there is no live level or no same-season history to check against, or if the level already reached the value in the last 30 days.
  - **Stored** in `typical_peaks` with status, n, years, the reason and the checks (`jsonb`). This is apart from NOAA's official thresholds.
- **Result (20:20Z):** 433 BC stations with level → **302 ok, 8 flagged, 1 rejected, 122 insufficient** (fewer than 10 years).
  - Flag reasons:
    - 6 reached the value in the last 30 days;
    - 1 had no same-season daily history;
    - 1 had no live level.
  - Rejected: one station, whose 30-day median of 1.274 m lies outside its same-season range.
  - All 7 Fraser Valley gauges are `ok` (table in the work log).
- **Why the median of annual maxima:** a number that is directly verifiable from public ECCC data, needs no distribution fit, and fits "reached in about half of years" exactly.
  - A 2-year return level from a fitted GEV would be close, but adds a model to explain.
  - A percentile of daily means would understate instantaneous peaks.
- **Reversibility / cost:**
  - A new method version can be added next to `typical-peak-v1`; the table is keyed by method.
  - The datum rule can miss a small datum change (under 0.5 m) and can flag a real but unusual season. Both are stated in the app.
- **Follow-ups:** part 2 uses the same table for the BC event catalogue ("crossings of the typical yearly peak").

### D-03.8 — The thresholds enter the ledger through new model cards, in the same issuance, before first use

- **Context:** forecasts that include the typical-peak threshold must be verifiable. Its values and provenance must be in the ledger before the first forecast that uses them, without changing any existing card or entry.
- **Options considered:**
  - (a) new model cards for `persistence-v1` and `trend3h-v1` whose `params.typical_peak` holds the method, source, period, rules and every `ok` value;
  - (b) a new entry type (for example `threshold_set`), which needs a schema change to the ledger's `entry_type` CHECK and verifier updates;
  - (c) new model names (v2), which would break the continuity of the live scores.
- **Choice:** (a). The issuer already appends a superseding card whenever a model's `params_hash` changes, in the same transaction and at lower seq than that issuance's forecasts.
  - Each card says `change: "typical yearly peak thresholds added or updated (params.typical_peak); forecast method and other parameters unchanged"` and `supersedes_seq`.
  - Each forecast for a station with an `ok` value gets a threshold `{"key": "typical:peak", "kind": "typical", "level_m", "label", "source": "typical-peak-v1 in the model card params (typical_peak)"}`, plus `p_exceed["typical:peak"]` at every horizon.
  - `flagged` and `rejected` values are shown in the app with their reason, but not used in forecasts.
- **Why:**
  - no ledger schema change and no verifier change;
  - the old cards are untouched (tested: the earlier cards are byte-identical after the new ones are appended);
  - "before first use" holds by construction, and is tested (card seq < every forecast seq of that issuance).
- **Reversibility / cost:**
  - Each card carries all ~300 values, about 20 kB of canonical text. It is written only when the values change.
  - Recomputing the table with different values would append new cards, which is visible and dated.
- **Follow-ups:** the scorer already scores any threshold, so Brier for `typical:peak` appears once events settle.

### D-03.9 — F4: the replay is refreshed in the background before its cache expires

- **Context:** `/v1/replay/overflow` takes ~9 s cold. When its 1 h cache expired, one visitor paid that cost (one supervisor page load took 16.5 s).
- **Choice:** the API's warm-up thread now loops. It recomputes the replay at start and every 50 min (`_REPLAY_REFRESH_S = 3000`), 10 min before the 1 h TTL, and swaps the cached copy in place. A failed refresh is logged, and the previous copy keeps serving until its TTL.
- **Why:** the simplest change that removes the cold path for visitors.
- **Reversibility / cost:** one computation every 50 min (about 9 s of database time).

### D-03.10 — F3: statement timeouts as a database default, and a guarded shell for ad-hoc work

- **Context:** the 01:38Z OOM was an unbounded ad-hoc query.
- **Choice:**
  - Migration 010 sets, for the current database (by name, so the disposable test database never touches production), `statement_timeout = 15min` and `idle_in_transaction_session_timeout = 30min` for every new session that does not set its own.
  - `scripts/dbshell` runs psql with `statement_timeout = 5min` and `work_mem = 8MB`; checked with `SHOW` → `5min`, `8MB`.
  - Long jobs set their own: the recompute 15 min, the typical-peak computation 10 min. `pg_dump` sets 0 itself.
  - History data went into new tables (`eccc_annual_peaks`, `eccc_daily`, `typical_peaks`), never into `observations`.
  - Raising `timescaledb.max_background_workers` and compressing old chunks were **skipped** in part 1 (time). They stay open issues, to be done with a dump first if they are done at all.
- **Reversibility / cost:** one `ALTER DATABASE … RESET` undoes it. The 15-min backstop is well above every scheduled job (the longest is the issuance at about 77 s).

### D-03.11 — The static app is deployed into a stable directory, not bind-mounted from the git working tree

- **Context (an outage).** At 20:26Z the public app answered **404 for `/` and every static file**. The API was fine. Inside the Caddy container, `/srv/web` was empty.
  - Caddy bind-mounted `./web` from the repository, and the host `web/` directory had been replaced: its files have mtime 19:41Z, when I ran `git checkout main && git pull` to start this stage. Caddy kept serving the deleted, empty directory.
  - **Probable outage: ~19:41Z to 20:26:43Z (~45 min), caused by the worker.** Caddy's logs went with the recreated container, so the start time rests on the file mtimes, not on logs.
  - The same mount also meant that **any edit to `web/` went live before it was committed**. That happened with the frontend agent's edits (work log `13:23`).
- **Choice:**
  - Caddy serves `${WEB_DIR:-/srv/floodlead/web}`.
  - `scripts/deploy_web.sh` deploys `web/` there with `rsync -a --delete`, which updates files in place and keeps the directory, and writes `.deployed-commit`. The file is public and shows which commit the site runs.
  - Web changes now go live only by an explicit deploy from a branch with an open PR, like the code.
- **Why:** it fixes the root cause (a directory bind mount on a path that git may replace), and it brings the static app under the deploy-only-from-an-open-PR rule.
- **Reversibility / cost:** one extra command per web deploy. Reverting is one line in `compose.yaml`.
- **Follow-ups:** the check that would have caught this is a public `GET /` in health monitoring. Proposed for Stage 5 (open issues).

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

- `12:58–13:04` — **Feedback** (D-03.6):
  - migration 008;
  - `src/floodlead/feedback.py`, `POST /v1/feedback`, health counts, `floodlead feedback list`, the issue form;
  - `tests/test_feedback.py`: validation, encryption round trip and wrong key, per-IP and global limits, end to end (202, not echoed, encrypted at rest, decrypted only by the reader, absent from captured logs and output, health counts, append-only), 413/400/429.
  - **The test caught a bug in my first version:** health folds every job block into the overall status, and the feedback block had none, so health would have returned 500. Feedback counts now sit outside the status roll-up.
  - `pytest -q` → **107 passed**.

- `13:05` — Feedback deployed: `floodlead migrate` → `008_feedback.sql`; the API recreated with `FEEDBACK_KEY` (`.env`, generated on the VM, not printed).
  - Public checks:
    - `POST {}` → 400;
    - a synthetic smoke test (`"Worker smoke test after deploy (synthetic, no personal data)."`) → 202 `{"status":"received"}`;
    - `floodlead feedback list` → `#1 2026-10-09 20:05Z useful=yes route=#/ … 1 item(s)`;
    - health `feedback: {counts_only: true, total: 0 → 1}`.
- `13:05–13:15` — Typical yearly peaks (D-03.7), issuer thresholds through new cards (D-03.8), `/v1/gauges/fraser-valley`, `/v1/track-record`, F4 (D-03.9), F3 (D-03.10).
  - New tests:
    - `tests/test_typical_peaks.py` (5): the median and the ice rule, ok, insufficient, the datum shift rejected (with tolerance edges), flags;
    - `test_typical_peaks_enter_the_ledger_in_new_cards_before_first_use`;
    - contract tests for both endpoints.
  - `pytest -q` → **115 passed**, 4 deselected.
- `13:12–13:22` — **History loaded, peaks computed, deployed** (`8e48476`):
  - `floodlead migrate` → `009_history_tables.sql`, `010_statement_timeouts.sql`;
  - `floodlead history load peaks` → **37,789 rows** in 37.3 s (17 of 37,806 features have no value or date);
  - `floodlead history load daily` → **448 stations, 7,825,554 daily rows** in 525.6 s (peak RSS 52 MB);
  - `floodlead history typical-peaks` → `{'stations': 433, 'counts': {'ok': 302, 'insufficient': 122, 'flagged': 8, 'rejected': 1}}` in 24.3 s.
  - Fraser Valley gauges (`/v1/gauges/fraser-valley` after the deploy at 20:22Z):

    | Gauge | Level now (m) | Age (min) | Typical yearly peak (m) | n (years) | Below peak (m) |
    |---|---|---|---|---|---|
    | Sumas R. near Huntingdon (08MH029) | 1.266 | 48 | 3.397 | 12 (2013–2024) | 2.131 |
    | Chilliwack R. at Vedder Crossing (08MH001) | 1.528 | 63 | 3.307 | 14 (2011–2024) | 1.779 |
    | Chilliwack R. above Slesse Ck (08MH103) | 0.558 | 78 | 2.817 | 14 (2011–2024) | 2.259 |
    | Fraser R. at Hope (08MF005) | 3.600 | 73 | 8.903 | 20 (2005–2024) | 5.303 |
    | Fraser R. at Mission (08MH024), tidal | 0.975 | 73 | 5.562 | 20 (2005–2024) | 4.587 |
    | Nicomekl R. at 203 St (08MH155) | 1.006 | 93 | 3.971 | 14 (2011–2024) | 2.965 |
    | Coquihalla R. below Needle Ck (08MF062) | 1.817 | 48 | 2.958 | 13 (2011–2024) | 1.141 |

  - `/v1/track-record` → 21,341 forecasts in 25 issuances, 0 gaps, 20 skill rows, 6 NOAA matched pairs; 0 official and 0 typical-peak crossings in the window.
  - Its statements are generated from the numbers. Example: "Lower median error (MAE) than pure persistence only at: persistence-v1 USGS 1 h (+4.5 %, n 200); … 3 h (+2.2 %, n 180); … 6 h (+3.9 %, n 150). Everywhere else pure persistence is as good or better."
- **Download progress** (`history_downloads`):
  - **iem-nws:** 46 ok, 13.0 MB, 19:50:08 → 19:51:39Z.
  - **snotel:** 23 ok, 85 MB, done 19:54:59Z.
  - **ncei:** 22 ok + 1 empty (2026 not yet available), 183 MB, done 19:58:52Z.
  - **eccc-peaks:** 4 pages, 21 MB.
  - **eccc-daily:** 1,026 ok + 4 empty, done 20:09:17Z.
  - **eccc-climate:** 121 ok + 1 empty, done 20:11:27Z.
  - **openmeteo:** still running; paced at 30 s per point-year (≈ 2.3 h).

- `13:23` — **Frontend** (a background agent briefed with the API contracts above; its files reviewed by the worker): `web/app.js`, `index.html`, `style.css`, `README.md`, `scripts/screenshots.cjs` (445 lines added, 15 removed).
  - **Feedback box:** the last card on every route, Yes/No plus text with a live count, the privacy sentence, `POST /v1/feedback`, messages for 202/400/413/429/offline, and the GitHub link.
  - **"Fraser Valley gauges":** a card on `#/` after the ledger panel, with a jump button in the hero.
  - **"How to read this":** a `<details>` panel in `index.html` under the header, on every route.
  - **`#/track-record`:** the statements first, then forecasts and the chain head and anchor, verify commands, one table per source, and the NOAA pair count.
  - Worker review:
    - no `innerHTML`, `eval` or inline styles or handlers added;
    - user text is never rendered;
    - the help text's colour claims match the chart (`COLORS.noaa #1f5fbf` blue, `COLORS.fl #5d7f78` grey-green).
  - `tests/test_web.py` gains the two new snapshot slugs → 18 passed.
  - **Deviation:** Caddy serves `./web` from this working tree, so the agent's edits were live on the public site while it worked (about 20 minutes) and before this commit put them in PR #5 (fixed by D-03.11). All the backend code they call was already in PR #5 and deployed.

- `13:24–13:27` — **Public app outage found and fixed (D-03.11).**
  - A headless check of `#/` and `#/track-record` showed an empty `#app` and 404s. `curl` gave `/ 404`, `app.js 404`, `style.css 404`. `docker compose exec caddy ls -la /srv/web` showed `total 0`, a deleted directory.
  - Fix:
    - `sudo mkdir /srv/floodlead/web`;
    - `scripts/deploy_web.sh` (`rsync -a --delete`);
    - `compose.yaml` caddy volume `${WEB_DIR:-/srv/floodlead/web}:/srv/web:ro`;
    - `docker compose up -d caddy`.
  - Back at **20:26:43Z**: `/ 200`, `/app.js 200`, `/style.css 200`, `/.deployed-commit 200` (fb18035).
- `13:27` — **AC-2, feedback from the app on the public URL:** `scripts/feedback_e2e.cjs` (headless Chromium, 375 px, `#/track-record`) clicked Yes, typed a synthetic sentence and submitted.
  - Result: `{"http_status":202,"status_text":"Thank you. Your feedback was received.","page_errors":[]}`.
  - Screenshots `img/stage-03/feedback-before-submit-375.png` and `feedback-after-submit-375.png`.
  - Read back on the VM:
    ```
    $ floodlead feedback list
    #1 2026-10-09 20:05Z useful=yes route=#/ station=- v=stage-03
        Worker smoke test after deploy (synthetic, no personal data).
    #2 2026-10-09 20:27Z useful=yes route=#/track-record station=- v=stage-03
        Synthetic end-to-end test by the build worker (no personal data).
    2 item(s)
    ```
- `13:28` — **AC-5, screenshots** (`scripts/screenshots.cjs`, zenika/alpine-chrome@sha256:ee10e242…, public URL, 64 s).
  - `layout-check.txt`: **scrollWidth = viewport on every page** (`#/`, `#/` with the help panel open, `#/stations`, two station pages, `#/track-record`) at 1280 and 375 px.
  - `page errors (all pages): 0; with navigator.language=en-US@posix: 0`.
  - The files are in `img/stage-03/`: track record, Fraser Valley list, help panel, feedback and the overflow watch.

- `13:30–13:38` — README "Build Session 3 — working in public"; contract files updated (table below).

## Measurements

| What | Value | How measured | When |
|---|---|---|---|

## Acceptance criteria

| AC | Result | Evidence |
|---|---|---|

## Contract files changed

| File | What changed | Why |
|---|---|---|
| `data-contract.md` | Five usage-rights records (ECCC climate-hourly, NCEI Global Hourly US-only, NRCS SNOTEL, Open-Meteo non-commercial, IEM NWS archive) with the terms pages fetched on Oct 9; inputs 8–11; feedback privacy tier; typical-peak lineage | D-03.2, D-03.6, D-03.7 |
| `evaluation.md` | The fair CRPS replaces the quantile score; the "ranks models" sentence withdrawn; MAE skill against pure persistence; future models store 19 quantiles; naive in the NOAA comparison | F1, D-03.4 |
| `architecture.md` | Components (history, scorer, feedback, web deploy), Stage 3 tables, new endpoints, DB guard rails, web deploy | Facts changed |
| `docs/ledger-spec.md` | The `typical` threshold kind and `params.typical_peak` in model cards | D-03.8 |
| `README.md` | "Build Session 3 — working in public": who it is for and 3 steps, feedback, what is measured live (with the run ID), known limits, how FloodLead will be judged, what changed; links to the track record | Part 1 item 6 |
| `compose.yaml` | Caddy serves `/srv/floodlead/web` (deployed by `scripts/deploy_web.sh`) | D-03.11 |

## Open issues and handoff to next stage

- (filled at end of each part)
