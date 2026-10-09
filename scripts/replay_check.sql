-- Independent check of /v1/replay/overflow (Stage 2, AC-9): the same definitions (D-02.4) written as one SQL query,
-- sharing no code with src/floodlead/replay.py. Run: psql -f scripts/replay_check.sql
-- event   = a run of North Cedarville (usgs:12210700) levels >= 146.5 ft, runs < 48 h apart merged
-- peak    = max level in [minor_first - 24 h, minor_last + 24 h]
-- gauge   = the window [minor_first - 12 h, ...] starts after the overflow gauge record begins
-- onset   = first overflow-gauge (usgs:12211195) record in [minor_first - 12 h, minor_last + 24 h] before 2026-10-01,
--           or the first >= 3.6 ft (its action stage) from then on; Cedarville level = latest reading at or before it
--
-- Safety: `observations` is a hypertable with >1,000 chunks. Correlated subqueries against it without constant time
-- bounds plan every chunk per subquery; the first version of this file did that and was OOM-killed inside the db
-- container (2.5 GiB) on 2026-10-09 01:38Z. So the two stations' level rows are copied once into a session temp table
-- (one scan, like replay.py's own queries) and everything else runs on that small table.
SET statement_timeout = '5min';
CREATE TEMP TABLE lv AS
    SELECT station_id, ts, raw_value FROM observations
    WHERE station_id IN ('usgs:12210700', 'usgs:12211195') AND param = 'level' AND NOT is_sentinel;
CREATE INDEX ON lv (station_id, ts);
ANALYZE lv;

WITH minor AS (
    SELECT ts FROM lv WHERE station_id = 'usgs:12210700' AND raw_value >= 146.5
), flagged AS (
    SELECT ts, CASE WHEN ts - lag(ts) OVER (ORDER BY ts) < interval '48 hours' THEN 0 ELSE 1 END AS new_event
    FROM minor
), numbered AS (
    SELECT ts, sum(new_event) OVER (ORDER BY ts) AS ev FROM flagged
), events AS (
    SELECT ev, min(ts) AS minor_first, max(ts) AS minor_last FROM numbered GROUP BY ev
), rec AS (
    SELECT min(ts) AS begins FROM lv WHERE station_id = 'usgs:12211195'
), detail AS (
    SELECT e.ev, e.minor_first,
           (SELECT max(raw_value) FROM lv o WHERE o.station_id = 'usgs:12210700'
              AND o.ts BETWEEN e.minor_first - interval '24 hours'
              AND e.minor_last + interval '24 hours') AS peak_ft,
           e.minor_first - interval '12 hours' >= rec.begins AS gauge,
           (SELECT min(o.ts) FROM lv o WHERE o.station_id = 'usgs:12211195'
              AND o.ts BETWEEN e.minor_first - interval '12 hours'
              AND e.minor_last + interval '24 hours'
              AND (o.ts < '2026-10-01T00:00:00Z' OR o.raw_value >= 3.6)) AS onset
    FROM events e, rec
), summary AS (
    SELECT d.*,
           (SELECT o.raw_value FROM lv o WHERE o.station_id = 'usgs:12210700' AND o.ts <= d.onset
              ORDER BY o.ts DESC LIMIT 1) AS onset_ft,
           round((extract(epoch FROM d.onset - d.minor_first) / 3600)::numeric, 2) AS hours_after_minor
    FROM detail d
)
SELECT count(*) AS events_total,
       count(*) FILTER (WHERE gauge) AS events_with_gauge,
       count(*) FILTER (WHERE gauge AND onset IS NOT NULL) AS events_with_overflow,
       min(onset_ft) FILTER (WHERE gauge) AS onset_ft_min,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY onset_ft) FILTER (WHERE gauge) AS onset_ft_median,
       max(onset_ft) FILTER (WHERE gauge) AS onset_ft_max,
       min(hours_after_minor) FILTER (WHERE gauge) AS hours_min,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY hours_after_minor) FILTER (WHERE gauge) AS hours_median,
       max(hours_after_minor) FILTER (WHERE gauge) AS hours_max,
       array_agg(peak_ft ORDER BY peak_ft) FILTER (WHERE gauge AND onset IS NOT NULL) AS peaks_with_overflow_ft,
       array_agg(peak_ft ORDER BY peak_ft) FILTER (WHERE gauge AND onset IS NULL) AS peaks_without_overflow_ft
FROM summary;
