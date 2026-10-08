# Stage 02 — Forecast ledger, baselines, scoring and the first working app

> Living document. Written while the stage is built, committed with the code. Newest work-log entries at the bottom.

| | |
|---|---|
| Branch | `stage-02-ledger-app` (PR 1), then `stage-02-part2` (PR 2) per addendum 1 |
| Started | 2026-10-08 12:41 PT (19:41 UTC) |
| Finished | (fill at end) |
| Prompt | `docs/build/prompts/STAGE-02-ledger-app.md` + `docs/build/prompts/STAGE-02-addendum-1.md` (the addendum wins where they conflict) |
| Status | in progress |

## Goal

From this stage on, FloodLead makes promises in public and keeps score. Every hour it issues baseline forecasts (`persistence-v1`, `trend3h-v1`) for every live gauge and fixes them in an append-only, hash-chained ledger before the truth exists. It publishes the ledger entries and chain head off the VM on a `ledger` branch, and scores every forecast against what the river did, next to NOAA's official forecast.

In the same stage, the first user gets a working app that follows one real situation from problem to result, using real data: **will the Nooksack spill toward Sumas Prairie, and how many hours would we have?** The app shows North Cedarville against the official flood stages, NOAA's official forecast, FloodLead's baseline chances of crossing, a personal level, and a replay of the 2021 and 2025 overflows. Build Session 2 mentors look at `main` at about Oct 9 01:00 UTC, so the app and the ledger core ship first, in PR 1.

## Inputs read

- `CLAUDE.md`, `AGENTS.md` (append-only ledger, no leakage, no performance claims without a run ID, NOAA conditions).
- `docs/build/prompts/STAGE-02-ledger-app.md`: Parts A–G, F1–F3, 12 ACs.
- `docs/build/prompts/STAGE-02-addendum-1.md`, which overrides the prompt:
  - two PRs and a new order (F1 → app → ledger core → PR 1 by ~23:30 UTC → the rest in PR 2);
  - credentials are set;
  - **no disk snapshots** (accepted risk);
  - publish the ledger entries hourly, not just the head;
  - link `brief.md` as AI-drafted;
  - the worker runs the reboot test as the very last step.
- `docs/build/PLAN.md`: Stage 1 QA log (PASS, `fe8208f`) and the facts it verified: the `today/` 404 after midnight, 30-day files written ~08:19Z, ~570k unchanged rows rewritten per refresh, and the overflow onset at North Cedarville ≈ 147.5 ft in 2021 and 2025. Also the human-task table: snapshots declined; the reboot moved to me.
- `brief.md` (on `main`, AI-drafted by the supervisor). It will be linked, never edited.
- `docs/stages/STAGE-01-live-archive.md`: D-01.5, D-01.6, D-01.13, D-01.18–D-01.20 and open issues 6–11.
- `evaluation.md`: its "> 30 min stale" rule assumed a far faster feed than ECCC's 40–90 min, and will be replaced.
- **State at start (19:41 UTC):**
  - `.env` keys: `PUBLIC_HOSTNAME, POSTGRES_PASSWORD, ARCHIVE_DIR, LEDGER_GITHUB_TOKEN, USGS_API_KEY` (values not printed);
  - health green for all three sources; disk 18.2 %;
  - all 4 services up for 21–22 h.

## Plan

Order from addendum 1 (targets in UTC):

1. Open this doc, commit, push (first).
2. **F1** (before 00:00): dated-directory fallback for ECCC `today/` 404s, for both `hourly/` and `daily/`, recorded in `ingest_runs.details`. Mocked-404 tests plus a live check of the dated path. Deploy.
3. Credentials: recreate `ingest`; confirm the USGS keyed rate limit without printing the key.
4. **App, part 1 (~21:30):**
   - static `web/` served by Caddy under a strict CSP: the overflow-watch view on Stage 1 data, NOAA's forecast, data age, the station picker with a 7-day chart;
   - the 2021/2025 replay computed from the DB for every minor-stage event, via a new API endpoint;
   - snapshot mode (`floodlead export-demo`);
   - the README Build Session 2 section;
   - **F3**: live URL at the top of the README; `brief.md` link; snapshot claims removed from the contract files.
