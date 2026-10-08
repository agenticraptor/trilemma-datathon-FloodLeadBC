# Architecture — FloodLead BC

## Bounded contexts

```text
┌──────────────┐   ┌───────────────┐   ┌──────────────┐   ┌───────────────┐
│  Ingestion   │──►│  Forecasting  │──►│   Ledger &   │   │    Agent      │
│ (ECCC feeds) │   │ (features +   │   │   Scoring    │   │ (alerts,      │
│              │   │  models)      │──►│              │   │  approvals)   │
└──────────────┘   └───────────────┘   └──────────────┘   └───────────────┘
                           │                                      ▲
                           └──────── risk detector ───────────────┘
                                                     │
                                          ┌──────────┴─────────┐
                                          │  Web PWA + Public  │
                                          │  API / llms.txt    │
                                          └────────────────────┘
```

## Data architecture record

Updated in Stage 1 (Oct 7, 2026) to what is actually running; numbers are measured unless labelled as estimates. Details and evidence: `docs/stages/STAGE-01-live-archive.md`.

```yaml
data_architecture:
  product: floodlead-bc
  sources:
    - ECCC Datamart real-time hydrometric CSVs, all BC (HTTPS polling with conditional GETs)
    - ECCC Datamart 30-day CSVs (backfill) and ECCC OGC API hydrometric-stations (station metadata only;
      its real-time collection is ~4 h behind)
    - USGS Water Data OGC API v1 (continuous 15-min stage 00065 and discharge 00060, 10 Nooksack/Sumas sites)
    - USGS legacy NWIS IV (history backfill 2004-10 onward, and live fallback while the keyless OGC quota is exhausted)
    - NOAA NWS NWPS (official forecasts for NRKW1/NKSW1, flood categories for 6 gauges)
    - planned, not yet ingested: ECCC HRDPS precipitation (GRIB2), ECCC historical daily (HYDAT), BC RFC advisory level
  volume:
    realtime_eccc: 429 hourly files rewritten every 30 min (Last-Modified ~:01/~:31, visible 2-6 min later); ~227k rows/day measured (4,634-4,700 rows per refresh)
      (estimate: 429 stations x 288 five-minute rows x ~1.9 params)
    realtime_usgs: 10 sites x 96 x 2 params ~= 1.9k rows/day
    official_forecasts: 29 points (NRKW1) + 40 (NKSW1) per issuance, about daily
    stored_oct7: 7.37M observation rows (6.93M ECCC incl. 30-day backfill, 0.44M USGS so far), 2.0 GB incl. indexes
      (~286 B/row)
    archive_oct7: gzip payloads, ECCC CSV compresses ~15x (21.0 MB -> 1.41 MB)
    growth_per_day: ~113 MB/day disk (archive ~48 MB + database ~65 MB, estimate from a 25-min steady-state window); WAL ~14 GB/day of writes (recycled); stored_oct7_end: 15.1M rows, 4.7 GB DB, 65 MB archive (2,115 files)
  freshness (measured Oct 7):
    eccc: newest row 22-47 min old just after a rewrite, 107 min worst case before the next; station-lag p50 ~49 min
    usgs: 14-52 min (OGC API v1; NWIS IV fallback when the keyless OGC quota is exhausted)
    nwps: forecasts issued ~daily (15:36 UTC on Oct 7); observed series ~37 min
  ingestion: >-
    One Python scheduler container polls ECCC every 5 min (:02/:07/...; only changed files, If-Modified-Since, plus a probe file when the listing looks stale),
    USGS every 15 min (rolling 6 h window), NWPS every 30 min, station metadata daily. At most 4 parallel requests
    per source. USGS keyless limit is 1,000 requests/hour per IP; backfills are paced to <= 500/h and honour
    Retry-After. Set-based idempotent upserts (COPY to staging), revision capture, out-of-order guard on
    published_at, per-station advisory locks.
  storage:
    hot: PostgreSQL 16 + TimescaleDB 2.30.2 in Docker on the VM (hypertable observations, 7-day chunks; named volume)
    raw_archive: >-
      every fetched payload gzipped to $ARCHIVE_DIR/raw/<source>/YYYY/MM/DD/HH/<name>.<sha8>.gz on the VM's
      boot disk, 0444, never overwritten or deleted, indexed with sha256 in raw_objects; identical payloads stored once
    off_machine_copy: none. Disk snapshots were declined by the owner (Oct 8; accepted risk): a disk loss loses the raw archive and the database. The forecast ledger entries and chain heads are published hourly to the `ledger` branch of the repository (Stage 2).
    offline: DuckDB/pandas over SQL extracts for training (Stage 3+)
  transformation: SI units (m, m3/s) with raw value and unit kept; sentinel flags; revisions in observation_revisions
  orchestration: in-process scheduler in the ingest container; one-off backfill containers (docker compose run)
  serving: >-
    FastAPI read-only public API behind Caddy (automatic Let's Encrypt HTTPS on <ip-with-dashes>.sslip.io);
    CORS GET *, 120 requests/min per IP, attribution on every response
  reliability:
    restart: all services restart: unless-stopped; scheduler marks interrupted runs; backfills resumable
    health: /v1/health per-source green/amber/red with documented thresholds; disk amber 80 %, red 90 %
  quality:
    checks: CSV header check, explicit UTC offsets, unit map, sentinel rule, primary-series filter (USGS), duplicates
    on_failure: one failing file/site never stops the others; failures recorded in ingest_runs; archive write
      failures logged loudly and recorded, ingestion continues
  cost (estimate, list prices, not billing data):
    infra: ~US$68-70/month (~CA$93-96) for e2-standard-2 + 100 GB pd-balanced + static IP, Toronto (no snapshots)
  complexity_justification: >-
    Single-node Postgres/Timescale handles this volume with headroom; Kafka, Airflow and object storage are
    deliberately avoided. Data refreshes every 15-30 min at the source, so polling is as fresh as push.
```

