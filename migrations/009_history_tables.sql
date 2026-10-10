-- 009_history_tables (Stage 3): parsed ECCC history, in new tables (never the 15-min `observations` hypertable, F3),
-- and FloodLead's typical yearly peak per BC station. Derived from archived payloads (history_downloads).

CREATE TABLE eccc_annual_peaks (
    station_number  text        NOT NULL,
    year            int         NOT NULL,
    data_type       text        NOT NULL CHECK (data_type IN ('level', 'discharge')),
    peak_code       text        NOT NULL CHECK (peak_code IN ('max', 'min')),
    peak_at         timestamptz,                 -- DATE + TIMEZONE_OFFSET (station standard time)
    value           double precision NOT NULL,   -- m (level) or m3/s (discharge)
    symbol          text,                        -- 'Estimated', 'Ice Conditions', 'Partial Day' or NULL
    raw_object_id   bigint REFERENCES raw_objects (raw_object_id),
    PRIMARY KEY (station_number, data_type, peak_code, year)
);

CREATE TABLE eccc_daily (
    station_number    text  NOT NULL,
    date              date  NOT NULL,
    level             real,                      -- daily mean water level, m
    discharge         real,                      -- daily mean discharge, m3/s
    level_symbol      text,
    discharge_symbol  text,
    raw_object_id     bigint REFERENCES raw_objects (raw_object_id),
    PRIMARY KEY (station_number, date)
);

CREATE TABLE typical_peaks (
    method        text        NOT NULL,          -- e.g. 'typical-peak-v1'
    station_id    text        NOT NULL,          -- 'eccc:08MH029'
    status        text        NOT NULL CHECK (status IN ('ok', 'flagged', 'rejected', 'insufficient')),
    value_m       double precision,              -- NULL unless ok or flagged
    n_years       int         NOT NULL,
    first_year    int,
    last_year     int,
    reason        text,
    checks        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    computed_at   timestamptz NOT NULL,
    PRIMARY KEY (method, station_id)
);