5. **Ledger core (~23:15):**
   - migration `002` (ledger tables, immutability triggers, serialised appends);
   - canonical JSON and hashing with a golden vector; genesis and model cards;
   - `persistence-v1` and `trend3h-v1` with empirical error-path libraries;
   - an hourly issuer at HH:15 with gap entries;
   - `/v1/ledger`, `/v1/ledger/head`, `/v1/stations/{id}/forecast`;
   - the app's forecast panel (chances, personal level) and ledger panel.
6. **PR 1** `Stage 02 (part 1): first app and forecast ledger` with a STAGE REPORT of what is done and what is not.
7. **Part 2** on `stage-02-part2` from the merged `main`:
   - official forecasts in the ledger, scorer and summaries, remaining API;
   - hourly anchors and entries published to the `ledger` branch via `LEDGER_GITHUB_TOKEN`;
   - both verifiers (`--source github`);
   - **F2** (0 rows written on identical re-fetch; WAL before and after);
   - health blocks, tests, docs, screenshots;
   - **PR 2**, then the STAGE REPORT, then `sudo reboot` as the last action.

## Decisions

### D-02.1 — Addendum 1 applied: two PRs, new order, credentials, no snapshots, published ledger, brief, reboot

- **Context:** addendum 1 (supervisor, Oct 8) overrides the Stage 2 prompt where they conflict.
- **Choice (one record per addendum item, as asked):**
  - (0) **Timeline.** F1 first; then the overflow-watch app with replay, snapshot mode, README section and F3 (~21:30Z); then the ledger core with `persistence-v1`/`trend3h-v1` plus the forecast and ledger panels (~23:15Z); then PR 1 `Stage 02 (part 1): first app and forecast ledger` (~23:30Z). Everything else goes to PR 2 from `stage-02-part2`. If the ledger slips, PR 1 ships without it.
  - (1) **Credentials** recreated and checked without printing the values (D-02.3).
  - (2) **No disk snapshots.** Every "daily snapshots are the off-machine copy" claim is removed from the contract files. Plainly: there is no off-machine copy of the raw archive or the database. The Stage 1 doc gets only a dated note.
  - (3) **Publish the ledger.** Each hour's entries go to the `ledger` branch as `ledger/entries/YYYY/MM/DD/HH.jsonl.gz` (in PR 2, with `verify_ledger.py --source github`), with bytes per hour measured.
  - (4) **`brief.md`** linked as "Brief (AI-drafted at the author's request)", never edited.
  - (5) **Reboot.** `sudo reboot` once, as the very last action after PR 2 and its report; replaces "do not reboot".
- **Why:** the mentors review `main` at ~01:00Z on Oct 9. A working app on `main` matters more than completeness.
- **Reversibility / cost:** none.

### D-02.2 — F1: dated Datamart directories first, then the previous date, then `today/`

- **Context:** `today/hydrometric/…` returned 404 for a few minutes after 00:00Z on Oct 8 (supervisor QA), and the ECCC run at 00:03:50Z failed. The 30-day `daily/` files are written once a day (~08:20Z), so for ~8 h after midnight only the previous date's `daily/` exists.
- **Measured at 19:50Z:** `/20261008/WXO-DD/hydrometric/csv/BC/hourly/` → `200`, 428 files, newest 19:31. Its `daily/` → 442 files, newest 08:20. `/20261007/…` and `/20261006/…` are still served (hourly newest 23:31, daily 08:20). `BC_08MH001` has the same `Last-Modified` (19:31:19) via the dated path and via `today/`.
- **Options considered:** (a) `today/` first, falling back on 404; (b) the dated directory for the current UTC date first, then the previous date, then `today/`.
- **Choice:** (b), in `eccc.fetch_listing()`, used by both `hourly/` and `daily/`. A 404, or a listing with no files, moves on to the next candidate. The directory that served the run and the fallbacks tried go into `ingest_runs.details` (`listing_dir`, `listing_fallbacks`). A 404 inside the rollover window is not an error; the run only fails if all three 404.
- **Why:** the dated directory is the stable location, and the normal case is one request. Right after midnight, the previous date's directory still holds the last pre-midnight files, so the run succeeds with no new data rather than failing. `today/` stays as a last resort.
- **Side effect:** `fetch_state` is keyed by URL, so each new date means one full download of the ~430 files at the first rewrite after midnight. Those are new versions anyway. The switch at deploy cost one extra full download (run 475, below).
- **Tests:** `tests/test_eccc_rollover.py` (5 tests, mocked transports). The live test now asserts that the dated directory serves ≥ 400 files.
- **Reversibility / cost:** small; `eccc_root` and `eccc_base` are settings.

