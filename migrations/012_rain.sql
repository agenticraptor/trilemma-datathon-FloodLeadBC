-- 012_rain (Stage 3 part 2): hourly precipitation and temperature history, parsed from archived payloads. New tables.
-- ts = END of the hour the value covers, UTC.
CREATE TABLE rain_hourly (
    source         text        NOT NULL,     -- 'eccc-climate', 'ncei', 'snotel'
    site           text        NOT NULL,     -- climate id, ISD id, SNOTEL triplet
    ts             timestamptz NOT NULL,
    precip_mm      real,                     -- amount in the hour ending at ts
    temp_c         real,
    swe_mm         real,                     -- SNOTEL snow water equivalent
    snow_depth_cm  real,                     -- SNOTEL snow depth
    flags          text,
    raw_object_id  bigint REFERENCES raw_objects (raw_object_id),
    PRIMARY KEY (source, site, ts)
);

CREATE TABLE openmeteo_hourly (
    kind           text        NOT NULL,     -- 'archive' (reanalysis), 'histfc' (historical forecast), 'prevruns'
    point          text        NOT NULL,     -- basin point name (src/floodlead/history/tasks.py BASIN_POINTS)
    ts             timestamptz NOT NULL,     -- Open-Meteo hourly time (UTC); values are for the preceding hour
    precip_mm      real,
    rain_mm        real,
    snowfall_cm    real,
    temp_c         real,
    snow_depth_m   real,
    soil_moisture  real,                     -- 0-7 cm, m3/m3 (archive)
    freezing_level_m real,                   -- histfc
    precip_prev_day1_mm real,                -- prevruns: as forecast 1 day before
    precip_prev_day2_mm real,                -- prevruns: as forecast 2 days before
    temp_prev_day1_c real,
    temp_prev_day2_c real,
    raw_object_id  bigint REFERENCES raw_objects (raw_object_id),
    PRIMARY KEY (kind, point, ts)
);
