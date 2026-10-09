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

### D-02.11 — Anchors and the published ledger: one Git Data API commit per hour on an orphan `ledger` branch

- **Options considered:** (a) the contents API, which makes one commit per file, so the entries file and the `heads.txt` line would land in separate commits; (b) the Git Data API: blobs, a tree on top of the previous tree, a commit with the previous head as parent, then a fast-forward ref update with `force: false`.
- **Choice:** (b). Each hourly anchor (job `ledger-anchor` at HH:30, after the HH:15 issuance is written) is **one commit** containing:
  - `ledger/entries/YYYY/MM/DD/HH.jsonl.gz`: every entry since the previous anchor, one JSON object per line (`seq, entry_type, created_at, canonical, prev_hash, entry_hash`, as stored), gzip with mtime 0;
  - the updated `ledger/heads.txt`, with one appended `<anchored_at> <seq> <entry_hash>` line.
- The `ledger` branch is an **orphan** (README plus `ledger/` only; no code), created by the first anchor. The job never touches `main` and never force-pushes; the ref update would fail rather than rewrite.
- Every attempt is recorded in `ledger_anchors` (`ok` or `error`, with commit SHA, URL, path and bytes). The table is append-only like the ledger.
- Manual run: `floodlead ledger anchor`. The token comes from `LEDGER_GITHUB_TOKEN` in `.env`. It expires 2026-11-07 (from the API's `github-authentication-token-expiration` header).
- **First anchor (20:15:45Z):** commit `28aefd8958451e550dd0d90e0d953e244091a337`, 856 entries, **395,114 B** gzip. Checked from outside: raw `heads.txt` = `2026-10-08T20:15:45Z 856 ccf8f76d…3a98`, and the downloaded `20.jsonl.gz` recomputes to the same head with a stdlib script. `git ls-remote` shows `main` still at `9e414f1`.
- **Publication size (addendum item 3):** ≈ 0.4 MB per hourly issuance → ≈ **285 MB/month**, under the ~1 GB/month limit. Git does not delta-compress gzip blobs well, so the repository grows by about that much each month. If that becomes a problem, alternatives are daily files, or hourly files kept only for a rolling window plus daily consolidations (each would be a published decision, never a silent drop).

### D-02.12 — NOAA issuances in the ledger: one entry per fetch, values exactly as received

- **Context:** NOAA keeps the same `issuedTime` and appends points: NRKW1's 2026-10-07 15:36Z issuance gained one point at each 6-hourly refresh (29 → 32 points by Oct 8).
  - **Corrected in D-02.18:** NOAA did not append points. The combined `stageflow` endpoint cuts NRKW1's forecast at request time + 7 days, so each fetch revealed more of an issuance that was complete from the start.
- **Choice:**
  - For each NOAA issuance, one `official_forecast` entry per fetch that brought new points, in fetch order: `part = "issuance"` for the first, `"added points"` for later ones. Each carries the points exactly as stored (stage ft, flow kcfs, `generated_at`), NOAA's `issuedTime`, our true `fetched_at` and the raw payload's sha256.
  - No unit conversion or rounding is applied; conversion to metres happens only in scoring.
  - Appended by the hourly issuance run (also in a late run), so the lag is ≤ 1 h. The issuances held since Oct 7 go in with their real fetch times, which is allowed: these are facts, not forecasts.
- **Preview at 20:20Z:** 8 entries for 4 issuances (NKSW1 ×2 with 40 points each; NRKW1 Oct 7: 29 + 1 + 1 + 1; NRKW1 Oct 8: 28 + 1).

### D-02.13 — Truth and scoring rules (scores are derived data, not ledger entries)

- **Settling:** a horizon is scored once `valid_at` is ≥ 3 h old. The scorer runs hourly at HH:40 (`floodlead score` by hand).
- **Level truth:** the observation at `valid_at`, else the nearest within ±10 min, else `no_truth` (counted, never imputed).
- **Event truth:** the maximum observation over `(data_as_of, valid_at]`. This is the same window as `qmax` and `p_exceed`, so forecast and truth mean the same thing. The window includes the feed-latency gap the forecaster could not see. Fewer than 80 % of the window's grid points → `insufficient_truth`.
- **Stored with each score:** the truth value, its timestamp, `first_seen_at` and `revision_count`.
- **Rescoring:** a score is rewritten when any observation in its truth window was revised after it was scored. To keep runs cheap, only stations with a recent revision are re-checked.
- **Metrics:**
  - **CRPS approximated by the quantile score**, 2 × mean pinball loss over the 7 levels. It equals the absolute error for a point forecast (tested). Measured against the analytic CRPS of N(0,1): −7 % at z = 0, −25 % at |z| = 1, −18 % at |z| = 2, and **−19.4 % in expectation** for a calibrated forecast (200,000 draws). It is applied identically to every model, so it ranks models, but its absolute values are biased low and are not comparable with exact-CRPS figures elsewhere.
  - Also: absolute error of the median, coverage of the 25–75, 10–90 and 5–95 % intervals, PIT bin (0–7), and Brier per threshold with its outcome.
- **Skill:** CRPSS and BSS vs persistence use **paired samples only** (same station, base time, horizon; both scored, neither stale). A family with fewer than 30 events reports "too few events to judge" instead of a number. Stale-input forecasts are excluded from the summary.
- **NOAA matched comparison:**
  - eligibility: base times at 00/06/12/18Z, horizons in multiples of 6 h, stations with an NWPS forecast;
  - comparison point: NOAA's latest issuance with points fetched by our `created_at`, at the same `valid_at`;
  - metrics: absolute error, and Brier with p ∈ {0, 1} for the official categories, using NOAA's points in the same window; NOAA's own lead (`valid_at − issuedTime`) is reported.
- **Summary:** materialised after every scorer run into `score_summaries`, carrying `scorer_run_id` and the window. Served by `/v1/scores/summary` and `/v1/scores/official`.
- **Not done:** the day-block bootstrap intervals for CRPSS (optional in the prompt).

### D-02.14 — Health gains `issuer`, `scorer` and `anchor` blocks

- **issuer:** age of the newest `issuance` or `gap` base time. Green ≤ 75 min, amber ≤ 135 min, otherwise red; amber if the newest entry is a gap. The block also reports gaps in the last 24 h, forecast counts and runtime.
- **scorer:** age of the last finished run, same thresholds.
- **anchor:** age of the last `ok` anchor, same thresholds, plus errors in the last 24 h. Amber "pending" before the first anchor.
- **Why 75/135 min:** the jobs are hourly, so one missed run turns amber and two turn red. The overall status is the worst of all blocks.

### D-02.15 — F2: identical re-fetches write nothing; a `payload_coverage` table keeps the out-of-order guard

- **Context:** each ECCC refresh rewrote about 555–577k unchanged observation rows (`last_seen_at`, and `published_at = GREATEST(…)`). Measured before the fix, over one refresh (20:25:44 → 20:38:21Z, run 511 plus a USGS and an NWPS run): **554,126 row updates** on the observation chunks (482,808 HOT), 5,916 inserts, +70,313 dead tuples, and **WAL 0x3FCB964F8 − 0x3F46F0940** (bytes in the measurements table).
- **Options considered:** (a) keep bumping `last_seen_at` but only every N hours; (b) stop writing unchanged rows entirely, and move "last seen" to a small per-station table outside the hypertable.
- **Choice:** (b). It is a code change plus one **new** table (`migrations/004_payload_coverage.sql`). No existing table is altered, so no `pg_dump` was required.
  - The unchanged path only **counts** rows: an identical re-fetch writes **0** observation rows, proven in tests by unchanged `xmin`.
  - **Out-of-order guard kept.** A differing incoming value is stale if the stored row's `published_at` is newer, **or** if a newer payload (of any kind) for that station already covered that timestamp. Without the second rule, an older 30-day file published between two identical hourly files could flip a value back. This is tested with exactly that scenario.
- **Meanings from now on (also in `architecture.md`):**
  - `first_seen_at` — when the row was first stored.
  - `last_seen_at` — when the **current value was last written** (first insert or last revision); no longer bumped on identical re-fetches.
  - `published_at` — publication time of the payload that set the current value.
  - `payload_coverage(station_id, kind, published_at, ts_min, ts_max, raw_object_id, last_seen_at)` — the per-station "last seen": the newest payload of each kind (`eccc:hourly`, `eccc:daily`, `usgs:ogc`, `usgs:nwis`), its time range, and when it was last processed. One row write per station per payload, instead of ~1,300.
- **After (measured, 20:39:33 → 21:07:52Z):** one full ECCC refresh (run 525: 427 files fetched, 2,910 inserted, 0 updated, 561,125 unchanged) plus 3 USGS runs, 2 NWPS runs, both station refreshes and a scorer run.
  - **0 row updates** on the observation chunks (`n_tup_upd` 24,907,584 → 24,907,584; before: +554,126).
  - **0 new dead tuples** (232,594 → 232,594; before: +70,313).
  - **WAL 15,733,024 B** over 28.3 min, vs **139,090,872 B** over 12.6 min before: at least **8.8× less**, in a longer window with more jobs.

### D-02.16 — Addendum 2 (supervisor QA of part 1) applied

PR #3: PASS, merged `4efdd81`. Each item, in the supervisor's order:

1. **Suggested personal level.** Replaced 146.2 ft, the March 2026 onset level, which came on the falling limb about 3 h after the 146.6 ft peak, so it is not a trigger level.
   - The suggestion is now the **official NWS minor flood stage, 146.5 ft**, with the rule "7 of 13 minor-stage events since Nov 2015 were followed by water on the overflow path, a median 4.9 h later (0.1–6.4 h)".
   - The summary lists the peaks with and without an overflow, and says they overlap (overflow 146.6–150.8 ft, none 146.7–147.3 ft), so no single level separates them.
   - API fields: `suggested_*`, `peaks_*`, `separation_text`, `onset_note`. README and app updated.
2. **375 px horizontal scroll** (the uPlot live legend was 451 px): the legend now wraps to the chart width (317 px at 375 px), one series per line on narrow screens. `scripts/screenshots.cjs` records `scrollWidth` vs the viewport for every page and width in `layout-check.txt`, listing any element wider than the viewport. Result: **scrollWidth = viewport on all 4 pages at 1280 and 375 px**, live and in snapshot mode.
3. **Clipped chances tables:** the chances and personal-level cards are now full width, and all horizon columns are visible at 1280 px (checked visually). At 375 px tables scroll inside their box with a right-edge fade and a "scroll →" hint.
4. **Persistence named honestly** (D-02.17).
5. **Verifier gap:** `ledger.verify_rows` now requires entry 1 to be a genesis entry with a zero `prev_hash` whenever seq 1 is verified (the check used to run only when `start_seq is None`). `scripts/verify_ledger.py` already required it; both are now tested with a self-consistent chain whose entry 1 is not a valid genesis.
6. **`created_at` defined exactly** in `docs/ledger-spec.md`: the data cut-off and the start of computation; entries are inserted about 70 s later and anchored at HH:30. Issuance entries from base 22:00Z onward carry `inserts_started_at` and `committed_at` (database `clock_timestamp()` just before the inserts and just before the last insert).
7. **Deploy only code in an open PR.** PR 2 was opened as a **draft** (#4) at 21:50Z, before any further deploy. Production had run part-2 code without an open PR since 20:18Z; that was the worker's error. From Stage 3 on, deploys come only from a branch with an open PR.
8. **Snapshot ages and the POSIX locale.**
   - Ages are computed per response, relative to the snapshot's `snapshot_at` ("48 min before the snapshot"), so live and snapshot data mixed on one page both read correctly. The chart's "now" line becomes a "snapshot" line.
   - **POSIX locale:** uPlot runs `new Intl.NumberFormat(navigator.language)` at load. The new `web/locale-guard.js` (same-origin, loaded before uPlot; it does nothing for a valid tag) maps an invalid tag to `en-CA`, or else wraps `Intl.NumberFormat`/`DateTimeFormat` to fall back for invalid tags. Every chart also gets explicit formatters, and the sorts use an explicit locale.
   - Result with `navigator.language = 'en-US@posix'`: **0 page errors**, both charts drawn.
9. **First live rollover (F1):** recorded in the work log (`17:21`). The dated directory switched at the first run after midnight, with no fallback, no 404 and no failed run.

### D-02.17 — `persistence-v1` is "level + typical change"; pure persistence is scored as `persistence-naive`

- **Context:** `persistence-v1`'s median is the current level plus the station's median historical change over the lead. Ledger seq 562: `eccc:08MH001` level at `data_as_of` 1.515 m, q50 1.5135 m at 1 h. Calling it "the level stays the same" was wrong.
- **Choice:**
  - Keep the model, with its outputs unchanged. Append a corrected `model_card` with the same `params_hash`, plus `supersedes_seq` and `change: "method description corrected; parameters and outputs unchanged"`. The issuer now appends a card whenever the method text changes, not only the parameters.
  - Score **pure persistence** as `persistence-naive`: the `level_at_data_as_of_m` already fixed in each `persistence-v1` entry, used as a point forecast at every horizon. CRPS = absolute error (tested). Event probability is 1 if the level is already at or above the threshold, else 0. No coverage or PIT for a point forecast. The scores go to the new table `forecast_scores_naive`; the view `all_scores` unions both. Migration `005` adds a table and a view only, so no `pg_dump` was needed.
  - The summary reports, for every model, CRPSS and BSS against **both** `persistence-v1` and `persistence-naive` (`skill_vs`).
  - `evaluation.md`: baseline 1 and the Demo Day headline mean the naive one. The app labels the model "Persistence + typical drift".
- **Why:** honest naming, and a skill headline against the baseline people actually mean.

### D-02.18 — NOAA forecasts come from `stageflow/forecast`; the "added points" were our endpoint's 7-day cut

- **Context (found during the AC-5 check, 01:17Z Oct 9):**
  - For NRKW1's 15:12Z Oct 8 issuance, `gauges/NRKW1/stageflow` (combined observed + forecast, the endpoint we used) returned 30 points ending Oct 16 00Z.
  - `gauges/NRKW1/stageflow/forecast` returned the same `issuedTime` with **40 points, ending Oct 18 12Z**, and all 30 shared points were identical.
  - Across all 7 NRKW1 fetches held, the last point we received is exactly the last 6-hourly point at or before `fetched_at + 7 days`. For example, fetched Oct 8 12:05Z → last point Oct 15 12:00Z.
  - NKSW1 is not cut: both endpoints give 40 points.
  - So D-02.12's "NOAA appends points" was wrong. The issuance was complete when issued, and our endpoint revealed it a little more at each fetch.
- **Choice:**
  - `nwps.ingest_live` now takes forecast rows from `stageflow/forecast` (archived as `stageflow_forecast_<lid>`).
  - It still archives the combined `stageflow` payload, because the module keeps NWPS observed series raw. That adds 6 requests per 30 min, so `items_fetched` goes from 12 to 18.
  - `parse_forecast` accepts both shapes.
  - Existing ledger entries are not touched (append-only). The 10 NRKW1 points not yet held (Oct 16 06Z – Oct 18 12Z) enter `official_forecasts` at the next NWPS run and the ledger at the next hourly run, as `part = "added points"` with their true `fetched_at`.
  - The spec now defines `"added points"` as points first seen at a later fetch, and says why there were such entries before Oct 9.
- **Effect on scoring:** none so far. NOAA matched pairs use horizons ≤ 48 h, and every cut point was more than 7 days ahead.
- **Why:** AC-5 asks for the issuance point for point as NOAA publishes it. The ledger must hold what NOAA issued, not what one endpoint's window showed.
- **Tests:**
  - `test_nwps_forecast_only_endpoint_parses_the_whole_issuance`, using the new real fixture `nwps_stageflow_forecast_NRKW1.json`, trimmed to its first 4 and last 2 points.
  - A bare-shape case in `test_nwps_missing_forecast_gives_no_rows`.
  - The live test now asserts that the forecast-only points include every combined-endpoint point.

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
- `13:12` — `docs/ledger-spec.md`: entries, canonicalisation, hash rule, golden vector, entry types, issuance rules, DB guards, anchors and publication (part 2), how to verify, plus a minimal stdlib verifier. Checks: `printf … | sha256sum` → `4f02a159…fa4e` (matches); the spec's minimal verifier run against the public API → `OK 856 ccf8f76d…3a98`. README "what works now" updated (hourly forecasts live, links to the spec and screenshots).
- `13:14` — PR 1 opened: https://github.com/agenticraptor/trilemma-datathon-FloodLeadBC/pull/3 (interim STAGE REPORT; done vs not done). Branched `stage-02-part2` from it.
- `13:15–13:20` — Anchor job (D-02.11): token check via the API (repo reachable; expiry 2026-11-07); `floodlead ledger anchor` → first anchor and orphan branch (commit `28aefd8`). Outside verification passed. `official_entries()` (D-02.12) previewed: 8 entries.
- `13:20–13:24` — Committed and pushed the anchor and official entries (part 2 commit 1). Rebuilt and recreated ingest at 20:17:57Z (jobs `ledger-anchor` HH:30; official entries go into the next issuance).
- `13:24–13:32` — Scorer (D-02.13): `migrations/003_scores.sql` (scorer_runs, forecast_scores, score_summaries; new tables only), `scorer.py`, `tests/test_scorer.py`:
  - point-forecast identity, normal-CRPS tolerance, PIT, ±10 min truth, 80 % coverage rule, NOAA `fetched_at` rule;
  - an end-to-end test (issuer on 35 days of synthetic 15-min data → 2 forecasts → nothing scored at +1 h → 16 scores at +52 h → idempotent → summary with paired CRPSS and "too few events to judge").
  - Fixes on the way: `upsert_station_meta` needs `name`; `avg(int)` returns `Decimal` (cast to float); ledger test cleanup must also truncate `forecast_scores`.
  - `pytest` → **83 passed** (twice).
  - `floodlead migrate` → `['003_scores.sql']`. `floodlead score` → run 1, 0 scored (nothing settled before ~00:00Z), 1.1 s.
- `13:32–13:38` — Committed and pushed the scorer (`stage-02-part2`); deployed ingest and api. Health: issuer green (lag 25 min), scorer green, anchor green (seq 856). `/v1/scores/official` → note "No matched pair has settled yet…". `scripts/verify_ledger.py`: `--api` → OK 856, 1 anchor checked; `--source github` → OK 856 from 1 file; `--from-seq 856` → OK; `--from-seq 500` → `FAIL … must be an anchored seq` (exit 1). `tests/test_verify_script.py` (4 tests, incl. a forged self-consistent chain caught by the anchor). `evaluation.md` rewritten for the live ledger, baselines and scoring.
- `13:25–13:38` — F2 before-measurement (above) and implementation. `pytest` → 84 passed.
- `13:39` — F2 deployed: `floodlead migrate` in the recreated ingest → `004_payload_coverage.sql`. Contract files updated (table below).
- `13:41–13:44` — **AC-6:** `scripts/reproduce_forecast.py --api https://<host> --n 3 --seed 1` rebuilt 3 random ECCC persistence forecasts (seq 584 `eccc:08MH053`, 784 `eccc:08NM249`, 66 `eccc:07FD002`) from the public observations API only, keeping rows with `first_seen_at ≤ created_at`. `input_hash` matches ×3; library 667 paths = 667 ×3; median equal at all 8 horizons ×3 → `ALL MATCH` (2.3 s).
- `13:44` — **AC-3** on production, each statement inside `BEGIN … ROLLBACK`: `UPDATE` → `ERROR: ledger_entries is append-only (UPDATE not allowed)`; `DELETE` → `… (DELETE not allowed)`; `TRUNCATE ledger_entries CASCADE` → `… (TRUNCATE not allowed)`; a forged genesis `INSERT` → `ERROR: ledger: append must have seq 857 and prev_hash ccf8f76d…`. Ledger still 856 entries.
- `13:45` — API contract tests for the ledger, forecast, scores, health blocks and replay (`tests/test_api.py`). `pytest` → **92 passed**, 4 live deselected.
- `13:47` — **AC-7 leakage audit** (`scripts/audit_leakage.sql`, 3 min 11 s) over all 852 forecasts at 20:47Z: `data_as_of_after_created_at 0`, `data_as_of_row_not_visible_at_created_at 0`, `inputs_count_mismatch 0`, `horizons_under_30_min 0` of 6,816 horizons. To be re-run over all base times before PR 2.
- `14:07` — F2 after-measurement (D-02.15): 0 updates and 0 new dead tuples across a full ECCC refresh; WAL 15.7 MB vs 139.1 MB.
- `14:30` — **Second hourly issuance on schedule:**
  - The 8 `official_forecast` entries (seq 857–864) were written first, then base 21:00Z: `created_at` 21:15:00.526Z, 853 forecasts (persistence 427, trend 426; seq 865–1717), issuance seq 1718. Runtime 67.5 s, 166.3 MB peak. Skipped: 14 with no level in 3 h; 2+2 small libraries; 1 trend with < 50 % coverage.
  - `code_commit 3db93ac` (on `origin/stage-02-part2`).
  - **Second anchor** at 21:30:00Z: `ledger/entries/2026/10/08/21.jsonl.gz`, 396,798 B, commit `debf0dd215fc2b7d8a899be59ffb9c33c94c71c5`.
  - `verify_ledger.py --api` and `--source github` both → `OK entries 1718, head 6a8f0bef…9e83, anchors_checked 2`.
  - Health: issuer green (0 gaps in 24 h), anchor green (seq 1718).
- `14:31` — **PR #3 merged** by the supervisor at 21:30:49Z (`4efdd81`, "QA PASS"; no file changes beyond the PR). Merged `origin/main` into `stage-02-part2` (`7cd60e6`, no rewrite of pushed history), so part 2 now builds on the merged `main`, as addendum 1 asks.
- `14:40–14:52` — Addendum 2 received (`05cd1fa`). Merged `main` into `stage-02-part2` (`5846a73`). **Opened draft PR #4** at 21:50Z: https://github.com/agenticraptor/trilemma-datathon-FloodLeadBC/pull/4. Started a frontend agent for items 2, 3 and 8 and the UI parts of 1 and 4.
- `14:52–14:58` — Backend: replay summary (item 1); `verify_rows` genesis check plus 2 tests (item 5); corrected persistence card, card supersession, `inserts_started_at`/`committed_at` (items 4 and 6); `persistence-naive` scoring, migration 005, summary vs both references (item 4); spec and `evaluation.md` text. `pytest` → **94 passed**.
- `15:00–15:08` — Frontend agent finished items 2, 3, 8 and the UI parts of 1 and 4 (files: `web/app.js`, `style.css`, `index.html`, new `locale-guard.js`, `web/README.md`, `scripts/screenshots.cjs`).
  - Worker review: `locale-guard.js` read in full; no `innerHTML`/`eval` added; no "stays the same" wording left.
  - Screenshot sample personal level changed 146.2 → 147.0 ft (146.2 was the old suggestion, and sat 0.3 ft from the minor line).
  - `floodlead export-demo` refreshed the snapshot (43 files; replay with the new summary; ledger head 1718 with anchor `ok`). `tests/test_web.py` 16 passed.
  - **Independent re-run of the screenshots:**
    - live: all 4 pages `scrollWidth = viewport` at 1280 and 375 px; legends 1034/317 px; `page errors (all pages): 0; with navigator.language=en-US@posix: 0`;
    - snapshot mode (local `http.server`, no API): same layout results; banner "Snapshot from Thu, Oct 8, 15:03 PDT (Oct 8, 22:03 UTC)"; ages "48 min before the snapshot"; 0 page errors (console shows only the expected `/v1` 404s that trigger the fallback).
  - Screenshots and both checks committed under `docs/stages/img/stage-02/`.
- `15:16` — **Base 22:00Z** issued by the scheduler.
  - Corrected `persistence-v1` model card appended at **seq 1719** (`supersedes_seq 2`, `change: "method description corrected; parameters and outputs unchanged"`); `trend3h-v1` card unchanged.
  - Issuance: `created_at` 22:15:00.532Z, `inserts_started_at` 22:16:08.736Z, `committed_at` 22:16:09.903Z, so **created → commit = 69.4 s, measured**. Runtime 68.2 s; 857 forecasts (persistence 429, trend 428).
- `15:31` — **Third anchor** at 22:30:00Z: seq 2577, `ledger/entries/2026/10/08/22.jsonl.gz` 397,541 B, commit `0f17882324d4000f6b1a19f0db9ea636985aa13a`. All three anchors (20:15, 21:30, 22:30) were written with `LEDGER_GITHUB_TOKEN` by the anchor code: the first via `floodlead ledger anchor`, the next two by the scheduled job. None was pushed by hand with git.
  - `heads.txt` = 3 lines.
  - `verify_ledger.py --source github` → `OK entries 2577, head fd94c322…df42, anchors_checked 3, files 3`; `--api` → the same.
  - Publication: 395,114 / 396,798 / 397,541 B per hour.
- `16:16` — **Base 23:00Z** issued: `created_at` 23:15:01.235Z, `committed_at` 23:16:18.717Z (**77.5 s**). Runtime 76.4 s; 853 forecasts (persistence 427, trend 426).
- `17:16` — **Base 00:00Z** issued: `created_at` 00:15:01.901Z, `committed_at` 00:16:19.609Z (**77.7 s**). Runtime 76.6 s; 854 forecasts (427 each).
  - Of the 834 ECCC forecasts, 0 are flagged `stale_inputs`.
  - Five consecutive base times so far (20, 21, 22, 23, 00Z), with 0 gap entries.
- `17:21` — **First live midnight rollover (F1, addendum 2 item 9).** ECCC `hourly` runs from `ingest_runs`, shown as run | start | status | files | fetched | rows | `listing_dir` | fallbacks:
  ```
  579 | 23:52:01 | ok | 429 |   0 |    0 | …/20261008/WXO-DD/hydrometric/csv/BC/hourly/ | []
  580 | 23:57:01 | ok | 429 |   0 |    0 | …/20261008/WXO-DD/hydrometric/csv/BC/hourly/ | []
  582 | 00:02:01 | ok | 429 | 429 | 4554 | …/20261009/WXO-DD/hydrometric/csv/BC/hourly/ | []
  584 | 00:07:01 | ok | 429 |   0 |    0 | …/20261009/WXO-DD/hydrometric/csv/BC/hourly/ | []
  585 | 00:12:01 | ok | 429 |   0 |    0 | …/20261009/WXO-DD/hydrometric/csv/BC/hourly/ | []
  587 | 00:17:02 | ok | 429 |   0 |    0 | …/20261009/WXO-DD/hydrometric/csv/BC/hourly/ | []
  ```
  - The new dated directory served the first run after 00:00Z. No run needed a fallback (no 404); `error_text` was empty and the ingest log had no ECCC warnings or errors between 23:50 and 00:21Z.
  - Run 582 downloaded all 429 files once (35 s). This was expected: `fetch_state` is keyed by URL (D-02.2 side effect).
  - On Oct 8, by contrast, the 00:03:50Z run failed on the `today/` 404.
  - The newest ECCC level at 00:21Z was 23:50Z. That is ECCC's normal publication lag, not a rollover gap; continuity past 00:00Z is checked after the 01:00Z publish.
  - The 30-day `daily/` listing is fetched only by the manual `backfill eccc-30d` command, not by the schedule, so it had no live rollover to observe. Its fallback is covered by `tests/test_eccc_rollover.py`.
- `17:25` — **AC-2, from outside the VM:** `python3 -I scripts/verify_ledger.py --api https://<host>` → `OK entries 4287, head aebed4bf…91de, by_type {genesis 1, model_card 3, forecast 4269, issuance 5, official_forecast 9}, anchors_checked 4` (2.2 s).
  - Tamper tests: `pytest tests/test_verify_script.py tests/test_ledger.py` → **12 passed**.
  - **Live tamper demo** on a clone of the published `ledger` branch (4 hourly files, 3,431 entries, 4 anchors). The clean copy verifies (`OK entries 3431, anchors_checked 4`). The tampered copies were made with throwaway scripts that are not committed, then checked with `verify_ledger.py --source files`:

    | Tamper | Verifier result |
    |---|---|
    | q0.5 at h1 of seq 865 changed by +0.1 m, hash left alone | `FAIL seq 865: entry_hash != sha256(...)` |
    | seq 870 deleted | `FAIL seq 871: expected seq 870` |
    | seq 866 and 867 exchange positions, seq fields renumbered | `FAIL seq 866: prev_hash does not link` |
    | seq 865 changed and the rest of that hour's file re-hashed | `FAIL seq 1719: prev_hash does not link` (the next file) |
    | seq 865 changed and every later hash recomputed up to the head | `FAIL seq 1718: anchor 21:30:00Z says 6a8f0bef…, chain has 17c3c960…` |

    - The last case **passes with `--no-heads`**: a self-consistent rewrite can only be caught by the external anchors. That is why the spec calls the ledger tamper-evident through its anchors.
    - Swapping two lines in a file while keeping their `seq` fields is not a change to the chain: the verifier orders by `seq`, and the result was OK.
- `17:30` — **AC-5:**
  - All 142 NOAA points held in `official_forecasts` (4 issuances: NKSW1 40 + 40, NRKW1 32 + 30) are in the ledger with the same `lid`, `issued_at`, `valid_at`, stage and flow. 0 are missing and 0 are duplicated.
  - The latest NRKW1 issuance (`issuedTime` 2026-10-08T15:12Z) compared with `api.water.noaa.gov/nwps/v1/gauges/NRKW1/stageflow/forecast` at 00:26Z: **all 30 points we hold match exactly** (stage ft and flow kcfs).
  - NOAA had appended 10 more points (Oct 16 06Z – Oct 18 12Z) after our 00:05Z fetch. The 00:35Z fetch and the 01:15Z run should add them, and the comparison will be repeated then.
- `17:31` — **AC-7 interim:** `scripts/audit_leakage.sql` over 4,269 forecasts (base times 20Z–00Z) → `0 | 0 | 0 | 0` of 34,152 horizons, in 4 min 36 s. The final run, after base 01:00Z, will cover all six base times.
- `17:40` — **First settled scores** (scorer run 9, 00:40:00Z, **7.0 s**): 852 candidates, giving 852 rows (426 per model) plus 426 `persistence-naive` rows. All are h = 1 from base 20:00Z, the only horizon settled so far (`valid_at + 3 h ≤ now`).
  - `/v1/scores/summary` totals: `scored 848, no_truth 4, stale_excluded 2`.
  - These numbers come from **one base time and one horizon**. They are measurements to check the pipeline, not results.

    | Model | Source | n | Mean CRPS (m) | MAE median (m) | 5–95 / 10–90 / 25–75 coverage | Paired CRPSS |
    |---|---|---|---|---|---|---|
    | persistence-naive | eccc | 413 | 0.0275 | 0.0275 | — | — |
    | persistence-v1 | eccc | 413 | 0.0152 | 0.0282 | 0.889 / 0.801 / 0.574 | 0.448 vs naive |
    | trend3h-v1 | eccc | 413 | 0.0174 | 0.0331 | 0.867 / 0.751 / 0.499 | −0.147 vs v1; 0.367 vs naive |
    | persistence-naive | usgs | 10 | 0.0073 | 0.0073 | — | — |
    | persistence-v1 | usgs | 10 | 0.0045 | 0.0058 | 1.0 / 0.8 / 0.5 | 0.391 vs naive |
    | trend3h-v1 | usgs | 10 | 0.0040 | 0.0060 | 0.9 / 0.8 / 0.4 | 0.108 vs v1; 0.457 vs naive |

  - **Rise events checked by hand:** 9 stations had a +0.25 m rise in their window, with 5 at +0.5 m and none at +1.0 m.
    - 7 of the 9 are **tidal**: Comox Harbour, Campbell River at Argonaut Wharf, and the lower Fraser at Steveston, North Arm, Deas Island and Port Mann, plus Campbell River at Campbell River.
    - Peace River above Alces is **regulated** (dam releases).
    - These are real changes in level, not data errors. But rise thresholds at tidal stations measure the tide, not flooding, so tidal and regulated stations need a flag before any rise-event skill is reported (open issue).
  - `forecast_scores` 565,248 B for 852 rows; `forecast_scores_naive` 335,872 B for 426 rows. These are small tables with fixed index overhead; the per-row size is re-measured at the end for the disk runway.
- `18:17` — **AC-1 met at base 01:00Z** (issuance seq 5144: `created_at` 01:15:00.475Z, `committed_at` 01:16:18.886Z, 77.3 s, 856 forecasts). The SQL (per base time: minutes after base, forecasts per model, and forecasts whose `created_at` differs from their issuance's):
  ```
  2026-10-08 20:00Z |  1.22 min | persistence-v1 426 | trend3h-v1 426 | 0
  2026-10-08 21:00Z | 15.01 min | 427 | 426 | 0
  2026-10-08 22:00Z | 15.01 min | 429 | 428 | 0
  2026-10-08 23:00Z | 15.02 min | 427 | 426 | 0
  2026-10-09 00:00Z | 15.03 min | 427 | 427 | 0
  2026-10-09 01:00Z | 15.01 min | 428 | 428 | 0
  forecasts with created_at − base_time > 30 min: 0; created_at < base_time: 0; created_at in the future: 0
  gap entries: 0; hours 20Z–01Z with neither an issuance nor a gap: none
  ```
  - `GET /v1/ledger/head` → `seq 5144, entry_hash 2c388b4e…3521`, with anchor `seq 4287 aebed4bf…91de, anchored 00:30:00Z, commit 425d36c2, status ok`.
  - Base 20:00Z was issued at 20:01Z by the first `floodlead issue` after deploy; every later base time was issued by the scheduler at HH:15.
- `18:17–18:21` — **AC-5 re-check → bug found and fixed (D-02.18).**
  - We still held 30 NRKW1 points while `stageflow/forecast` served 40. NWPS runs 592 (00:35Z) and 601 (01:05Z) inserted 0 rows, because `stageflow` itself returned 30.
  - Fix: forecast rows now come from `stageflow/forecast`.
  - `ruff` clean; `pytest -q` → **95 passed**, 4 deselected; `pytest -m live -k nwps` → 1 passed.
  - Commit `3314532`, pushed to PR #4 (open), then deployed at 01:21Z (`docker compose build -q ingest api && docker compose up -d ingest api`). The ingest container reports `FLOODLEAD_GIT_SHA=3314532…`, and the scheduler restarted with the same 8 jobs.
- `18:35` — **NWPS run after the D-02.18 deploy:** run 608 (scheduler start, 01:21:19Z) fetched 18 payloads and inserted the **10 missing NRKW1 points** (`points 40, new_rows 10`). Run 615 (01:35Z) inserted 0 new rows, as expected. `official_forecasts` NRKW1 15:12Z: 40 points ending Oct 18 12Z. They go into the ledger at the 02:15Z run.
- `18:38` — **Incident caused by the worker: PostgreSQL was OOM-killed and restarted.**
  - **Cause:** the first version of `scripts/replay_check.sql` (for AC-9) used correlated subqueries against the `observations` hypertable (1,150 chunks) with no constant time bounds. The memory cgroup of the db container (limit 2.5 GiB) hit its limit and the kernel killed a backend at 01:38:14Z (`dmesg`: `Memory cgroup out of memory: Killed process … (postgres)`).
  - **Recovery:** the postmaster terminated all backends and ran crash recovery from WAL (`redo done … elapsed 0.08 s`). It accepted connections again at **01:38:16Z (≈ 2 s)**.
  - **Data:** no committed data was lost.
    - `floodlead ledger verify` → `ok True, entries 5144`, same head `2c388b4e…3521`.
    - The last ingest run (616, ECCC) had committed at 01:37:51Z. No issuance, anchor or migration was running.
  - **Knock-on:** each pool then handed one dead connection to its next user.
    - The API returned one 500 at 01:38:34Z.
    - Four jobs failed once: scorer 01:40, ECCC 01:42 and 01:47, USGS 01:47. Each case lost nothing:
      - **Scorer:** the restart-time run 10 (01:21Z) had already scored those 853 forecasts, and run 11 had 0 left to score.
      - **ECCC:** the files roll; at 01:52 they were unchanged since 01:37.
      - **USGS:** the 01:53 run fetched its rolling window (21 rows).
  - **Fix (`97c4a52`, deployed 01:53:49Z from PR #4):**
    - `db.pool()` now passes `check=ConnectionPool.check_connection`.
    - New test `test_pool_replaces_a_connection_killed_by_a_server_restart` kills a pooled backend: it **fails without the fix and passes with it**.
    - `pytest -q` → **96 passed**.
    - After the restart, all 5 start-up runs and scorer run 11 were `ok`.
  - **Rule from now on:** ad-hoc queries on production touch the hypertable only through constant time bounds, or through one scan into a temp table, and run with a `statement_timeout`. `scripts/replay_check.sql` now copies the two stations' rows (660,124) into a temp table first.
- `18:55` — **AC-9, replay = independent SQL.** `scripts/replay_check.sql` uses the D-02.4 definitions as one SQL query and shares no code with `replay.py`. Run on production: 16.4 s; peak db container memory 1.12 GiB, sampled every 2 s.
  ```
  events_total 20 | events_with_gauge 13 | events_with_overflow 7
  onset_ft min 146.2 | median 147.56 | max 148.44 ; hours_after_minor min 0.08 | median 4.92 | max 6.42
  peaks_with_overflow_ft    {146.6,147.26,148.13,148.53,148.85,150.44,150.76}
  peaks_without_overflow_ft {146.73,146.86,146.93,147.04,147.18,147.3}
  ```
  - `/v1/replay/overflow` `.summary` gives **the same values for every field**.
- `19:17` — **Base 02:00Z** issued (seq 5998): `created_at` 02:15:01.453Z, `committed_at` 02:16:25.097Z (83.6 s); 852 forecasts (426 each). Seven consecutive base times, 0 gaps.
- `19:17` — **AC-5 met.**
  - The run first appended **seq 5145**, `official_forecast` NRKW1, `issued_at` 2026-10-08T15:12Z, `part "added points"`, `fetched_at` 01:21:19Z, 10 points, `raw_sha256 0d4b9790…0949` (the `stageflow/forecast` payload).
  - All 152 held points are in the ledger, with 0 missing and 0 duplicated.
  - Point-for-point comparison with `api.water.noaa.gov/nwps/v1/gauges/<lid>/stageflow/forecast` at 02:17Z:
    ```
    NRKW1 issuedTime 2026-10-08T15:12:00Z | NOAA points 40 | ledger points 40 | mismatches 0
    NKSW1 issuedTime 2026-10-08T15:12:00Z | NOAA points 40 | ledger points 40 | mismatches 0
    ```
    Stage ft and flow kcfs are compared as JSON numbers, with no rounding.
- `19:20` — **AC-7 audit in a safe form.** `scripts/audit_leakage.sql` now reads constant time bounds from the ledger (`\gset`), copies the level rows in that range into a temp table (57,214 rows), and audits against that, with a `statement_timeout`. The checks are unchanged. Result over **5,977 forecasts (7 base times, 20Z–02Z)** → `0 | 0 | 0 | 0` of **47,816** horizons, in **6.7 s** (was 4 min 36 s). Every forecast has `inputs_n > 0`, so 0 count mismatches also shows the temp table held the matching rows. It is re-run at PR time.
- `19:30` — README "What works now" brought up to date for part 2 (contract-files table updated).

- `20:40` — **Scorer run 13 (03:40:00Z):** 3,415 candidates, **1,706 scored, 9.5 s**. Totals in `forecast_scores`: **5,097 scored**, 23 `no_truth`, 8 stale-input excluded; plus 2,562 `persistence-naive` rows. Settled so far: **h1 and h3 only** (base times 20Z–02Z for h1, 20Z–00Z for h3). The next horizons settle later: h6 of base 20Z (valid 02Z, settled 05Z) is scored at the **05:40Z** run, and h12 at the **11:40Z** run. The first NOAA matched pair (base 00Z, h6, valid 06Z) settles at 09:00Z and is scored at the **09:40Z** run; `/v1/scores/official` says so in its `note`. So AC-8 is **PARTIAL** at PR time: 2 of the 4 required horizons.
  - `/v1/scores/summary` (scorer run 13): paired CRPS (m, quantile score), CRPSS and n pairs. First-day numbers from 7 base times, not claims:

    | Source | h | Comparison | n pairs | CRPS model / reference | CRPSS |
    |---|---|---|---|---|---|
    | ECCC | 1 | persistence-v1 vs naive | 1,659 | 0.0180 / 0.0285 | 0.369 |
    | ECCC | 1 | trend3h-v1 vs naive | 1,656 | 0.0124 / 0.0244 | 0.491 |
    | ECCC | 1 | trend3h-v1 vs persistence-v1 | 1,656 | 0.0124 / 0.0139 | 0.107 |
    | ECCC | 3 | persistence-v1 vs naive | 827 | 0.0355 / 0.0587 | 0.396 |
    | ECCC | 3 | trend3h-v1 vs naive | 827 | 0.0361 / 0.0587 | 0.385 |
    | ECCC | 3 | trend3h-v1 vs persistence-v1 | 827 | 0.0361 / 0.0355 | −0.018 |
    | USGS | 1 | persistence-v1 vs naive | 40 | 0.0037 / 0.0049 | 0.243 |
    | USGS | 1 | trend3h-v1 vs persistence-v1 | 40 | 0.0040 / 0.0037 | −0.094 |
    | USGS | 3 | persistence-v1 vs naive | 20 | 0.0066 / 0.0072 | 0.084 |
    | USGS | 3 | trend3h-v1 vs persistence-v1 | 20 | 0.0066 / 0.0066 | 0.002 |

  - Interval coverage, ECCC (nominal 0.90 / 0.80 / 0.50): persistence-v1 h1 0.884 / 0.796 / 0.590, h3 0.877 / 0.791 / 0.589; trend3h-v1 h1 0.851 / 0.745 / 0.476, h3 0.866 / 0.757 / 0.487. Median-MAE (m), ECCC h1: naive 0.0285, persistence-v1 0.0297, trend3h-v1 0.0222.
  - **The means rest on a few stations.** Median CRPS is 1–2 mm, against 12–36 mm means. The largest errors are at tidal or regulated ECCC stations (08MH053, 08MH126, 08HB087 and others), and at **08LF027** (Deadman River above Criss Creek). There the level stepped from a flat 0.142 m to 1.589 m at 22:25Z, then to a flat 4.257 m at 23:05Z. This looks like a gauge or datum change, not water. Two persistence-v1 h1 forecasts there (bases 22Z and 23Z, CRPS 4.1 and 2.7 m) have no trend3h-v1 pair. They alone shift the ECCC h1 persistence-v1 mean from 0.0139 m (the subset paired with trend3h-v1) to 0.0180 m. A step-change and tidal flag is needed before any skill number is quoted (open issues).
- `20:42` — **Disk runway re-estimated from measured growth.** Same query as the 01:35:55Z baseline (`pg_database_size`, ledger and score table sizes, observation chunk sizes, `du -sb` archive, `df`), re-run at 03:42:03Z (2.10 h later):

  | Part | 01:35:55Z | 03:42:03Z | Δ | Per day |
  |---|---|---|---|---|
  | Database | 4,790,656,023 | 4,801,223,703 | +10,567,680 | ≈ 121 MB (this window) |
  | – ledger_entries | 9,674,752 (5,144 entries) | 12,943,360 (6,850) | +3,268,608 for 2 issuances | ≈ 39 MB |
  | – scores (both tables) | 1,671,168 (2,558 rows) | 4,677,632 (7,682) | +3,006,464 = 587 B/row | ≈ 144 MB at steady state |
  | – observation chunks | 4,709,515,264 | 4,712,611,840 | +3,096,576 | ≈ 35 MB |
  | Archive | 110,308,770 | 113,804,646 | +3,495,876 | ≈ 40 MB |
  | `df` used | 22,134,919,168 | 22,093,078,528 | −41,840,640 | (not used) |

  - Scores at steady state: 10,224 rows/h (852 forecasts + 426 naive, × 8 horizons) × 587 B ≈ 144 MB/day. In this window only h1 and h3 were being scored.
  - Total ≈ **270 MB/day**. 80 % of the 102.9 GB disk leaves 60.2 GB → **≈ 220 days (mid-May 2027)**. This replaces the Oct 8 estimate (≈ 230 MB/day, ≈ 270 days) in `architecture.md`.
  - `df` fell in the window, from Docker and WAL churn, so the estimate uses table, chunk and archive sizes instead. A 2-hour window means ±30 % is normal.
- `20:43` — **Final checks at PR time.**
  - `scripts/audit_leakage.sql` (safe form, 64,668 temp rows) → `6828 | 0 | 0 | 0 | 0 | 54624`: 0 violations over **6,828 forecasts (8 base times, 20Z–03Z)** and 54,624 horizons, in **6.64 s**.
  - `ruff check .` → `All checks passed!`.
  - `pytest -q` (DB tests run against the local test database) → **96 passed, 4 deselected** in 11.1 s.
  - `scripts/verify_ledger.py --api https://<host>` → `OK entries 6850, head 53103c11…e752, by_type {genesis 1, model_card 3, forecast 6828, issuance 8, official_forecast 10}, anchors_checked 8` (1.9 s).
  - `--source github` → the same, from 8 files (2.7 s).
  - Health green, with issuer, scorer and anchor all green.
  - Base 03:00Z (seq 6850): `created_at` 03:15:00.101Z, `committed_at` 03:16:14.006Z (73.9 s). That makes **8 consecutive base times, 0 gaps**.
- `20:52` — PR #4 marked ready for review, with the STAGE REPORT as its body. The last step follows: `sudo reboot`, once (addendum 1 item 5). Nothing is run after it. The supervisor checks recovery from outside.

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
| First anchor | 856 entries, 395,114 B jsonl.gz, commit `28aefd8` | anchor job | 20:15Z |
| Publication rate (estimate from one hour) | ≈ 0.4 MB/h → ≈ 285 MB/month on the `ledger` branch | × 720 | 20:15Z |
| F2 before (one ECCC refresh) | 554,126 row updates, +70,313 dead tuples, WAL 139,090,872 B (12.6 min window) | `pg_stat_user_tables`, `pg_current_wal_lsn()` | 20:25–20:38Z |
| F2 after (one ECCC refresh) | 0 row updates, +0 dead tuples, WAL 15,733,024 B (28.3 min window, more jobs) | same | 20:39–21:07Z |
| Leakage audit | 852 forecasts, 0 violations, 0 of 6,816 horizons < 30 min | `scripts/audit_leakage.sql` (3 min 11 s) | 20:47Z |
| AC-6 reproduction | 3/3 forecasts: input_hash and 8/8 medians match from the public API | `scripts/reproduce_forecast.py` (2.3 s) | 20:43Z |
| Issuance commit lag (`committed_at − created_at`) | 69.4–83.6 s over 6 base times (22Z 69.4, 23Z 77.5, 00Z 77.7, 01Z 77.3, 02Z 83.6, 03Z 73.9); 20Z and 21Z predate the field | `committed_at` in each issuance entry | 22:16–03:16Z |
| Forecasts per base time | 851–856 (426–429 stations × 2 models), 8 base times 20Z–03Z | ledger | 03:16Z |
| Anchors | 8 of 8 `ok`; hourly files 394,993–397,541 B | `ledger_anchors` | 20:15–03:30Z |
| Publication rate (measured, 8 h) | ≈ 396 kB/h → ≈ 285 MB/month on the `ledger` branch | mean of 8 files × 720 | 03:30Z |
| Scorer runtime | 0.7–9.5 s per run (13 runs); run 13: 3,415 candidates, 1,706 scored, 9.5 s | `scorer_runs` | 03:40Z |
| Settled scores | 5,097 scored, 23 no_truth, 8 stale excluded; 2,562 naive rows; h1 and h3 only | `forecast_scores`, `/v1/scores/summary` | 03:40Z |
| Verifier from outside | `--api` 6,850 entries 1.9 s; `--source github` 8 files 2.7 s | `time` | 03:44Z |
| Leakage audit (final, safe form) | 6,828 forecasts, 0 violations, 0 of 54,624 horizons < 30 min, 6.64 s | `scripts/audit_leakage.sql` | 03:43Z |
| AC-5 point-for-point | NRKW1 and NKSW1 15:12Z issuances: 40/40 points each, 0 mismatches; 152/152 held points in the ledger | `tools/ac5_compare.py` (scratch) vs `stageflow/forecast` | 02:17Z |
| Replay independent SQL | 16.4 s; peak db container memory 1.12 GiB | `scripts/replay_check.sql`, `docker stats` every 2 s | 01:55Z |
| Disk growth (measured, 2.1 h) | ≈ 270 MB/day (archive 40, observations 35, ledger 39, scores 144 at steady state, other 14) → ≈ 220 days to 80 % | sizes at 01:35:55Z vs 03:42:03Z | 03:42Z |
| DB crash recovery (incident) | OOM kill 01:38:14Z → accepting connections 01:38:16Z (≈ 2 s); 0 committed data lost | db logs, `floodlead ledger verify` | 01:38Z |

## Acceptance criteria

| AC | Result | Evidence |
|---|---|---|
| AC-1 Hourly issuance | **PASS** | 8 consecutive base times, 20Z Oct 8 to 03Z Oct 9, 0 gaps, 0 `gap` entries needed. 851–856 forecasts each (426–429 stations × 2 models). `created_at − base_time` 1.2–15.0 min. 0 entries before base, 0 late, 0 with future inputs. `/v1/ledger/head` → seq 6850, anchored 03:30Z, commit `90126fe5`. Work log `18:17`, `19:17`, `20:43` |
| AC-2 Chain verifies from outside; tamper tests | **PASS** | `verify_ledger.py --api` → OK 6,850 entries, 8 anchors checked. `--source github` → the same from 8 files. `pytest tests/test_verify_script.py tests/test_ledger.py` → 12 passed (golden vector, tamper detection, the genesis check). Live demo on copies of the published files: 5 of 5 tampers caught; the self-consistent rewrite is caught only by the anchors. Seq 1 must be genesis with a zero prev_hash in all three verifiers (addendum 2 item 5). Work log `17:25`, `20:43` |
| AC-3 UPDATE/DELETE/TRUNCATE fail | **PASS** (part 1) | Each statement rejected inside `BEGIN … ROLLBACK` on production. Work log `13:44` |
| AC-4 ≥ 3 anchors match the chain | **PASS** | 8 hourly anchors 20:15Z–03:30Z, all `ok`, all written by the anchor job with `LEDGER_GITHUB_TOKEN`. All match the chain (`anchors_checked 8, anchors_outside_range 0`). Commits `28aefd89`, `debf0dd2`, `0f178823`, `ad595fd4`, `425d36c2`, `1a700584`, `974b615f`, `90126fe5` on the `ledger` branch |
| AC-5 NOAA issuances in the ledger | **PASS** | 152/152 held points are in the ledger (10 `official_forecast` entries). The latest NRKW1 and NKSW1 issuances (15:12Z) equal `stageflow/forecast` point for point, 40/40 each, 0 mismatches. This needed the D-02.18 fix: our endpoint had cut NRKW1 at +7 days. Work log `18:17–18:21`, `19:17` |
| AC-6 3 forecasts reproduced from the public API | **PASS** (part 1) | `scripts/reproduce_forecast.py --n 3`: input_hash and 8/8 medians match. Work log `13:41–13:44` |
| AC-7 Leakage audit | **PASS** | 6,828 forecasts (8 base times): 0 inputs after `created_at`, 0 rows not yet visible, 0 count mismatches, 0 of 54,624 horizons with `valid_at − created_at` < 30 min. 6.64 s. Work log `20:43` |
| AC-8 Scores | **PARTIAL** | ≥ 5,000 settled scores: **met**, 5,097 at 03:40Z. Paired CRPS, MAE and coverage with n for both models: given by `/v1/scores/summary`, but only at **2 horizons (h1, h3)**. The other horizons have not settled yet: h6 is scored at 05:40Z, h12 at 11:40Z (the 4th horizon), h18 at 17:40Z. NOAA matched pairs: none yet; the first settles at 09:00Z and is scored at 09:40Z Oct 9, as `/v1/scores/official` states. The scorer runs hourly, so this completes without new code. Work log `20:40` |
| AC-9 Demo path | **PASS** | Screenshots of all 4 pages at 1280 px and 375 px. `scrollWidth` = viewport on every page. 0 page errors, including with `en-US@posix`. Replay = independent SQL on every field. Snapshot mode with `python3 -m http.server -d web 8080` works, with its banner and ages counted from the snapshot. Work log `13:07–13:10`, `15:00–15:08`, `18:55` |
| AC-10 F1 and F2 | **PASS** | F1: fallback tests (`tests/test_eccc_rollover.py`); live dated-path check; the first live midnight rollover was clean (work log `17:21`). F2: one ECCC refresh went from 554,126 row updates to 0, and WAL from 139.1 MB to 15.7 MB; an identical re-fetch writes 0 rows (work log `14:07`, measurements) |
| AC-11 ruff and pytest | **PASS** | `ruff check .` → All checks passed. `pytest -q` → 96 passed, 4 deselected (live), DB tests run. `pytest -m live -k nwps` → 1 passed. Work log `20:43`, `18:17–18:21` |
| AC-12 Decisions, stage doc, contracts, runway | **PASS** | 18 decisions (D-02.1–D-02.18). The stage doc is in 25 of the 29 part-2 commits on top of `main` (2 of the 29 are merges of `main`; the count includes this commit) and in 5 part-1 commits, spread from Oct 8 19:41Z to the final commit on Oct 9. README, architecture, evaluation, data-contract, ledger-spec and product.yaml are updated (table below). Disk runway re-estimated from measured growth: ≈ 270 MB/day, ≈ 220 days to 80 % (work log `20:42`) |

## Contract files changed

| File | What changed | Why |
|---|---|---|
| `README.md` | Live URL at the top (F3). "Brief (AI-drafted at the author's request)" link. "Build Session 2 — working app" section with the computed replay table, run-locally steps, works-now/remains, screenshots. No-snapshot wording | Parts F/G, F3, addendum items 2 and 4 |
| `architecture.md` | No off-machine copy (snapshots declined). Forecast ledger, F2 write rules, growth with ledger and scores (~230 MB/day, ~270 days to 80 %, estimate). Components (ledger, issuer, anchor, scorer, static web). Stage 2 tables as built. API rows for replay, forecast, ledger and scores. Scheduler jobs. Cost without snapshots | Facts changed in this stage |
| `evaluation.md` | Live ledger cadence, horizons, leakage, the new stale rule (150/120 min, replacing "> 30 min"), hourly anchors and published entries, baseline definitions incl. the 6 h trend cap, scoring rules (quantile-score CRPS and its measured bias, event window, paired skill, ≥ 30 events), NOAA matched comparison | Prompt "Documentation" |
| `data-contract.md` | Lineage: forecasts as ledger entries with `input_hash` and library hash; F2 meanings and `payload_coverage` | Facts changed |
| `docs/ledger-spec.md` | New: public specification with golden vector | Part A.8 |
| `docs/stages/STAGE-01-live-archive.md` | Dated note on open issue 2 (snapshots declined) | Addendum item 2 |
| `product.yaml` | `status: spec → prototype`, `maturity 1 → 2` (`Prototype`), output: the overflow-watch app | Status changed: a deployed app and hourly forecasts (values from the schema's `status` enum: idea, spec, prototype, mvp, showcase, active, archived) |
| `README.md` (part 2) | "Check the forecasts yourself": both verifier modes, the reproduction script, the scores endpoint | Part G / AC-2 |
| `README.md` (part 2) | "What works now" updated for Oct 9: scoring, anchors and publication, verifier, NOAA forecasts in the ledger. Next steps. Statement that scores cover about one day, so no skill is claimed | Facts changed |
| `docs/ledger-spec.md` (part 2) | `created_at` defined exactly; `inserts_started_at` and `committed_at`; model-card supersession; `official_forecast` parts, with the NRKW1 7-day-cut explanation | Addendum 2 items 4 and 6; D-02.18 |
| `data-contract.md` (part 2) | NWPS access method: `stageflow/forecast` for official forecasts (the combined endpoint cuts at +7 days) | D-02.18 |
| `architecture.md` (part 2) | `growth_with_ledger` replaced by the measured rate: ≈ 270 MB/day, ≈ 220 days to 80 % (scores are the largest part) | AC-12, measured |
| `evaluation.md` (part 2) | `persistence-naive` is the headline baseline; `persistence-v1` described as level + typical change | D-02.17 |

## Open issues and handoff to next stage

1. **AC-8 completes after the PR.** The h6 scores arrive at the 05:40Z run, the first NOAA matched pair at 09:40Z, and h12 (the 4th horizon) at 11:40Z Oct 9. Check them with `curl https://<host>/v1/scores/summary` and `/v1/scores/official`. No code change is expected.
2. **No skill claim yet.** Scores cover about 8 hours of base times. The means rest on a few tidal or regulated stations and on one apparent gauge step (08LF027: 0.142 → 1.589 → 4.257 m, flat between steps). Stage 3 needs a step-change flag and a tidal/regulated flag for truth and for training. Report skill per station class, with medians, before quoting any CRPSS.
3. **CRPS is a 7-quantile score.** It is about 19 % below the exact CRPS for a calibrated normal forecast (D-02.13). The bias is the same for every model, so paired skill is fair, but absolute CRPS values are not comparable with other studies.
4. **Database memory and ad-hoc queries.** `observations` has 1,150 chunks and the db container has a 2.5 GiB limit. A query without constant time bounds can plan every chunk and be OOM-killed; that happened at 01:38Z (the worker caused it, and no data was lost). Rule: constant bounds or one scan into a temp table, with `statement_timeout`. Stage 3 should consider larger chunks or compressing old chunks, and a lower `work_mem` for ad-hoc roles. At the restart, TimescaleDB logged "background worker limit of 2 exceeded"; `timescaledb.max_background_workers` should be raised when the db is next recreated.
5. **Scorer runtime grows with the candidate set.** 9.5 s at 3,415 candidates. At steady state (48 h horizon, about 52 base times × 852 forecasts ≈ 44k candidates), linear scaling gives about 2 min (estimate). Measure it again in Stage 3; restrict candidates to forecasts with unscored, settled horizons if needed.
6. **Disk.** About 270 MB/day, about 220 days to 80 % (measured over 2.1 h). Scores are 144 MB/day of that and are derived data, so compressing or thinning old scores is the first lever.
7. **No off-machine copy** of the raw archive or the database (snapshots declined; an accepted risk). The ledger itself is published hourly to the `ledger` branch, so the track record survives the VM.
8. **The `ledger` branch grows by about 285 MB/month** (measured over 8 h). This is under the ~1 GB/month limit, but if it becomes a problem, the alternatives are daily files, or a rolling window plus daily consolidations, published as a decision.
9. **Anchors are as strong as GitHub's history.** Anyone who can force-push the `ledger` branch could rewrite both the files and the heads. The anchor job never force-pushes. Branch protection on `ledger` (no force-push, no deletion) is a human action (Needs human).
10. **ECCC `daily/` is not scheduled.** Only `hourly/` is polled. The daily files are not needed for the hourly forecasts.
11. **Deploys:** from Stage 3 on, only from a branch with an open PR (addendum 2 item 7). Part-2 code first ran in production before PR #4 existed (addendum 2 item 7). Every deploy after PR #4 opened (21:50Z) was from its branch, the last two being `3314532` and `97c4a52`.
12. **Reboot test.** This is the last step of this stage, after this report. The supervisor checks from outside that health returns to green, that hourly issuance continues, and that any base time missed during the reboot appears as a `gap` entry.
