# Stage 01 — Foundation and live archive

> Living document. Written while the stage is built, committed with the code. Newest work-log entries at the bottom.

| | |
|---|---|
| Branch | `stage-01-live-archive` |
| Started | 2026-10-07 13:34 PT |
| Finished | (fill at end) |
| Prompt | `docs/build/prompts/STAGE-01-live-archive.md` |
| Status | in progress |

## Goal

Start keeping the river data that would otherwise disappear, and make it checkable from outside. ECCC's Datamart only holds 30 days of real-time BC gauge data. This stage ingests three public sources continuously on the VM:

- ECCC Datamart hourly CSVs for every BC gauge;
- USGS 15-min stage and flow for the Nooksack/Sumas gauges that flood Sumas Prairie;
- NOAA NWPS official forecasts and flood categories.

Every raw payload is archived immutably on local disk with its sha256. The ECCC 30-day files and the USGS history are backfilled. A read-only HTTPS API lets anyone see what we hold and how fresh it is. The user value: the forecasts and ledger in later stages need this data underneath them, and every hour without archiving is history that cannot be recovered.

## Inputs read

- `CLAUDE.md` (updated on `main`): the raw archive is `ARCHIVE_DIR` (default `/srv/floodlead/archive`), never deleted or overwritten. `pg_dump` goes to `/srv/floodlead/backups/` before any migration that touches existing tables.
- `AGENTS.md`: licensed sources only (records 1, 6, 7 in `data-contract.md` cover ECCC, USGS and NWPS), no leakage, attribution on every response.
- `docs/build/PLAN.md`, "Facts the supervisor verified". ECCC OGC real-time is ~4 h behind, so it is used for station metadata only. Datamart hourly files are ~1 h behind and rewritten at :31. USGS North Cedarville stage dates from 2007-10-01. Everson's 2021 peak was 52,300 cfs. NRKW1 flood stages are given.
- `docs/build/prompts/STAGE-01-live-archive.md`: priorities P1–P4, data model, schedules, archive layout, API, 12 acceptance criteria.
- `docs/stages/STAGE-00-environment.md` (QA passed): e2-standard-2 (2 vCPU, 7.7 GiB, no swap), 92 GB free, ports 80/443/5432/8000 free. Datamart uses a fixed `-08:00` offset. Git identity is unset on the VM.
- `data-contract.md`, `architecture.md`, `README.md`, `evidence/` (`pull_gauges.py` uses the OGC API; `station_summary.csv` reports 1 sentinel row at 08MH001 and ±99999 sentinels in the real-time feed).
- **Re-checked at start (13:33 PT, VM rebooted 4 min earlier onto kernel 7.0.0-1013-gcp):**
  - `docker run --rm hello-world` works **without sudo** (user in group `docker`; Docker 29.1.3, Compose 2.40.3).
  - `gcloud compute addresses list` shows `floodlead-ip` reserved and `IN_USE`, so the external IP is now static. `PUBLIC_HOSTNAME` resolves to it.
  - `ACME_EMAIL` is still **absent** from `.env`.
  - **No snapshot schedule** is attached to the boot disk yet (`disks describe … --format='value(resourcePolicies)'` → empty).
  - Swap is still 0 B. Ports 80/443/5432/8000 are still free.

## Plan

