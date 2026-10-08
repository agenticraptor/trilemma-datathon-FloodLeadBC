-- 001_init: stations, raw archive index, observations (hypertable), revisions,
-- official forecasts, ingest runs, backfill progress.
-- Additive only. Later changes go in new numbered files.

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- One row per distinct fetched payload (deduplicated on sha256 of the raw bytes).
CREATE TABLE raw_objects (
    raw_object_id   bigserial PRIMARY KEY,
    source          text        NOT NULL,          -- 'eccc' | 'usgs' | 'nwps'
    url             text        NOT NULL,
    archive_path    text,                          -- relative to ARCHIVE_DIR; NULL if the archive write failed
    archive_error   text,
    sha256          text        NOT NULL UNIQUE,   -- of the uncompressed payload
    bytes           bigint      NOT NULL,          -- uncompressed payload size
    archive_bytes   bigint,                        -- gzipped size on disk
    http_status     int         NOT NULL,
    last_modified   timestamptz,                   -- HTTP Last-Modified, when sent
    fetched_at      timestamptz NOT NULL
);
CREATE INDEX raw_objects_source_fetched ON raw_objects (source, fetched_at DESC);

CREATE TABLE stations (
    station_id          text PRIMARY KEY,           -- namespaced: 'eccc:08MH001', 'usgs:12210700'
    source              text NOT NULL,
    native_id           text NOT NULL,
    name                text,
    lat                 double precision,
    lon                 double precision,
    region              text,                       -- province or state, e.g. 'BC', 'WA'
    drainage_area_km2   double precision,
    params              text[] NOT NULL DEFAULT '{}',
    official_thresholds jsonb  NOT NULL DEFAULT '{}'::jsonb,
    links               jsonb  NOT NULL DEFAULT '{}'::jsonb,
    meta                jsonb  NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at       timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX stations_source ON stations (source);

CREATE TABLE observations (
    station_id      text        NOT NULL,
    ts              timestamptz NOT NULL,           -- UTC instant of the observation
    param           text        NOT NULL CHECK (param IN ('level', 'flow')),
    value           double precision,               -- SI: m or m3/s; NULL when is_sentinel
    raw_value       double precision,               -- exactly as published
    raw_unit        text        NOT NULL,           -- 'm', 'm3/s', 'ft', 'ft3/s'
    quality         jsonb       NOT NULL DEFAULT '{}'::jsonb,  -- grade/symbol/QA-QC or USGS approval/qualifier
    is_sentinel     boolean     NOT NULL DEFAULT false,
    published_at    timestamptz,                    -- when the source published this version (guards out-of-order payloads)
    first_seen_at   timestamptz NOT NULL,
    last_seen_at    timestamptz NOT NULL,
    revised_at      timestamptz,
    revision_count  int         NOT NULL DEFAULT 0,
    raw_object_id   bigint,                         -- payload that set the current value
    PRIMARY KEY (station_id, ts, param)
);
SELECT create_hypertable('observations', by_range('ts', INTERVAL '7 days'));

-- Append-only history of every change to an observation.
CREATE TABLE observation_revisions (
    revision_id       bigserial PRIMARY KEY,
    station_id        text        NOT NULL,
    ts                timestamptz NOT NULL,
    param             text        NOT NULL,
    old_value         double precision,
    new_value         double precision,
    old_raw_value     double precision,
    new_raw_value     double precision,
    old_quality       jsonb,
    new_quality       jsonb,
    old_is_sentinel   boolean,
    new_is_sentinel   boolean,
    old_raw_object_id bigint,
    new_raw_object_id bigint,
    revised_at        timestamptz NOT NULL
);
CREATE INDEX observation_revisions_key ON observation_revisions (station_id, ts, param);

-- Official NOAA NWS forecasts, stored unmodified, one row per (gauge, issuance, valid time).
CREATE TABLE official_forecasts (
    lid             text        NOT NULL,
    issued_at       timestamptz NOT NULL,
    valid_at        timestamptz NOT NULL,
    stage_ft        double precision,
    flow_kcfs       double precision,
    generated_at    timestamptz,
    fetched_at      timestamptz NOT NULL,
    raw_object_id   bigint REFERENCES raw_objects (raw_object_id),
    PRIMARY KEY (lid, issued_at, valid_at)
);

CREATE TABLE ingest_runs (
    run_id          bigserial PRIMARY KEY,
    source          text        NOT NULL,
    job             text        NOT NULL,           -- 'live', 'stations', 'backfill-eccc-30d', ...
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    status          text        NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'ok', 'partial', 'error')),
    items_total     int NOT NULL DEFAULT 0,         -- files / sites / gauges attempted
    items_fetched   int NOT NULL DEFAULT 0,         -- payloads downloaded (HTTP 200)
    items_unchanged int NOT NULL DEFAULT 0,         -- HTTP 304 or not modified per listing
    items_failed    int NOT NULL DEFAULT 0,
    rows_inserted   bigint NOT NULL DEFAULT 0,
    rows_updated    bigint NOT NULL DEFAULT 0,
    rows_unchanged  bigint NOT NULL DEFAULT 0,
    rows_stale      bigint NOT NULL DEFAULT 0,      -- incoming value older than the stored version; ignored
    error_text      text,
    details         jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX ingest_runs_source_started ON ingest_runs (source, job, started_at DESC);

-- Conditional-GET state per URL (survives restarts; raw_objects dedupes identical payloads, so it
-- cannot tell us the newest Last-Modified we have seen).
CREATE TABLE fetch_state (
    url            text PRIMARY KEY,
    last_modified  timestamptz,
    last_status    int,
    checked_at     timestamptz NOT NULL DEFAULT now()
);

-- Resumable backfills: one row per completed chunk.
CREATE TABLE backfill_chunks (
    job          text        NOT NULL,
    key          text        NOT NULL,              -- e.g. 'usgs:12210700:00065'
    chunk_start  timestamptz NOT NULL,
    chunk_end    timestamptz NOT NULL,
    rows         bigint      NOT NULL,
    finished_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (job, key, chunk_start)
);

-- Append-only guards.
CREATE FUNCTION forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only (% not allowed)', TG_TABLE_NAME, TG_OP;
END;
$$;
CREATE TRIGGER observation_revisions_append_only
    BEFORE UPDATE OR DELETE ON observation_revisions
    FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER official_forecasts_append_only
    BEFORE UPDATE OR DELETE ON official_forecasts
    FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER raw_objects_append_only
    BEFORE UPDATE OR DELETE ON raw_objects
    FOR EACH ROW EXECUTE FUNCTION forbid_change();
