-- 004_payload_coverage (Stage 2, F2): per-station "last seen" outside the observations hypertable.
-- Identical re-fetches no longer write observation rows; this table keeps, per station and payload kind, the newest
-- payload's publication time and the time range it covered, so an older payload can never overwrite a value that a
-- newer payload already covered (the out-of-order guard). Additive: a new table only.

CREATE TABLE payload_coverage (
    station_id     text        NOT NULL,
    kind           text        NOT NULL,   -- 'eccc:hourly', 'eccc:daily', 'usgs:ogc', 'usgs:nwis'
    published_at   timestamptz NOT NULL,   -- newest payload of this kind for this station
    ts_min         timestamptz NOT NULL,
    ts_max         timestamptz NOT NULL,
    raw_object_id  bigint,
    last_seen_at   timestamptz NOT NULL,   -- when a payload of this kind for this station was last processed
    PRIMARY KEY (station_id, kind)
);
