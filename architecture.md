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
  forecast_ledger (Stage 2): >-
    One global append-only SHA-256 chain (ledger_entries), enforced by DB triggers on insert; hourly issuance at
    HH:15 of persistence-v1 and trend3h-v1 for ~426 gauges (852 forecasts/h, 72 s, 184 MB peak); NOAA issuances as
    official_forecast entries; hourly anchor at HH:30 commits the new entries (jsonl.gz, ~0.4 MB/h) and the head to
    the `ledger` branch; scorer at HH:40 writes derived forecast_scores and a materialised summary.
  observation_write_rules (Stage 2, F2): >-
    identical re-fetches write 0 observation rows; last_seen_at = when the current value was last written (insert
    or revision); published_at = publication time of the payload that set it; the per-station "last seen" is
    payload_coverage (newest payload per station and kind, with its time range), which also guards against older
    payloads overwriting values a newer payload covered.
  growth_with_ledger (measured Oct 9 01:36-03:42Z, 2.1 h; replaces the Oct 8 estimate of ~230 MB/day, ~270 days): >-
    archive ~40 MB/day + observations ~35 MB/day (F2: no rewrites) + ledger ~39 MB/day (1.63 MB per hourly
    issuance stored, ~1.9 kB/entry with indexes) + scores ~144 MB/day (587 B/row measured; at steady state
    10,224 rows/h = 852 forecasts + 426 naive, x 8 horizons; only h1/h3 had settled when measured) + other DB
    ~14 MB/day = ~270 MB/day; 60.2 GB of headroom to 80 % of the 102.9 GB disk => ~220 days (mid-May 2027).
    Scores are the largest part and are derived (recomputable from the ledger and observations), so compressing
    or thinning old scores is the first lever. Measured from table, chunk and archive sizes, not df (df "used"
    fell 42 MB in the window from Docker/WAL churn); a 2-hour window, so treat +-30 % as normal.
  complexity_justification: >-
    Single-node Postgres/Timescale handles this volume with headroom; Kafka, Airflow and object storage are
    deliberately avoided. Data refreshes every 15-30 min at the source, so polling is as fresh as push.
```

## Components

| Component | Tech | Notes |
|---|---|---|
| Ingestor | Python 3.12, `httpx`, `psycopg` 3 (`src/floodlead/`) | Polls ECCC/USGS/NWPS, archives each raw payload (gzip, sha256, 0444) and upserts rows into Timescale |
| Backfill | `floodlead backfill eccc-30d / usgs / nwps` | Datamart 30-day files; USGS 15-min history since 2004 (paced, resumable) |
| History (Stage 3) | `floodlead history download <source…>` (`src/floodlead/history/`), one-off `backfill` containers | Paced, resumable downloads into the raw archive with a manifest (`history_downloads`): ECCC annual peaks, daily means and hourly climate; IEM NWS warnings; NCEI KBLI; SNOTEL; Open-Meteo. `floodlead history load peaks|daily` parses them into new tables; `floodlead history typical-peaks` computes the typical yearly peak per BC gauge |
| HRDPS subsetter | `xarray` + `cfgrib` | Basin-mean precipitation per run |
| Feature builder | SQL + pandas/polars | Lags, slopes, upstream travel-time lags, antecedent flow, forecast precip |
| Models | LightGBM quantile + isotonic calibration; discrete-time hazard for time-to-crossing | CPU only |
| Baselines | Persistence, linear trend, RFC level, CLEVER/COFFEE, Flood Hub | Same scoring code path as the model |
| Ledger | `ledger_entries` (migration 002); `entry_hash = sha256(prev_hash + "\n" + canonical)`; DB trigger re-checks every insert; advisory-locked appends | Hourly anchor: new entries + head committed to `ledger/` on the `ledger` branch ([spec](docs/ledger-spec.md)) |
| Issuer | `src/floodlead/issuer.py`, `baselines.py` (numpy) | Hourly at HH:15; empirical error-path baselines; gaps instead of backdating |
| Anchor | `src/floodlead/anchor.py` (GitHub Git Data API, fine-grained token) | Hourly at HH:30; one commit per anchor; never `main`, never force |
| Scorer | `src/floodlead/scorer.py`: fair CRPS (`crps.py`, CDF rebuilt from the quantiles; quantile score kept as `crps_qs`), MAE, coverage, PIT, Brier; paired CRPSS and MAE skill vs persistence-v1 and pure persistence; NOAA matched pairs | Hourly at HH:40; derived table `forecast_scores`, summary in `score_summaries`; `floodlead score --recompute-crps` |
| Feedback (Stage 3) | `src/floodlead/feedback.py`, `POST /v1/feedback` | Anonymous; free text Fernet-encrypted (`FEEDBACK_KEY`); append-only table; per-client-IP limits in memory; read only with `floodlead feedback list` |
| Agent | Explicit state machine | `detect → compose → call_user → await_approval → notify_contacts → escalate` |
| Messaging | Voice + SMS provider with Canadian numbers | Webhooks for keypress and replies |
| Public API | FastAPI + uvicorn behind Caddy | `/v1/health`, stations, observations, official forecasts (Stage 1) |
| Web | Static `web/` (vanilla JS, uPlot 1.6.32 vendored), deployed by `scripts/deploy_web.sh` to `/srv/floodlead/web` and served by Caddy under `default-src 'self'` | Overflow watch, Fraser Valley gauges, replay, station picker, personal level (device only), ledger panel, track record, "How to read this", feedback box; snapshot mode from `floodlead export-demo` |
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

Stage 2 tables (migrations 002–004):

```sql
ledger_entries(seq bigint PK, entry_type, created_at, canonical text, prev_hash, entry_hash UNIQUE,
               station_id, model, base_time, lid)          -- append-only; insert trigger checks seq, link, hash