### D-02.3 — Credentials checked without printing them

- `docker compose up -d ingest` recreated the scheduler. In the container: `USGS key loaded: True | ledger token loaded: True`.
- USGS with the key (header read from `.env` by a process substitution, so the key never appears in a command line or log): `HTTP/2 200`, **`x-ratelimit-limit: 1000`, `x-ratelimit-remaining: 999`**. The same request without a key: `HTTP/2 200` with **no** rate-limit headers.
- **Finding, contrary to addendum item 1's expectation:** the keyed limit header still reads 1000. What changed is that requests now count against a per-key quota that USGS reports (`remaining`), instead of the opaque per-IP limit that blocked us for up to an hour in Stage 1.
- Live USGS ingestion is back on the OGC API (run 478 `ok`, 10 payloads, no NWIS fallback). The NWIS fallback (D-01.19) stays for 429s.
- `LEDGER_GITHUB_TOKEN` is used from the anchor job in PR 2; checked there.

### D-02.4 — Overflow replay: definitions, computed from the database

- **Context:** the demo path needs "how many hours the gauge gave before the overflow began" for **every** North Cedarville minor-stage event, not just 2021 and 2025, computed rather than typed in.
- **Finding:** the Overflow at SR 544 gauge (`usgs:12211195`) record begins 2015-11-14 09:15Z. Until 2026-10-01 it reported only in short episodes (10 episodes; values 3.54–7.75 ft), each during a North Cedarville minor event. **Since 2026-10-01 it reports continuously at 3.53–3.54 ft** (1,201 rows), below its NWS action stage (3.6 ft). "First record" therefore meant onset only until Oct 1.
- **Choice (`src/floodlead/replay.py`):**
  - event = a run of North Cedarville levels ≥ 146.5 ft, merging runs less than 48 h apart;
  - `action_first` = first record ≥ 144.8 ft in the 72 h before minor (the 2025 rise dipped below action and came back);
  - moderate, major and peak in [minor − 24 h, last minor + 24 h]; the peak reports when it was first reached and its plateau end;
  - onset = first overflow-gauge record in [minor − 12 h, last minor + 24 h] before 2026-10-01, or the first record ≥ 3.6 ft after that date;
  - events whose window begins before the gauge record existed are excluded from the summary (2015-11-13).
  - Served by `/v1/replay/overflow` and `/v1/replay/overflow/{event_id}/series` (ft as published; cached 1 h and warmed at API start: 8.5 s cold → 0.17 s).
- **Result (computed 19:51Z):** 20 minor events since 2008, 13 with the gauge operating, **7 with an overflow**. Onset at North Cedarville **146.20–148.44 ft (median 147.56)**, **0.08–6.42 h after minor (median 4.92 h)**. 6 events without an overflow peaked up to 147.30 ft. All the supervisor's 2021/2025 figures are reproduced exactly: 2021 action 18:30Z, minor 21:30Z, overflow 02:25Z (3.81 ft) at 147.56 ft, 4 h 55 min, moderate 04:00Z, major 23:45Z, peak 150.76 ft at 00:50Z, Everson action 00:15Z; 2025 action 12-09 07:15Z, minor 20:15Z, overflow 00:45Z at 147.47 ft, 4 h 30 min, moderate 03:30Z, major 10:00Z, peak 150.44 ft. The only nuance is that the 2025 peak is a 10:30–11:00Z plateau; the supervisor quoted 11:00Z.
- **Consequence for the app:** the ranges overlap, so no single "~147.5 ft" level is supported. The app offers **146.2 ft** (lowest onset seen) as a suggested personal level, labelled "empirical observation, not an official threshold", with the full spread shown.
- **Reversibility / cost:** definitions are constants in one module, with the docstring served as `method`.