1. Branch, open this doc, commit and push (first).
2. Create a 4 GiB swapfile and add it to `/etc/fstab` (prompt requirement; decision record).
3. Probe each source once to confirm its live payload shapes and commit trimmed real fixtures. USGS OGC `continuous` items (paging, limits, rate-limit headers, deprecation notices), NWPS `gauges/{lid}` (flood categories, `usgsId`), and the ECCC hourly and daily CSVs.
4. Scaffold `src/floodlead/` with `uv`: settings, DB helpers, SQL migrations and runner, raw-archive writer (gzip, atomic, `0444`, sha256 dedupe), set-based upserts with revision capture, `ingest_runs`, JSON logs, CLI `floodlead`.
5. **P1:** ECCC Datamart live ingestion (listing every 10 min, conditional GETs, only changed files). Compose `db` (pinned TimescaleDB/PG16 image, memory-limited) and `ingest` with `restart: unless-stopped`. Bring them up and verify rows plus archive files.
6. **P2:** ECCC 30-day backfill as a one-off compose service. USGS live (15 min, rolling 6 h) and NWPS live (30 min, store every `issuedTime`). USGS history backfill (chunked, resumable cursor, ≤ 4 parallel requests). Station metadata daily from the ECCC OGC API, USGS and NWPS.
7. **P3:** FastAPI read-only API (`/v1/health`, stations, observations, official forecasts, `/docs`, attribution, CORS, rate limit) behind Caddy with automatic HTTPS for `PUBLIC_HOSTNAME`. Report certificate issuance as the inbound proof.
8. **P4:** tests on real fixtures (parsers, conversions, sentinels, `-08:00`, upsert idempotency and revisions against a disposable DB, API contract) plus `@pytest.mark.live`. Run `ruff` and `pytest`. Update `architecture.md`, `README.md` and `data-contract.md`. Run the restart/reboot check, collect AC evidence, open the PR and write the STAGE REPORT.

## Decisions

### D-01.1 — 4 GiB swapfile

- **Context:** 7.7 GiB RAM and no swap. The DB (≤ 2.5 GiB), ingest (≤ 1 GiB), API, Caddy, backfill containers and this Claude Code session share it. With no swap, a burst means the OOM killer.
- **Options considered:** (a) no swap, rely on container limits; (b) 4 GiB swapfile on the boot disk (prompt requirement); (c) resize the VM (costs money, human decision).
- **Choice:** (b). `fallocate -l 4G /swapfile`, `chmod 600`, `mkswap`, `swapon`, plus `/swapfile none swap sw 0 0` in `/etc/fstab`. Swappiness left at the Ubuntu default (60).
- **Why:** it makes memory pressure slow instead of fatal. It costs 4 GB of the 92 GB free disk.
- **Reversibility / cost:** `swapoff /swapfile`, remove the fstab line, delete the file.
- **Follow-ups:** watch `free -h` during backfills. Sustained swap use means the memory limits need revisiting.

### D-01.2 — Polling with conditional GETs, not AMQP

- **Context:** `architecture.md` assumed an AMQP consumer. Datamart freshness is set by the hourly file rewrite (all 429 hourly files stamped `:31`; the newest row is about 1 h old when written).
- **Options considered:** (a) AMQP `sarracenia`/`aio-pika` subscription; (b) poll the listing every 10 min and download only files whose listing time is newer than the stored `Last-Modified`, using `If-Modified-Since`.
- **Choice:** (b). The ECCC job runs at :03/:13/…/:53, so the :33 run catches each rewrite about 2 min after publication.
- **Why:** freshness is the same because the files only change hourly, and polling is far simpler to debug and resume. Conditional GET verified: `If-Modified-Since` on an unchanged file returned `304` (Stage 0 probe; and run 5 below: `unchanged 429`, `fetched 0`, 0.45 s).
- **Reversibility / cost:** an AMQP trigger could later replace the timer. Parsing and storage are unaffected.
- **Follow-ups:** none.

### D-01.3 — Pinned images

- **Context:** reproducible deploys on a production VM.
- **Choice:** `timescale/timescaledb:2.30.2-pg16` (latest 2.x pg16 tag on Docker Hub, published 2026-09-29), `caddy:2.11.7-alpine` (2026-10-06), `python:3.12.15-slim-bookworm`, and the uv binary from `ghcr.io/astral-sh/uv:0.12.23` (same version as on the VM). Python deps are locked in `uv.lock` (31 packages).
- **Options considered:** floating tags (`latest-pg16`, `2-alpine`) vs exact tags.
- **Why:** exact tags mean a restart never silently upgrades the database engine.
- **Reversibility / cost:** change the tag, then pull and recreate. TimescaleDB minor upgrades need `ALTER EXTENSION timescaledb UPDATE`.
- **Follow-ups:** Stage 8 (hardening) can add digest pinning.

### D-01.4 — Station ID scheme and units

