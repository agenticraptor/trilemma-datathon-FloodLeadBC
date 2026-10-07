# Stage 1 prompt — Foundation and live archive

You are the FloodLead BC build worker. Follow `CLAUDE.md` exactly (stage protocol, honesty rules, production safety, STAGE REPORT). Branch: `stage-01-live-archive`. Stage doc: `docs/stages/STAGE-01-live-archive.md`, created from `docs/stages/_TEMPLATE.md` **before you write code** and updated in every behaviour-changing commit.

## Mission

Start keeping the river data that would otherwise disappear, and make it verifiable from outside.

ECCC's real-time files only hold 30 days. Every hour we are not archiving is history we can never get back, and every forecast the ledger issues later needs this data underneath it. By the end of this stage, three public sources are being ingested continuously on the VM, every raw file is archived immutably in GCS, the backfills are loaded, and a read-only HTTPS API lets anyone check what we hold.

Build Session 2 is today at 18:00 PT. Get the live ECCC ingestion and raw archive running first, then widen.

## Read first

`CLAUDE.md`, `AGENTS.md`, `docs/build/PLAN.md` (especially "Facts the supervisor verified"), `data-contract.md` (records 1, 6, 7), `architecture.md`, `evidence/` (earlier pull scripts and `station_summary.csv`). The VM's `.env` holds `GCS_BUCKET`, `PUBLIC_HOSTNAME`, `ACME_EMAIL`, `POSTGRES_PASSWORD`.

## Priorities and time boxes

| Priority | Deliverable | Target |
|---|---|---|
| P1 | ECCC Datamart live ingestion for all BC hourly files + raw archive to GCS, running under docker compose | within ~90 min of starting |
| P2 | ECCC 30-day backfill; USGS and NOAA NWPS live ingestion; USGS history backfill | next ~2 h |
| P3 | Read-only public API behind Caddy HTTPS | before 17:30 PT if possible |
| P4 | Tests, docs, contract sync, PR | before you stop |

If time runs out, ship P1–P2 working and report P3–P4 honestly as PARTIAL.

## Verified source facts (do not re-derive; do re-check if something fails)

**ECCC Datamart (BC gauges)**
- Listing: `https://dd.weather.gc.ca/today/hydrometric/csv/BC/hourly/` (429 files on Oct 7, all rewritten at about :31 each hour). 30-day files: same path with `/daily/`.
- File names: `BC_<STATION>_hourly_hydrometric.csv`, `BC_<STATION>_daily_hydrometric.csv`.
- Columns: `ID, Date, Water Level / Niveau d'eau (m), Grade, Symbol / Symbole, QA/QC, Discharge / Débit (cms), Grade, Symbol / Symbole, QA/QC`. `Date` is ISO 8601 with a `-08:00` offset. Hourly files hold ~2 days; daily files hold ~30 days of 5-min rows (8,626 rows for 08MH001).
- Measured latency: newest row p50 61 min, p90 91 min behind real time.
- The OGC API real-time collection is ~4 h behind. Use it only for station metadata (`collections/hydrometric-stations`, `PROV_TERR_STATE_LOC=BC`), not for live data.
- Use conditional GETs (`If-Modified-Since` / `Last-Modified`) so each file is downloaded once per refresh. Send a descriptive `User-Agent` naming the project and repo URL.

**USGS (Nooksack and Sumas, Washington)**
- Sites: 12205000 (NF Nooksack nr Glacier), 12208000 (MF nr Deming), 12210000 (SF at Saxon Bridge), 12210500 (Nooksack at Deming), 12210700 (North Cedarville), 12211200 (Everson), 12211190 and 12211195 (overflow gauges at Everson), 12211500 (nr Lynden), 12213100 (Ferndale), plus the Sumas River gauge (take its `usgsId` from NWPS gauge `SUMW1`). Drop any site that returns no data, and log it.
- Parameters: `00065` gage height (ft), `00060` discharge (cfs). 15-min data, ~45 min behind.
- North Cedarville history: stage from 2007-10-01, flow from 2004-10-15.
- Prefer the new USGS Water Data OGC API (`https://api.waterdata.usgs.gov/ogcapi/v0/collections/continuous/items`). Its `datetime` parameter needs an explicit ISO interval (`P1D` was rejected). Fall back to the legacy IV service (`https://waterservices.usgs.gov/nwis/iv/`, follow redirects). Record which one you used and why, and check for any deprecation notice.
- Cross-check value for your backfill: Everson (12211200) discharge peaked at **52,300 cfs at 2021-11-15 13:40 PST**.