### D-02.5 — The app: static files behind Caddy, same-origin API, recorded snapshots, strict CSP

- **Options considered:** (a) a framework SPA with a build step; (b) server-rendered pages from FastAPI; (c) static HTML, CSS and vanilla JS in `web/`, served by Caddy, calling the same-origin `/v1/*` API.
- **Choice:** (c).
  - Caddy routes `/v1/*`, `/docs` and `/openapi.json` to the API and serves `web/` for everything else.
  - The app gets `Content-Security-Policy: default-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'; object-src 'none'` (these extra directives only restrict; nothing is relaxed). `/docs` is excluded, because Swagger UI loads from a CDN.
  - **Snapshot mode:** `floodlead export-demo` runs the real API code in-process against the database and writes each canonical path's response to `web/data/snapshot/<slug>.json` with `snapshot_at`. Slug = path without the leading `/`, with every run of characters outside `[A-Za-z0-9._-]` replaced by `_`. When the API cannot be reached, the app loads these and shows a "Snapshot from …" banner.
  - Chart library: uPlot, vendored (MIT).
  - The observations endpoint gains `days=1..7`, so canonical paths are time-independent.
- **Why:** no build step, reproducible from the repo with `python3 -m http.server -d web 8080`, no third-party requests, and the strictest CSP that works.
- **Work split:** the frontend in `web/` was built by a background agent against exact API contracts written by the worker, while the worker built the backend. Every file is reviewed and committed by the worker.

### D-02.6 — No disk snapshots: claims removed (addendum item 2)

- Removed "daily snapshots are the off-machine copy" from `architecture.md` (data architecture record, cost line, deployment) and `README.md` ("How it works" storage row). Each now says plainly: **there is no off-machine copy of the raw archive or the database**, and the ledger entries are published hourly to the `ledger` branch. Cost estimate without snapshots: ≈ US$68–70/month (estimate).
- `data-contract.md` had no snapshot claim. `docs/stages/STAGE-01-live-archive.md` got only a dated note on open issue 2.

### D-02.7 — One global chain, and the database enforces it

- **Options considered:** (a) one chain per station; (b) one global chain.
- **Choice:** (b). Every entry type (`genesis`, `model_card`, `issuance`, `forecast`, `official_forecast`, `gap`) goes into one sequence `ledger_entries(seq, entry_type, created_at, canonical, prev_hash, entry_hash)`, plus query columns (`station_id`, `model`, `base_time`, `lid`) that are copies and never used for verification.
- **Why:** one head hash covers everything. A single anchor per hour proves the whole record, including issuances and gaps; per-station chains would need hundreds of anchors.
- **Enforcement** (migration `002_ledger.sql`): a `BEFORE INSERT` trigger rejects any row unless `seq = last + 1` (genesis = 1, with zero `prev_hash`), `prev_hash = last entry_hash`, and `entry_hash = encode(sha256(convert_to(prev_hash || E'\n' || canonical, 'UTF8')), 'hex')`. So the database recomputes every hash on insert. `BEFORE UPDATE OR DELETE` row triggers and a `BEFORE TRUNCATE` statement trigger reject changes. Appends take `pg_advisory_xact_lock(hashtext('floodlead.ledger.append'))`, so concurrent writers queue; a racing writer that slipped past would fail on the primary key, not fork.
- **Wording:** this is **tamper-evident, not tamper-proof**. A database superuser can disable triggers; the hourly external anchors and published entries (PR 2) are what make a rewrite visible.
- **Tests:** golden vector, tamper detection, trigger rejections, 4 threads × 5 transactions appending concurrently → gapless and verifiable.

### D-02.8 — Canonical JSON, rounding and the hash rule

