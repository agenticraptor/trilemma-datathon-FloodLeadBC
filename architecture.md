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

```yaml
data_architecture:
  product: floodlead-bc
  sources:
    - ECCC real-time hydrometric (AMQP push + HTTPS fallback)
    - ECCC historical daily hydrometric (OGC API / HYDAT)
    - ECCC HRDPS precipitation (GRIB2)
    - BC RFC advisory level (HTML snapshot, baseline only)
  volume:
    realtime: ~40 demo stations x 288 readings/day x 2 params ≈ 23k rows/day (all BC ≈ 150–300 stations ≈ 170k rows/day)
    history: ~1–5 million station-days
    forecasts: stations x 24/day x 4 horizons ≈ 4k–29k rows/day
  freshness:
    observations: minutes
    forecasts: hourly
    ledger_head_commit: daily to GitHub
  ingestion: Python asyncio AMQP consumer; dedupe on (station_id, ts, param); 30-day backfill job
  storage:
    hot: PostgreSQL 16 + TimescaleDB hypertables
    archive: Parquet on S3-compatible object storage, Canadian region
    offline: DuckDB over Parquet for training
  transformation: SQL views + Python feature builder with train/serve parity tests
  orchestration: systemd timers / APScheduler (hourly forecast, 6-hourly HRDPS, daily ledger head); no Airflow at this scale
  serving: FastAPI (public read API, ledger, PWA backend)
  reliability:
    slo_ingest: 99% of observations ingested within 10 min of publication
    slo_alert: alert-to-call p95 < 60 s
    fallbacks: HTTPS polling if AMQP drops; gauge-only model if HRDPS missing
  quality:
    checks: level range per station, monotonic timestamps, duplicates, stale stations, unit consistency
    on_failure: quarantine batch, mark features missing, never silently impute ground truth
  cost:
    infra: ~CA$60–120/month (1 VM 4 vCPU/16 GB + managed Postgres + object storage)
    messaging: per-SMS and per-voice-minute provider fees, capped by rate limits
  complexity_justification: >-
    Single-node Postgres/Timescale handles this volume with headroom; streaming platforms (Kafka)
    and orchestration frameworks are deliberately avoided. The only "real-time" requirement is
    minutes-level ingestion and hourly forecasts.
```

## Components

| Component | Tech | Notes |
|---|---|---|
| Ingestor | Python 3.12, `aio-pika` or `sarracenia` | Writes raw CSV to Parquet (hashed) and rows to Timescale |
| Backfill | Python + `httpx` | Pulls last 30 days of Datamart CSVs and HYDAT history |
| HRDPS subsetter | `xarray` + `cfgrib` | Basin-mean precipitation per run |
| Feature builder | SQL + pandas/polars | Lags, slopes, upstream travel-time lags, antecedent flow, forecast precip |
| Models | LightGBM quantile + isotonic calibration; discrete-time hazard for time-to-crossing | CPU only |
| Baselines | Persistence, linear trend, RFC level, CLEVER/COFFEE, Flood Hub | Same scoring code path as the model |
| Ledger | Append-only table; `sha256(prev_hash ‖ canonical_json(row))` | Daily head hash committed to `ledger/heads.txt` |
| Scorer | Brier, CRPS, reliability bins, lead time, FAR | Runs hourly as truth arrives |
| Agent | Explicit state machine | `detect → compose → call_user → await_approval → notify_contacts → escalate` |
| Messaging | Voice + SMS provider with Canadian numbers | Webhooks for keypress and replies |
| Web | Next.js PWA | Gauge chart + forecast fan, threshold setup, ledger viewer |
| Observability | Prometheus + Grafana; structured JSON logs | Feed lag, ingest rate, model latency, alert outcomes |

## Core schema

```sql
observation(station_id text, ts timestamptz, param text, value double precision,
            qa_flag text, first_seen_at timestamptz, revised_at timestamptz,
            primary key (station_id, ts, param));

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

| Method | Path | Returns |
|---|---|---|
| GET | `/v1/stations` | Stations with metadata and latest reading |
| GET | `/v1/stations/{id}/forecast` | Latest forecast: `p_exceed`, `q10/q50/q90`, `issued_at`, `model_version` |
| GET | `/v1/ledger?since=` | Ledger rows with hashes |
| GET | `/v1/scores/summary` | Live skill vs each baseline |
| POST | `/v1/thresholds` | Create a personal threshold (authenticated) |
| POST | `/v1/webhooks/voice`, `/v1/webhooks/sms` | Provider callbacks |
| GET | `/llms.txt` | Agent-readable product description |

## Deployment

- One VM plus managed Postgres in a Canadian cloud region (data residency for personal data).
- Containers via Docker Compose; GitHub Actions for tests and deploy.
- Secrets in the provider's secret store, never in the repo.