## Components

| Component | Tech | Notes |
|---|---|---|
| Ingestor | Python 3.12, `httpx`, `psycopg` 3 (`src/floodlead/`) | Polls ECCC/USGS/NWPS, archives each raw payload (gzip, sha256, 0444) and upserts rows into Timescale |
| Backfill | `floodlead backfill eccc-30d / usgs / nwps` | Datamart 30-day files; USGS 15-min history since 2004 (paced, resumable); HYDAT history in Stage 3 |
| HRDPS subsetter | `xarray` + `cfgrib` | Basin-mean precipitation per run |
| Feature builder | SQL + pandas/polars | Lags, slopes, upstream travel-time lags, antecedent flow, forecast precip |
| Models | LightGBM quantile + isotonic calibration; discrete-time hazard for time-to-crossing | CPU only |
| Baselines | Persistence, linear trend, RFC level, CLEVER/COFFEE, Flood Hub | Same scoring code path as the model |
| Ledger | Append-only table; `sha256(prev_hash ‖ canonical_json(row))` | Daily head hash committed to `ledger/heads.txt` |
| Scorer | Brier, CRPS, reliability bins, lead time, FAR | Runs hourly as truth arrives |
| Agent | Explicit state machine | `detect → compose → call_user → await_approval → notify_contacts → escalate` |
| Messaging | Voice + SMS provider with Canadian numbers | Webhooks for keypress and replies |
| Public API | FastAPI + uvicorn behind Caddy | `/v1/health`, stations, observations, official forecasts (Stage 1) |
| Web | Next.js PWA | Gauge chart + forecast fan, threshold setup, ledger viewer |
| Observability | Prometheus + Grafana; structured JSON logs | Feed lag, ingest rate, model latency, alert outcomes |

## Core schema

Stage 1 tables (exact DDL: `migrations/001_init.sql`):