- canonical = `json.dumps({"seq", "entry_type", "created_at", "data"}, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`. Keys sort by code point; UTF-8 is kept, not escaped.
- Levels and probabilities are rounded to 4 decimals **before** serialisation (0.1 mm in metres; 1e-4 in probability; -0.0 becomes 0.0; NaN becomes null), so the text never contains exponents.
- Timestamps: RFC 3339 UTC with `Z`; `created_at` to milliseconds, other times to seconds.
- `entry_hash = hex(sha256(prev_hash_hex + "\n" + canonical_utf8))`; genesis `prev_hash` = 64 zeros. Verifiers hash the stored text and never re-serialise.
- **Golden vector** (in `tests/test_ledger.py`, cross-checked with `sha256sum`): entry 1 → `4f02a159d797b56810d422afce63f20d47455a086f83bf582263d35985e2fa4e`; entry 2 → `74873df1285247e90aa859d27b11ba17d66b2c76c03e129f3c7b0bc9b5cd4b1e`.

### D-02.9 — Base time, the HH:15 run, horizons, and no backdating

- `base_time` = top of the UTC hour. The scheduler job `ledger-issue` runs at HH:15, after the HH:01 Datamart rewrite becomes visible at about HH:05–HH:07 (polled every 5 min). It also runs at scheduler start, which issues only if that start is within 30 min of the base time.
- `created_at` = the run's start time = the input cutoff: every input has `ts ≤ created_at` and `first_seen_at ≤ created_at`. The entries are committed when the run finishes (72 s later for the first run). Both times are recorded: `created_at` in each entry and the commit time in the issuance's `runtime_s`.
- Horizons 1, 3, 6, 12, 18, 24, 36 and 48 h, with `valid_at = base_time + h`. A horizon is dropped when `valid_at − created_at < 30 min`.
- **No backdating:** a run more than 30 min after its base time writes a `gap` for it. Any base time after the last issuance or gap that has neither gets a `gap` entry from the next run. Gaps are never filled. Before the first issuance nothing is recorded.

### D-02.10 — Baselines: empirical error paths, the 6 h trend cap, the stale rule

- **Method (`src/floodlead/baselines.py`):** samples = point path + the same model's error paths at past origins, indexed by lead from `data_as_of` on the station's grid (5 min ECCC, 15 min USGS). Gaps of up to 30 min are carried forward when building paths, and paths with longer gaps are dropped.
  - `q` = quantiles of the level at `valid_at`;
  - `qmax` = quantiles of the running maximum over `(data_as_of, valid_at]`;
  - `p_exceed` = fraction of sample paths whose running maximum reaches the threshold (from samples, not interpolated);
  - quantiles at 0.05/0.10/0.25/0.50/0.75/0.90/0.95, via `numpy.quantile` linear.
- **Libraries:** ECCC uses the trailing 30 days, with an origin every 1 h. USGS adds the same season (day of year ± 30 days) in every prior year, with an origin every 3 h; North Cedarville's library holds 9,266 paths.
  - **Deviation:** libraries are computed fresh in each run, from data first seen before `created_at`, rather than precomputed daily and cached. A run takes 72 s, well inside the 10-min budget, and per-run computation is leakage-safe by construction.
  - Each forecast records `error_library.hash` (sha256 of model, station, origin times and the error matrix rounded to 1e-4 as float32) and `paths`.
- **trend3h-v1:** least-squares slope over the 3 h ending at `data_as_of`, needing ≥ 50 % of the window's grid points (else that station is skipped and counted). Point path = last level + slope × min(lead, 6 h), so the trend is held after 6 h. The library uses the same capped trend at each origin.
- **Stale rule:** `stale_inputs = created_at − data_as_of > 150 min (ECCC) / 120 min (USGS)`, the sources' green lag thresholds. Stale forecasts are still issued. This replaces `evaluation.md`'s "> 30 min" rule (update in PR 2).
- **Thresholds:** NWS categories where defined (North Cedarville, Ferndale, Everson, Overflow SR 544), plus rises of +0.25, +0.5 and +1.0 m above the level at `data_as_of`.
- `input_hash` = sha256 of the canonical list `[[ts, value_r4], …]` of the observations in the 3 h window ending at `data_as_of` (the point-path inputs).
- A station-model with fewer than 50 library paths is skipped and counted (2 stations each in the first run).

## Work log

