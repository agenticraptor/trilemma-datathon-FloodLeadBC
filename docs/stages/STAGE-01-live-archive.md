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

### D-01.13 — Literal station predicate in the upsert joins, and short station-row locks (measured)

- **Context:** the ECCC 30-day backfill managed about 12 files/min. EXPLAIN ANALYZE of the stale-row count for one 30-day file (12,904 staged rows): **Hash Join over Seq Scans of all 5 chunks (701,900 rows), 5,610 ms**. Separately, `pg_stat_activity` showed USGS backfill workers waiting on `Lock/tuple` and `Lock/transactionid` for `INSERT INTO stations … ON CONFLICT DO UPDATE`, because that row lock was held for the whole upsert transaction.
- **Options considered:** (a) `enable_hashjoin = off` per session; (b) `ANALYZE` the staging table; (c) add `o.station_id = ANY(<literal list>)` so the planner range-scans the primary key.
- **Choice:**
  - (c), which brings the plan to Hash Join over **Index Scans** returning 1,134 rows: **68.7 ms** (82× faster).
  - `ensure_stations` runs in its own short transaction and only updates when `params` actually change.
  - USGS backfill tasks are interleaved across sites, so parallel workers do not queue on one station's advisory lock.
  - An interrupted backfill run is marked `error` ("abandoned: interrupted, resumed by a later run") when the job restarts.
- **Why:** it is the measured bottleneck, and (c) keeps the plan correct without global planner switches.
- **Reversibility / cost:** none.

### D-01.14 — Health thresholds

- **Context:** `/v1/health` reports per-source status green/amber/red. The thresholds come from the measured behaviour of each feed.
- **Choice:**
  - **ECCC:** green when the last successful live run is ≤ 30 min old (job runs every 10 min), the newest row is ≤ 150 min old (worst case measured in Stage 0: 107 min just before a rewrite), and ≥ 80 % of stations seen in the last 7 days reported in the last 3 h. Amber up to 90 min / 360 min. Otherwise red.
  - **USGS:** green when run ≤ 45 min (job every 15 min), lag ≤ 120 min (measured 21–52 min), reporting ≥ 80 %. Amber up to 120 / 360 min.
  - **NWPS:** green when run ≤ 90 min (job every 30 min) and the newest official issuance is ≤ 36 h old (NRKW1 is issued about daily in low water). Amber up to 180 min / 72 h.
  - **Disk:** amber at 80 % used, red at 90 % (prompt).
  - Overall status is the worst of the four.
- **Why:** each threshold sits above normal behaviour, so green means "working as designed". The response also shows per-station lag p50/p90, so a reader can judge for themselves. Health is computed from SQL and cached for 30 s in the API process.
- **Follow-ups:** Stage 8 monitoring alerts on amber/red.

### D-01.15 — Public API shape, CORS, rate limit, attribution