ledger_anchors(anchor_id, seq, entry_hash, anchored_at, commit_sha, commit_url, entries_path, entries_bytes,
               status, error_text)                          -- append-only
scorer_runs(scorer_run_id, started_at, finished_at, status, scored, rescored, details)
forecast_scores(seq, h, station_id, source, model, base_time, valid_at, stale_inputs, status,
                truth_ts, truth_m, truth_first_seen_at, truth_revision_count, q50_m, crps, ae_median,
                in_50, in_80, in_90, pit_bin, event_status, window_coverage, window_max_m, events jsonb,
                noaa jsonb, scored_at, scorer_run_id)     -- derived; PK (seq, h); rewritten on truth revision
score_summaries(scorer_run_id PK, generated_at, body jsonb)
payload_coverage(station_id, kind, published_at, ts_min, ts_max, raw_object_id, last_seen_at)  -- PK (station_id, kind)
-- Stage 3 (migrations 006-010):
forecast_scores.crps_qs, forecast_scores_naive.crps_qs                -- the old quantile score, kept as a secondary column
history_downloads(source, key, url, status, http_status, bytes, raw_object_id, fetched_at, elapsed_s, error)
eccc_annual_peaks(station_number, year, data_type, peak_code, peak_at, value, symbol, raw_object_id)
eccc_daily(station_number, date, level, discharge, level_symbol, discharge_symbol, raw_object_id)  -- 7.8 M rows
typical_peaks(method, station_id, status, value_m, n_years, first_year, last_year, reason, checks jsonb, computed_at)
feedback(feedback_id, received_at, route, station_id, useful, text_enc bytea, text_chars, key_id, app_version)
                                                                       -- append-only; no IP, name, email or phone
```

The Stage 1 sketch below of `forecast`/`score` is superseded by these: a forecast is a `forecast` ledger entry whose `canonical` JSON carries `q`, `qmax` and `p_exceed` per horizon (see the spec).

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
| GET | `/v1/replay/overflow`, `/v1/replay/overflow/{event_id}/series` | Every North Cedarville minor-stage event and the Sumas Prairie overflow onset, computed from stored data |
| GET | `/v1/stations/{id}/forecast` | Latest FloodLead baseline forecast per model (seq, hash, q, qmax, p_exceed) + NOAA's latest issuance, unmodified |
| GET | `/v1/ledger?after_seq=&limit=`, `/v1/ledger/head`, `/v1/ledger/{seq}` | Ledger entries with canonical text and hashes; head with the latest anchor |
| GET | `/v1/scores/summary?source=&model=&horizon=`, `/v1/scores/official?lid=` | Materialised scorer output with its run ID (fair CRPS, `mean_crps_qs_m`, CRPSS and MAE skill; pure persistence included) |
| GET | `/v1/gauges/fraser-valley` | Fraser Valley gauges: latest level, data age, typical yearly peak (FloodLead-derived, not official) and the distance below it |
| GET | `/v1/track-record` | Forecasts issued, chain head and anchor, skill against pure persistence per horizon with n, and generated plain-language statements |
| POST | `/v1/feedback` | Anonymous feedback (≤ 1,000 characters, encrypted at rest, never echoed); 202, or 400/413/429 |

Planned:

| Method | Path | Returns |
|---|---|---|
| POST | `/v1/thresholds` | Create a personal threshold (authenticated) |
| POST | `/v1/webhooks/voice`, `/v1/webhooks/sms` | Provider callbacks |
| GET | `/llms.txt` | Agent-readable product description |

## Deployment

- One GCE VM in Toronto (`northamerica-northeast2`, e2-standard-2: 2 vCPU, 7.7 GiB RAM + 4 GiB swap, 100 GB pd-balanced), static external IP, hostname `<ip-with-dashes>.sslip.io`.
- Docker Compose (`compose.yaml`; scheduler jobs in `ingest`: ECCC every 5 min, USGS 15 min, NWPS 30 min, `ledger-issue` HH:15, `ledger-anchor` HH:30, `scorer` HH:40, station metadata daily): `db` (timescale/timescaledb:2.30.2-pg16, ≤ 2.5 GiB, loopback-only port), `ingest` (≤ 1 GiB), `api` (≤ 512 MiB), `caddy` (caddy:2.11.7-alpine, ≤ 256 MiB, ports 80/443), all `restart: unless-stopped`; one-off `backfill` containers (`restart: "no"`).
- No managed Postgres and no object storage: Postgres data (named volume) and the raw archive (`/srv/floodlead/archive`) live on the boot disk. **There is no off-machine copy of either** (disk snapshots declined by the owner on Oct 8; accepted risk). The live track record survives a disk loss because the ledger entries and chain heads are published hourly to the `ledger` branch.
- Personal data (from Stage 7) stays in Canada on this VM, encrypted at rest.
- Secrets only in `.env` on the VM (gitignored), including `FEEDBACK_KEY` from Stage 3. GitHub Actions for tests in Stage 8.
- Database guard rails (Stage 3, F3): `statement_timeout = 15min` and `idle_in_transaction_session_timeout = 30min` as database defaults; ad-hoc work through `scripts/dbshell` (5 min, `work_mem` 8 MB); history in separate tables, never in the `observations` hypertable.
- The static app is deployed explicitly (`scripts/deploy_web.sh`, `rsync --delete` into `/srv/floodlead/web`), never served from the git working tree (Stage 3, D-03.11).