- `12:41` — `git checkout main && git pull` → `9e414f1` ("Stage 2 addendum: timeline reset, app first, two PRs before the mentor review"). PR #2 shows as `MERGED`. Read the prompt, addendum 1, PLAN.md and `brief.md`. `git checkout -b stage-02-ledger-app`.
- `12:42` — Committed and pushed the opened doc (`288b03c`).
- `12:43` — Live probe of the dated paths (D-02.2). Implemented F1 (`eccc.candidate_bases`, `eccc.fetch_listing`), `tests/test_eccc_rollover.py` and the live test update. `ruff` clean. `pytest -q` → **49 passed**, 4 deselected (DB tests ran against the production server's Postgres on 127.0.0.1 via disposable `floodlead_test_*` databases). `pytest -m live -k eccc` → 1 passed.
- `12:44` — Rebuilt and recreated `ingest` (D-02.3).
  - First run on the dated directory, run 475: `ok`, `listing_dir https://dd.weather.gc.ca/20261008/WXO-DD/hydrometric/csv/BC/hourly/`, `listing_fallbacks []`, 428 fetched (one-time re-download for the new URLs), 0 inserted, 554,107 unchanged, 54.9 s.
  - USGS run 478 `ok` via OGC; NWPS run 476 `ok`.
- `12:46–12:50` — Overflow gauge episodes and North Cedarville minor events via SQL (D-02.4). Started a background agent for `web/` with the API contracts for the existing and new endpoints, the forecast and ledger shapes, snapshot slugs and CSP rules.
- `12:50–12:52` — `src/floodlead/replay.py`, `/v1/replay/overflow` and `/v1/replay/overflow/{event_id}/series`, `days=` on observations, `floodlead export-demo` (`src/floodlead/snapshot.py`). TestClient smoke test: replay `200` 8.53 s cold; 2021 series `200` with 340 / 272 / 396 points for 12210700 / 12211195 / 12211200; unknown event `404` with attribution; `days=7` → 670 rows. `pytest` → 49 passed. Deployed api: `/v1/replay/overflow` public `200 0.17 s` (warm).
- `12:52` — Caddyfile: static `web/` with CSP plus API routes. Validated with `caddy validate` (2.11.7). Compose mounts `./web:/srv/web:ro` into caddy (not yet recreated: waiting for the app files).
- `12:53–12:58` — README: live URL at the top (F3), brief link "Brief (AI-drafted at the author's request)", the "Build Session 2 — working app" section with the replay table generated from the live endpoint; no-snapshot edits (D-02.6).
- `12:58–13:01` — Ledger core: `migrations/002_ledger.sql`, `ledger.py`, `baselines.py` (numpy 2.5.3 added), `issuer.py`, CLI `floodlead issue [--dry-run]`, `floodlead ledger verify`, scheduler job `ledger-issue` (3600 s, offset 900 s), `GIT_SHA` build arg recorded as `FLOODLEAD_GIT_SHA`.
  - `floodlead migrate` → `['002_ledger.sql']`. The migration only adds tables, so no `pg_dump` was needed.
  - Dry run at 19:58Z (late, so nothing could have been written): 426 + 426 forecasts, skipped `{"no level observation in the last 3 h": 15, "persistence-v1: error library < 50 paths": 2, "trend3h-v1: …": 2}`, 71.3 s, 157 MB peak RSS, 2,953 B per forecast.
- `13:01` — Committed and pushed `a4d4a6e`; built with `GIT_SHA=a4d4a6e292d9f4a248b51ebdd762dc08e44050bf`; recreated ingest at 20:01:11Z.
  - **First live issuance:** base 20:00Z, `created_at` 20:01:13.352Z, written 20:02:26Z. 856 entries: genesis (seq 1), 2 model cards (2–3), 852 forecasts (4–855), issuance (856). Runtime 72.2 s, peak RSS 184 MB.
  - `floodlead ledger verify` → `ok: True, entries: 856, last_hash ccf8f76d7617484031b08786180ab6d600bf90f750785dbae5a120e587a13a98`. `UPDATE ledger_entries …` → `ERROR: ledger_entries is append-only (UPDATE not allowed)`.
- `13:02–13:04` — API: `/v1/ledger?after_seq=&limit=` (≤ 1000), `/v1/ledger/head` (anchor `pending` until PR 2), `/v1/ledger/{seq}`, `/v1/stations/{id}/forecast` (latest per model with seq, hash and all fields, plus NOAA's latest issuance for linked gauges, labelled "NOAA NWS official forecast (unmodified)"). Deployed. Public: head seq 856. North Cedarville at 24 h: persistence P(action) 0.0004, P(+0.25 m) 0.1227; trend 0.0003 / 0.1107.
- `13:04–13:07` — Tests: `tests/test_ledger.py` (golden vector, rounding, tamper detection at the right seq for a changed byte, a swapped pair and a deleted entry, mid-chain start, DB trigger rejections, gapless concurrent appends), `tests/test_baselines.py` (constant series → zero-width intervals; random walk → quantiles within 15 % of analytic, rise exceedance 0.02–0.06 vs reflection-principle 0.0455; trend cap, coverage and gaps; ffill limit), leakage test in `tests/test_db.py`. One fix: TRUNCATE of `ledger_entries` alone hit the `ledger_anchors` foreign key first, so the test truncates both to exercise the trigger. **75 passed, 1 skipped.**
- `13:05` — The frontend agent finished (report: uPlot 1.6.32 vendored with sha256s, 15 web tests, no git or service actions). Its catch: `.gitignore` `data/` also ignored `web/data/`; changed to `/data/`. Reviewed `web/`: no `innerHTML`, no inline script or style, no third-party URLs. `floodlead export-demo` → 43 files, 2.6 MB. Recreated caddy: `/` → app with the CSP header, `/v1/*`, `/docs` and `/openapi.json` → API; `/docs` has no CSP.
- `13:07–13:10` — Screenshots with headless Chromium (`zenika/alpine-chrome@sha256:ee10e242…`, Puppeteer; `scripts/screenshots.cjs`) at 1280 px and 375 px: 0 console errors, page errors or failed requests.
  - Review found and fixed: (1) `appendKids` took one argument, so multi-argument calls dropped children; the Overflow gauge block was missing its observation time and stage list. (2) Input age now uses `created_at − data_as_of` (the entry's `input_age_min`). (3) The Overflow block now states "below action stage: no overflow; reports ~3.5 ft continuously since 2026-10-01".
  - The snapshot `index.json` gained attribution. Web tests 16 passed. Screenshots committed in `docs/stages/img/stage-02/` (4.8 MB).
- `13:10` — Ledger size after the first issuance: 856 entries, 2,849,717 B canonical text, 3,341 B average per forecast, `pg_total_relation_size` 1,656 kB (TOAST compression).

## Measurements

| What | Value | How measured | When |
|---|---|---|---|
| F1 first dated-directory run | 428 files from `/20261008/…/hourly/`, 0 fallbacks, 54.9 s | ingest_runs 475 | 19:51Z |
| Replay compute | 8.5 s cold, 0.17 s warm (cached 1 h, warmed at API start) | TestClient, public `curl` | 19:50–19:52Z |
| Issuance runtime / peak memory | 72.2 s / 184 MB (dry run: 71.3 s / 157 MB) | issuer log, `ru_maxrss` | 20:01Z |
| Entries per hourly issuance | 852 forecasts + 1 issuance (+ model cards and gaps when due) | ledger | 20:02Z |
| Bytes per forecast entry | 3,341 B canonical (avg); ledger table 1,656 kB for 856 entries | SQL `length(canonical)`, `pg_total_relation_size` | 20:10Z |
| Ledger growth (estimate from one issuance) | ≈ 2.85 MB canonical/h → ≈ 68 MB/day of text, ≈ 40 MB/day stored after compression | × 24 | 20:10Z |
| Snapshot | 43 JSON files, 2.6 MB | `export-demo` | 20:09Z |
| Screenshots | 15 PNGs, 4.8 MB, 0 browser errors | `scripts/screenshots.cjs` | 20:09Z |

## Acceptance criteria

| AC | Result | Evidence |
|---|---|---|

## Contract files changed

| File | What changed | Why |
|---|---|---|

## Open issues and handoff to next stage

- (filled at end)