**NOAA NWS NWPS (official forecasts and flood stages)**
- `https://api.water.noaa.gov/nwps/v1/gauges/{lid}` (metadata, `usgsId`, flood categories) and `.../gauges/{lid}/stageflow` (`observed` and `forecast` objects with `issuedTime`, and `data[]` of `validTime`, `generatedTime`, `primary` stage in ft, `secondary` flow in kcfs).
- Gauges: `NRKW1` (Nooksack at North Cedarville, USGS 12210700; has an official 7-day forecast, 6-hourly points; flood stages action 144.8 ft, minor 146.5, moderate 148, major 150), `NREW1`, `NOEW1`, `NKLW1`, `NKSW1`, `SUMW1`.
- NWPS stage and USGS gage height share a datum (both ~138.0 ft on Oct 7).
- Store every distinct forecast issuance (keyed by `issuedTime`) unmodified. Never alter an official value. NOAA's conditions are in `data-contract.md` record 7.

## Pre-made architecture decisions

You may override any of these, but only with a decision record that gives evidence.

- **Runtime:** Docker Compose on this VM. Services: `db` (TimescaleDB on PostgreSQL 16, pinned image tag), `ingest` (Python scheduler), `api` (FastAPI + uvicorn), `caddy` (automatic HTTPS for `PUBLIC_HOSTNAME`). All `restart: unless-stopped`. Postgres is never exposed publicly.
- **Python:** 3.12, `uv`, `ruff`, `pytest`, `psycopg` 3, `httpx`, `pydantic-settings`, `google-cloud-storage` (credentials from the VM's service account; no key files). Package at `src/floodlead/`, CLI entry point `floodlead`.
- **Polling, not AMQP.** Measured freshness is set by the hourly file refresh, so polling after :31 is as fresh as push and simpler to debug. Write this up as a decision.
- **Migrations:** plain SQL files in `migrations/`, applied by a small runner recording a `schema_migrations` table.

## Data model (minimum)

- `stations`: `station_id` (namespaced: `eccc:08MH001`, `usgs:12210700`), source, native id, name, lat/lon, region (province or state), drainage area if available, parameters available, `official_thresholds` (JSON: NWS categories with units and source), links (for example `nwps_lid`).
- `observations` (hypertable): `station_id, ts (UTC), param ('level' | 'flow')`, `value` in SI (m, m³/s), `raw_value`, `raw_unit`, quality fields as received (grade, symbol, QA/QC or USGS qualifiers), `is_sentinel`, `first_seen_at`, `last_seen_at`, `revised_at`, `revision_count`, `raw_object_id`. Primary key `(station_id, ts, param)`.
  - Conversions: ft × 0.3048, cfs × 0.028316846592. Keep raw values.
  - Flag sentinels (|value| ≥ 9999 and any documented sentinel codes) and keep them. The API's default series excludes them.
- `observation_revisions`: append-only history of every changed value (old value, new value, when, which raw object).
- `official_forecasts`: `lid, issued_at, valid_at, stage_ft, flow_kcfs, generated_at, fetched_at, raw_object_id`; unique on `(lid, issued_at, valid_at)`.
- `raw_objects`: one row per fetched payload: source, URL, GCS URI, sha256, bytes, HTTP status, `Last-Modified`, `fetched_at`.
- `ingest_runs`: source, started/finished, status, rows inserted/updated/unchanged, error text.

## Ingestion

- **Schedules:** ECCC listing every 10 min (download only changed files); USGS every 15 min (rolling 6 h window per site); NWPS every 30 min; station metadata daily.
- **Raw archive:** every fetched payload is gzipped to `gs://$GCS_BUCKET/raw/<source>/YYYY/MM/DD/HH/<name>.<sha8>.gz` and recorded in `raw_objects`. Objects are never overwritten or deleted. If GCS is unreachable, spool to a local directory and retry; never block or drop ingestion.
- **Upserts:** idempotent. A re-fetch of identical data changes nothing except `last_seen_at`. A changed value updates the row, increments `revision_count` and appends to `observation_revisions`.
- **Robustness:** timeouts, retries with backoff, one failing station never stops the others, every run logged to `ingest_runs`. Structured JSON logs to stdout.

## Backfills (CLI, idempotent, resumable)

1. `floodlead backfill eccc-30d`: all BC 30-day files.
2. `floodlead backfill usgs --sites … --since …`: chunked (for example by month), polite pacing, resumable from a cursor.
3. `floodlead backfill nwps`: gauge metadata, flood categories, current forecast.

Run them in the background (for example a one-off compose service) so the live ingestion keeps running.

## Public read-only API (behind Caddy, HTTPS)

- `GET /v1/health`: per source, last successful run, newest observation time, lag in minutes, stations reporting in the last 3 h, and status (green/amber/red with thresholds you document).
- `GET /v1/stations` (filters: source, region, text search), `GET /v1/stations/{station_id}` (includes official thresholds).
- `GET /v1/stations/{station_id}/observations?param=&since=&until=&include_sentinels=` (max 7 days per call; ISO UTC timestamps).
- `GET /v1/official-forecasts/{lid}?issued_after=`.
- OpenAPI at `/docs`. Every response carries an `attribution` field with the credit lines from `data-contract.md`. CORS allows GET from any origin. Basic rate limiting.

## Tests

- Parser tests on small real fixtures you commit (trimmed ECCC CSV, USGS response, NWPS response).
- Unit conversions, sentinel flagging, timezone handling (the `-08:00` offsets), upsert idempotency and revision capture against a disposable test database, API contract tests.
- Live checks against the real sources, marked `@pytest.mark.live`.

## Documentation (while you build)

- Stage doc with at least 10 decision records (for example polling vs AMQP, image pin, ID scheme, units, sentinel rule, revision handling, archive layout, USGS API choice, health thresholds, rate limits).
- Update `architecture.md` (data architecture record: polling, TimescaleDB in Docker on GCE, GCS archive, Caddy/sslip, US sources, measured volumes), `README.md` ("How it works" and the data table: add USGS and NOAA), and `data-contract.md` (replace estimated freshness with the latencies you measure).

## Acceptance criteria

| AC | Criterion | Evidence to paste |
|---|---|---|
| AC-1 | `https://$PUBLIC_HOSTNAME/v1/health` is green for ECCC, USGS and NWPS | `curl` output |
| AC-2 | ≥ 400 BC stations have observations newer than 3 h; ECCC newest-row lag p50 ≤ 90 min | SQL + numbers |
| AC-3 | ECCC backfill: ≥ 400 stations with ≥ 25 days of 5-min data | SQL |
| AC-4 | For 08MH001, 08MH029 and 08MH103, the latest stored row equals the last row of the live Datamart file fetched at check time | both outputs side by side |
| AC-5 | USGS: all live sites backfilled; North Cedarville stage from 2007-10-01, with per-year completeness reported; Everson's 2021-11-15 peak present and equal to 52,300 cfs | SQL |
| AC-6 | NWPS: at least one official NRKW1 forecast stored with `issued_at`; flood categories stored as official thresholds | API output |
| AC-7 | Every fetched payload is in GCS with sha256 in `raw_objects`; objects written in the last hour counted | `gcloud storage ls` count + SQL |
| AC-8 | Sentinel and revision counts reported; sentinels excluded from the default API series | SQL + API |
| AC-9 | Services survive `docker compose restart` and a VM reboot; ingestion resumes without manual steps | health before/after |
| AC-10 | `ruff check .` and `pytest` pass; test count reported | output |
| AC-11 | Stage doc has ≥ 10 decisions and was updated across ≥ 4 commits; contract files updated | `git log --stat` excerpt |
| AC-12 | Monthly cost estimate for VM, disk, bucket and egress, labelled as an estimate | table |

## Out of scope for this stage

Forecasts, ledger, models, web UI and alerts. Do not start them; they are later stages.

## When done

Open the PR (do not merge) and print the STAGE REPORT. Under "Supervisor checks", list the public URLs and a few `curl` commands with expected results, so they can be verified from outside the VM.