- **Context:** two countries, three agencies, two unit systems.
- **Choice:** namespaced IDs `eccc:<station number>` and `usgs:<site number>`. NWPS gauges (`NRKW1`, …) are not separate stations: they attach to the USGS station given by NWPS `usgsId`, as `links.nwps_lid` and `official_thresholds`. `value` is SI (m, m³/s); `raw_value` and `raw_unit` keep exactly what was published. Factors: ft × 0.3048, ft³/s × 0.028316846592.
- **Why:** one namespace prevents collisions, and keeping raw values means a conversion bug can always be fixed from the database without re-fetching.
- **Reversibility / cost:** IDs are primary keys, so renaming them later is costly. This scheme is fixed from now on.
- **Follow-ups:** forecasts in Stage 2 key on these IDs.

### D-01.5 — Sentinel rule (overrides the prompt's "|value| ≥ 9999" for flows)

- **Context:** the prompt asks to flag `|value| ≥ 9999` plus documented codes. That rule would flag real flows: the Nooksack at Everson reached **52,300 ft³/s** on 2021-11-15 (verified in the USGS payload, below), and the Fraser at Hope has exceeded 10,000 m³/s in freshet (an assumption from general hydrology, not measured here).
- **Options considered:** (a) `|v| ≥ 9999` for everything; (b) per-parameter rule.
- **Choice:** (b). Flag a row when the raw value is one of the documented codes {±99999, ±999999, −9999} (ECCC real-time ±99999, USGS legacy −999999, NWS/USGS −9999); or for **levels** when `|v| ≥ 9999`; or for **flows** when `|v| ≥ 99999`. Sentinel rows are kept with `raw_value` verbatim, `value = NULL`, `is_sentinel = true`. The API's default series excludes them.
- **Why:** it never turns a real flood flow into "missing", and a sentinel can never be read as a real value (value is NULL).
- **Reversibility / cost:** `raw_value` is kept, so flags can be recomputed with one UPDATE in a migration.
- **Follow-ups:** sentinel counts are reported under AC-8.

### D-01.6 — Revisions, idempotency and an out-of-order guard

