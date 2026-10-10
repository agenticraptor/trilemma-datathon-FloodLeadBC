-- Stage 3: manifest of one-off history downloads (raw payloads go to raw_objects + the archive, as always).
-- New table only; nothing existing is touched. Parsed history goes into separate new tables (never `observations`).
CREATE TABLE history_downloads (
    source         text        NOT NULL,   -- e.g. 'eccc-daily', 'iem-nws', 'openmeteo-archive'
    key            text        NOT NULL,   -- one task, e.g. '08MH029/0' or 'FLWSEW/2021'
    url            text        NOT NULL,
    status         text        NOT NULL,   -- 'ok' | 'error' | 'empty'
    http_status    int,
    bytes          bigint,
    raw_object_id  bigint REFERENCES raw_objects (raw_object_id),
    fetched_at     timestamptz NOT NULL,
    elapsed_s      real,
    error          text,
    PRIMARY KEY (source, key)
);