```sql
stations(station_id text PK,            -- 'eccc:08MH001', 'usgs:12210700'
         source, native_id, name, lat, lon, region, drainage_area_km2, params text[],
         official_thresholds jsonb,     -- NOAA NWS flood categories (ft + m), source, raw_object_id
         links jsonb, meta jsonb, first_seen_at, updated_at);

observations(station_id, ts timestamptz, param 'level'|'flow',     -- hypertable, PK (station_id, ts, param)
             value double precision,     -- SI (m, m3/s); NULL for sentinels
             raw_value, raw_unit, quality jsonb, is_sentinel, published_at,
             first_seen_at, last_seen_at, revised_at, revision_count, raw_object_id);

observation_revisions(...old/new value, quality, sentinel flag, raw objects, revised_at)   -- append-only
official_forecasts(lid, issued_at, valid_at, stage_ft, flow_kcfs, generated_at, fetched_at, raw_object_id)
                                                                   -- PK (lid, issued_at, valid_at), append-only
raw_objects(raw_object_id, source, url, archive_path, archive_error, sha256 UNIQUE, bytes, archive_bytes,
            http_status, last_modified, fetched_at)                -- append-only
ingest_runs(run_id, source, job, started_at, finished_at, status, items_*, rows_inserted/updated/unchanged/stale,
            error_text, details jsonb)
fetch_state(url PK, last_modified, last_status, checked_at)        -- conditional GETs across restarts
backfill_chunks(job, key, chunk_start, chunk_end, rows)             -- resumable backfills
schema_migrations(version, applied_at)
```

Planned for later stages (unchanged design):

```sql
forecast(forecast_id uuid primary key, station_id text, issued_at timestamptz,
         horizon_h int, threshold_m double precision, p_exceed double precision,
         q10 double precision, q50 double precision, q90 double precision,
         model_version text, feature_snapshot_hash text, prev_hash text, row_hash text);

user_threshold(user_id uuid, station_id text, label text, level_m double precision,
               lead_needed_h int, risk_pref double precision);

contact(contact_id uuid, user_id uuid, role text, phone_enc bytea, opted_in_at timestamptz);

alert(alert_id uuid, user_id uuid, forecast_id uuid, sent_at timestamptz,
      channel text, approved_at timestamptz, outcome text);

score(forecast_id uuid, observed_max double precision, crossed_at timestamptz,
      brier double precision, crps double precision);
```

## Public API

Live since Stage 1 (read-only; OpenAPI at `/docs`; every response carries `attribution`):

| Method | Path | Returns |
|---|---|---|
| GET | `/v1/health` | Per source (ECCC, USGS, NWPS): last successful run, newest observation, lag, stations reporting in 3 h, green/amber/red; disk use; archive size |
| GET | `/v1/stations?source=&region=&q=` | Stations with metadata and the latest reading per parameter |
| GET | `/v1/stations/{id}` | One station, including official thresholds |
| GET | `/v1/stations/{id}/observations?param=&since=&until=&include_sentinels=` | SI values plus raw values, at most 7 days per call; sentinels excluded by default |
| GET | `/v1/official-forecasts/{lid}?issued_after=` | NOAA NWS official forecasts, unmodified |

Planned:

| Method | Path | Returns |
|---|---|---|
| GET | `/v1/stations/{id}/forecast` | Latest forecast: `p_exceed`, `q10/q50/q90`, `issued_at`, `model_version` |
| GET | `/v1/ledger?since=` | Ledger rows with hashes |
| GET | `/v1/scores/summary` | Live skill vs each baseline |
| POST | `/v1/thresholds` | Create a personal threshold (authenticated) |
| POST | `/v1/webhooks/voice`, `/v1/webhooks/sms` | Provider callbacks |
| GET | `/llms.txt` | Agent-readable product description |

## Deployment

- One GCE VM in Toronto (`northamerica-northeast2`, e2-standard-2: 2 vCPU, 7.7 GiB RAM + 4 GiB swap, 100 GB pd-balanced), static external IP, hostname `<ip-with-dashes>.sslip.io`.
- Docker Compose (`compose.yaml`): `db` (timescale/timescaledb:2.30.2-pg16, ≤ 2.5 GiB, loopback-only port), `ingest` (≤ 1 GiB), `api` (≤ 512 MiB), `caddy` (caddy:2.11.7-alpine, ≤ 256 MiB, ports 80/443), all `restart: unless-stopped`; one-off `backfill` containers (`restart: "no"`).
- No managed Postgres and no object storage: Postgres data (named volume) and the raw archive (`/srv/floodlead/archive`) live on the boot disk. **There is no off-machine copy of either** (disk snapshots declined by the owner on Oct 8; accepted risk). The live track record survives a disk loss because the ledger entries and chain heads are published hourly to the `ledger` branch.
- Personal data (from Stage 7) stays in Canada on this VM, encrypted at rest.
- Secrets only in `.env` on the VM (gitignored). GitHub Actions for tests in Stage 8.