- **Context:** ECCC data are provisional and revised. The 30-day "daily" files (rewritten once a day at ~08:18 UTC) overlap the hourly files (rewritten hourly). Ingesting an older daily file after a newer hourly one would flip values back, and the next hourly file would flip them forward again: false revisions.
- **Choice:**
  - Set-based upsert per payload: COPY into a temp staging table, then:
    1. bump `last_seen_at` on identical rows;
    2. append changed rows to `observation_revisions` (old and new value, quality, sentinel flag, raw object ids) and update them, incrementing `revision_count`;
    3. insert new rows.
  - "Changed" means raw value, unit, quality fields or sentinel flag differ.
  - Each row stores `published_at` (the payload's HTTP `Last-Modified` for ECCC, the per-value `last_modified` for USGS). An incoming version published **before** the stored one is counted as `stale` and not applied.
  - Writers serialise per station with `pg_advisory_xact_lock(hashtext(station_id))`, so live ingest and backfills cannot deadlock or interleave.
  - `observation_revisions`, `raw_objects` and `official_forecasts` have triggers that reject UPDATE and DELETE.
- **Why:** re-fetching identical data changes only `last_seen_at`. Verified: forced re-download of all 429 hourly files → `rows_unchanged 563393`, `rows_inserted 0`, `rows_updated 0` (run 3). The guard makes revision counts mean something.
- **Reversibility / cost:** `published_at` is an extra column beyond the prompt's minimum model.
- **Follow-ups:** Stage 2 features must use the value as first seen (`observation_revisions` holds the history).

### D-01.7 — Raw archive layout and immutability

- **Choice:**
  - Layout: `$ARCHIVE_DIR/raw/<source>/YYYY/MM/DD/HH/<name>.<sha8>.gz`, by UTC fetch time.
  - gzip with `mtime=0`, so the archived bytes depend only on the payload. sha256 is computed on the **uncompressed** payload: `zcat f | sha256sum` must equal `raw_objects.sha256`.
  - Written to a temp file in the same directory, `fsync`, `chmod 0444`, then `os.link` into place. A link never replaces an existing file, so nothing is ever overwritten.
  - Identical payloads (same sha256) are recorded once (`UNIQUE (sha256)`).
  - The archive row is committed in its own transaction **before** parsing, so a parse failure never leaves a payload unindexed.
  - The directory is bind-mounted read-write into `ingest` and read-only into `api`. Containers run as uid 1001/gid 1002, the VM user that owns `/srv/floodlead/archive`.
- **Why:** these properties make the archive immutable and checkable, as the prompt requires. Verified: files show `-r--r--r-- prana prana`. A forced re-download of 429 identical files added 0 new `raw_objects`.
- **Reversibility / cost:** the layout is fixed from now on. Moving it means copying, never rewriting.
- **Follow-ups:** a disk snapshot schedule is still needed for an off-machine copy (human).

### D-01.8 — USGS: Water Data OGC API v1, primary series only

- **Context:** the prompt names `…/ogcapi/v0/…`. Every v0 response's `next`/`self` links point to **`/ogcapi/v1/`** (`api-version: 1.9.8`), so v1 is current. No deprecation header was seen on v0 or v1 responses; all headers were checked. The legacy `waterservices.usgs.gov/nwis/iv` still answered `200` in Stage 0.
- **Options considered:** (a) OGC v1 `continuous` collection; (b) legacy NWIS IV.
- **Choice:** (a). Requests use `limit=50000`, `skipGeometry=true` and a `properties=` filter, and follow `rel=next` cursors. Only the series marked `Primary` with statistic `00011` in `time-series-metadata` are kept per (site, parameter), so two sensors cannot write the same key. Site 12210500 (Deming) has no instantaneous data after 2005-09-30, so it is **dropped** from live ingest and the backfill (logged in each run's `details.dropped_no_recent_data`).
- **Why:** one request returns a whole month for a site (2,831 rows, 1.3 MB, 1.0 s). It returned the verified Everson peak exactly: `time 2021-11-15T21:40:00+00:00` (13:40 PST), `value 52300`, `Approved`.
- **Reversibility / cost:** the parser is isolated in `sources/usgs.py`. NWIS IV can be added as a fallback if v1 fails.
- **Follow-ups:** keep checking response headers for deprecation notices.

### D-01.9 — Prepared statements disabled (measured)

- **Context:** the first full ECCC load took **5 min 32 s** for 429 files, and throughput fell from 126 to about 50 files/min. A forced re-run was still unfinished after 10 min, with four Postgres backends at 36–45 % CPU each and single UPDATEs running for seconds. The same upsert on a fresh connection took **0.13 s** per 1,426-row file (EXPLAIN ANALYZE: 55 ms, index scans on the chunk's primary key).
- **Choice:** connect with `prepare_threshold=None` (no server-side prepared statements).
- **Why:** after 5 executions psycopg prepares statements, and PostgreSQL's generic plan for the staging-to-hypertable join is far slower than the custom plan, which uses the literal time bounds for chunk exclusion. After the change, the forced re-download of all 429 files took **54 s** (run 3; fetch 13.9 s, process 196 s summed over 4 workers).
- **Reversibility / cost:** one line. A small planning cost on every statement (~11 ms measured).
- **Follow-ups:** none.

### D-01.10 — NWPS: forecasts stored unmodified; observed series archived only

- **Choice:**
  - Every `stageflow` forecast point is inserted with `ON CONFLICT (lid, issued_at, valid_at) DO NOTHING`, so each issuance is stored once, exactly as published (values not altered, including any NWS missing codes). The table rejects UPDATE and DELETE.
  - Flood categories with a value other than −9999 ("not defined" in NWPS) become `official_thresholds` on the USGS station named by `usgsId`, in native ft plus a converted metre value, with source and `raw_object_id`.
  - The NWPS `observed` series duplicates the USGS gauge, so it is archived raw but not loaded into `observations`.
- **Why:** this follows NOAA's conditions (data-contract record 7: do not modify official data and present it as official). It also leaves one system of record for observations.
- **Follow-ups:** Stage 2 scores against `official_forecasts`.

### D-01.11 — Runtime layout and memory limits

- **Choice:**
  - Four compose services with `restart: unless-stopped`:
    - `db`: `mem_limit 2560m`, `shared_buffers 512MB`, `effective_cache_size 1536MB`, `work_mem 16MB`, `maintenance_work_mem 128MB`, `max_connections 50`, `timescaledb.max_background_workers 2`, `max_parallel_workers 2`, telemetry off, `NO_TS_TUNE=true`;
    - `ingest`: 1 GiB;
    - `api`: 512 MiB;
    - `caddy`: 256 MiB.
  - Postgres data is in the named volume `pgdata` (on the boot disk, under `/var/lib/docker/volumes`).
  - Postgres is published on **127.0.0.1:5432 only**, for admin and tests on the VM. GCP firewall has no 5432 rule either.
  - At most 4 parallel HTTP requests per source (`http_max_parallel = 4`), including backfills.
- **Why:** this leaves at least 3.5 GiB for the OS page cache and this session. Loopback-only binding keeps the database private.
- **Follow-ups:** none.

### D-01.12 — `fetch_state` table for conditional GETs across restarts

- **Context:** `raw_objects` deduplicates identical payloads, so it cannot record the newest `Last-Modified` seen for a URL.
- **Choice:** a small `fetch_state(url, last_modified, last_status, checked_at)` table, advanced only **after** a payload has been archived and upserted, so a failed parse is retried on the next run.
- **Why:** a restarted ingest container resumes without re-downloading 429 files. Verified: the first scheduler run after start fetched 0 and found 429 unchanged, in 0.45 s.

## Work log

- `13:33` — `git remote set-url origin https://github.com/agenticraptor/trilemma-datathon-FloodLeadBC.git` (the new URL the human gave), `git checkout main && git pull origin main` → fast-forward `b7b263e..939495f` ("Fold Stage 0 findings into Stage 1; fix repo name and archive wording"). `docker run --rm hello-world` → `Hello from Docker!` without sudo. `git checkout -b stage-01-live-archive`.
- `13:35` — Committed and pushed the opened doc (`d4e5e1d`).
- `13:35` — Swapfile (D-01.1): `fallocate -l 4G /swapfile && chmod 600 && mkswap && swapon`, plus the fstab line. `swapon --show` → `/swapfile file 4G 0B -1`.
- `13:36–13:40` — Source probes with the project User-Agent:
  - USGS `ogcapi/v0/collections/continuous/items` → `200 0.334s`; `next` links point to `/ogcapi/v1/`. v1 with both parameters for 8 h at 12210700 → 66 features. One month of Everson 00060 (2021-11) → `200 1.003s 1,314,023 B`, 2,831 rows, max `52300` at `2021-11-15T21:40:00+00:00`, `Approved`.
  - USGS `time-series-metadata` for the 11 sites → primary 00011 series and begin dates (for example 12210700: 00065 from 2007-10-01, 00060 from 2004-10-15; 12211500 and 12214500 stage from 2022-10). 12210500 instantaneous data ends 2005-09-30.
  - NWPS `gauges/{lid}` for 6 gauges → all `200`. `usgsId`: NRKW1→12210700, NREW1→12211200, NOEW1→12211195, NKLW1→12211500, NKSW1→12213100, **SUMW1→12214500**. NRKW1 categories action 144.8 / minor 146.5 / moderate 148 / major 150 ft. NKSW1 also has routine forecasts.
  - ECCC daily listing → 442 `BC_*_daily_hydrometric.csv` files, all stamped `2026-10-07 08:18/08:19`. 08MH001 daily → 465,812 B, 8,625 rows, first `2026-09-07T00:00:00-08:00`, last `2026-10-06T23:20:00-08:00`. A conditional GET with its `Last-Modified` → `304`.
- `13:41` — Pulled the pinned images (D-01.3). Wrote `pyproject.toml` and `uv.lock` (`uv lock` → 31 packages), `migrations/001_init.sql`, `src/floodlead/` (config, log, units, db, http, archive, store, ingest, scheduler, cli, sources/eccc, usgs, nwps), `Dockerfile`, `compose.yaml` and `deploy/Caddyfile`. `uv run ruff check .` → `All checks passed!`
- `13:46` — `docker compose build ingest` (23.9 s). `docker compose up -d db` → healthy. `docker compose run --rm --no-deps ingest floodlead migrate` → `['001_init.sql']`.
- `13:46–13:52` — First ECCC load (`floodlead run eccc-hourly`) → run 1: `status ok, items_total 429, fetched 429, failed 0, inserted 563393` in **5:31.9**. One transient `RemoteProtocolError('Server disconnected…')` on one file, retried successfully. Throughput per minute (from `raw_objects.fetched_at`): 126, 82, 58, 44, 59, 60 files.
- `13:52–14:03` — Diagnosed the slowdown (D-01.9). Profiling one file on a fresh connection: fetch 0.240 s, parse 0.012 s, upsert 0.13–0.16 s for 1,426 rows. A forced re-download on pooled connections was still running after 10 min (run 2), with `pg_stat_activity` showing UPDATEs running 0.3–2.6 s each and `docker stats` showing db at 188 % CPU. Stopped that one-off container (`docker stop`; the run is idempotent). EXPLAIN ANALYZE of the same UPDATE → 55 ms with index scans. Set `prepare_threshold=None`, rebuilt, forced re-run → run 3: `fetched 429, rows_unchanged 563393, inserted 0, updated 0` in **54.1 s** (`timing_s {"fetch": 13.868, "process": 196.288}`, summed over 4 workers).
- `14:04` — `docker compose up -d ingest` (scheduler). Run 2 (killed) is left as `running`; the scheduler now marks interrupted live runs `error` at start. First cycle: eccc-hourly run 5 `fetched 0, unchanged 429` (0.45 s); usgs-stations run 4 `ok`; eccc-stations run 7 `ok` (2,324 BC stations read, real-time ones upserted); usgs-live run 8 `ok`, 10 sites; nwps-live run 6 `ok`, 6 gauges, 12 payloads.
- `14:06` — Snapshot:
  - `observations`: eccc 429 stations, 563,393 rows, newest `20:20 UTC` (lag 46 min); usgs 10 stations, 373 rows, newest `20:45 UTC` (lag 21 min); sentinels 0.
  - `official_forecasts`: NRKW1 issued `15:36 UTC`, 29 points to Oct 14 18:00; NKSW1 issued `15:36 UTC`, 40 points to Oct 17 12:00.
  - Official thresholds on usgs:12210700 (NRKW1, 4 categories), 12211195 (NOEW1: action 3.6, minor 4 ft), 12211200 (NREW1: action 83 ft) and 12213100 (NKSW1, 4 categories). 12211500 (NKLW1) and 12214500 (SUMW1) define none.
  - `raw_objects`: eccc 430 (21.0 MB raw → 1.41 MB gz), nwps 12 (3.77 MB → 0.15 MB), usgs 13 (0.40 MB → 0.03 MB).
  - Archive: 455 files, 2.4 MB, files `-r--r--r-- prana prana`.

## Measurements

| What | Value | How measured | When |
|---|---|---|---|
| First full ECCC hourly load | 429 files, 563,393 rows, 5 min 32 s (before D-01.9) | ingest_runs run 1 | 20:46–20:51 UTC |
| Forced re-download of all hourly files | 54.1 s; 563,393 rows unchanged; 0 new raw objects (sha dedupe) | ingest_runs run 3 | 21:03 UTC |
| Single-file upsert, 1,426 rows | 0.12–0.20 s (custom plan), EXPLAIN 55 ms | `prof2.py`, EXPLAIN ANALYZE | 20:55 UTC |
| Conditional-GET cycle, nothing changed | 0.45 s for 429 files (listing only) | ingest_runs run 5 | 21:04 UTC |
| gzip ratio, ECCC hourly CSV | 21,007,854 B → 1,411,813 B (14.9×) | `raw_objects` sums | 21:06 UTC |
| ECCC newest-row lag (all stations) | 46 min at 21:06 UTC (max ts 20:20) | SQL `now() - max(ts)` | 21:06 UTC |
| USGS newest-row lag | 21 min at 21:06 UTC (max ts 20:45) | SQL | 21:06 UTC |

## Acceptance criteria

| AC | Result | Evidence |
|---|---|---|

## Contract files changed

| File | What changed | Why |
|---|---|---|

## Open issues and handoff to next stage

- (filled at end)