- **Choice:**
  - FastAPI behind Caddy, read-only, GET only. CORS `*` for GET.
  - In-memory token bucket of **120 requests/min per client IP** on `/v1/*` (client IP from Caddy's `X-Forwarded-For`; the API is only reachable through Caddy). Over the limit → 429 with `Retry-After: 30`.
  - Every response, errors included, carries `attribution` (the four credit lines from `data-contract.md`).
  - Observations are served in SI with `raw_value`/`raw_unit`, at most 7 days per call (400 otherwise). Sentinels are excluded unless `include_sentinels=true`.
  - `/v1/official-forecasts/{lid}` returns the latest issuance by default, or all issuances after `issued_after`, unmodified, with the station's official thresholds.
  - `/v1/stations` includes the latest reading per parameter (last 3 days) via one primary-key probe per station and parameter. That query took 5.6 s as a `DISTINCT ON` sort and 0.17 s as `LATERAL … ORDER BY ts DESC LIMIT 1`.
- **Why:** this satisfies the prompt's API contract, and the latest-reading query stays cheap as history grows.

### D-01.16 — TLS via Caddy with no ACME email

- **Context:** `ACME_EMAIL` is absent from `.env`. The prompt says to use it only if present.
- **Choice:** the Caddyfile has no `email` option. Caddy obtains the certificate for `PUBLIC_HOSTNAME` automatically (`admin off`, HSTS, gzip/zstd).
- **Evidence:** Caddy log `"certificate obtained successfully","identifier":"<host>.sslip.io","issuer":"acme-v02.api.letsencrypt.org-directory"`, after `tls-alpn-01` validation requests from 5 Let's Encrypt vantage points reached port 443. That is the first real proof that inbound 443 works. `openssl x509` → `issuer=C = US, O = Let's Encrypt, CN = YE2`, `notAfter=Jan  5 20:15:00 2027 GMT`. `http://` → `308` to `https://`.
- **Reversibility / cost:** adding `email {$ACME_EMAIL}` later only affects expiry notices.

### D-01.17 — USGS keyless rate limit: paced, resumable backfill; API key requested

- **Context:** after about 250 USGS requests, the API returned **HTTP 429** `OVER_RATE_LIMIT` with `x-ratelimit-limit: 1000`, `x-ratelimit-remaining: 0`, `retry-after: 1336`. The message says to sign up for an API key at `https://api.waterdata.usgs.gov/signup/`. The monthly-chunk plan needed **1,802** requests, and the old retry loop slept at most 120 s, then retried into the limit.
- **Options considered:**
  - (a) keep monthly chunks and wait out the limit for hours;
  - (b) larger chunks plus pacing plus honouring Retry-After;
  - (c) sign up for a key myself. **Not done:** it is a credential tied to a person's email, so it is the human's call (CLAUDE.md "stop and ask").
- **Choice:** (b), plus support for an optional `USGS_API_KEY` in `.env` (sent as `X-Api-Key`).
  - Chunks are **6 calendar months** per site with both parameters (≈ 35k rows, one page; pagination is still followed). The total drops to about 300 requests.
  - Requests are paced at **7.2 s between starts (≤ 500/h)**, leaving ≥ 450/h for live ingest (about 44/h). With a key the interval drops to 1 s.
  - A 429 asking to wait more than 60 s raises `RateLimited` at once. The backfill then pauses all workers for Retry-After + 5 s and retries the chunk (up to 6 times). Live ingest stops the cycle after the first 429.
  - Resume is by **coverage**: a chunk is skipped when completed chunks of any size cover it, so the 113 monthly chunks already done are kept.
  - Sites go in priority order (12210700, 12211200 first), newest chunks first.
  - 2 workers, because each 6-month page is about 15–25 MB of JSON and the container limit is 1 GiB.
- **Reversibility / cost:** with a key, re-run `floodlead backfill usgs` and it continues from the coverage table.
- **Follow-ups:** "Needs human": a USGS API key.

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
- `14:06` — Committed and pushed `6dc918b`.
- `14:07` — Added a `backfill` compose service (`restart: "no"`, profile `backfill`). `docker compose run -d --name fl-backfill-eccc30d backfill floodlead backfill eccc-30d`; `docker inspect` → `restart=no mem=1073741824`.
  - USGS dry run: `floodlead backfill usgs --sites 12211200 --since 2021-11-01 --until 2021-12-01` → run 10 `ok`, 5,662 rows in 8.7 s. SQL: `usgs:12211200 flow 2021-11-15 13:40:00 (America/Vancouver) raw 52300 ft3/s, SI 1481.0 m3/s, Approved`.
  - Then the full USGS backfill: plan 1,802 monthly tasks.
- `14:09` — ECCC backfill slow (17 files in about 2 min). `pg_stat_activity` showed 1–4 s joins and lock waits on `stations`. EXPLAIN → D-01.13. Fixed, rebuilt, restarted ingest, relaunched both backfills (resumed: ECCC skips files already in `fetch_state`; USGS skips recorded chunks). After 45 s: 43 daily files, 105 USGS chunks.
- `14:11–14:13` — Wrote `api.py`. TestClient smoke test against the live DB: `/v1/health 200`; `/v1/stations?source=usgs 200` (5.60 s, then 0.17 s after the LATERAL rewrite); `/v1/stations/usgs:12210700 200` with the NRKW1 categories; observations `200` (278 level rows for 24 h); `/v1/official-forecasts/NRKW1 200`; unknown station → `404`; 30-day window → `400`. Errors now carry attribution.
- `14:13` — `docker compose up -d ingest api caddy`. Caddy obtained a Let's Encrypt certificate via `tls-alpn-01` in about 3.5 s (D-01.16). From the VM: `curl https://<host>/v1/health` → `status green`; eccc lag 24 min, station lag p50 49 min, 428 stations reporting in 3 h; usgs lag 14 min, 10 stations; nwps newest issuance 5.63 h; disk 15.5 %; archive 993 files, 22.2 MB on disk (381 MB raw), 0 write failures. `http://` → `308`.
- `14:14` — USGS backfill stalled. `docker logs` showed `status 429`. `curl -D -` → `HTTP/2 429`, `retry-after: 1336`, `x-ratelimit-limit: 1000`, `x-ratelimit-remaining: 0`, `"code": "OVER_RATE_LIMIT"`. Stopped the backfill container. Recorded chunks so far: 12205000 71 chunks (2004-10 → now, 304,502 rows); the other 9 sites only their newest 4–5 months. 12211200 also has 2021-11. Implemented D-01.17, rebuilt, redeployed ingest and api.
- `14:17` — Committed and pushed `5f3961d`. The backfill start now also waits out a 429 on its metadata request. Relaunched `fl-backfill-usgs` (6-month chunks): first request → `429`, `retry_after_s 1652`, so it waits on its own. The quota window is rolling: Retry-After grew from 1,336 s to 1,652 s.
- `14:18–14:24` — Tests and fixtures:
  - Real trimmed fixtures in `tests/fixtures/` (see its README): ECCC hourly 08MH001, ECCC daily 08NJ026 with a **real `99999.000` level sentinel**, ECCC listing, USGS continuous and metadata, NWPS gauge and stageflow.
  - Unit tests: parsers, `-08:00` handling, units, sentinel rule, archive atomicity/read-only/no-overwrite/deterministic gzip, chunk planning.
  - DB tests against a **disposable** `floodlead_test_<hex>` database created and dropped per session on the same server: idempotency, revisions, out-of-order guard, append-only triggers, sha256 dedupe, archive-failure path, forecasts insert-once, NWPS thresholds.
  - API contract tests (attribution on every response including 404/400/422, health shape, filters, 7-day limit, sentinel exclusion, forecasts, CORS, rate limiter).
  - 3 live tests. `uv run pytest -q` → **41 passed, 3 deselected**. `uv run pytest -m live` → 2 passed, 1 failed: the USGS live test, because the API is rate-limiting this IP (429). It will be re-run after the quota resets.
- `14:24` — Finding: ECCC rewrote the hourly files at **20:31:21** and again at **21:01:28** UTC (`raw_objects.last_modified` for 08MH001; all 429 `fetch_state` rows at 21:01). That is a 30-min cadence, not hourly as PLAN.md says. Polling every 10 min catches both within about 2 min. Run 12 (21:10, during both backfills) fetched 429 files: 4,634 rows inserted, 563,393 unchanged, 0 stale, in 2 min 21 s.
- Sentinel evidence for D-01.5: 2 real ECCC sentinels (`eccc:08HB029` and `eccc:08NJ026`, level `99999`). **1,119** USGS flow values are ≥ 9999 ft³/s and are real, not flagged; the prompt's literal rule would have flagged all of them.

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
