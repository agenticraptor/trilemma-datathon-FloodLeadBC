-- Leakage audit over every `forecast` ledger entry (Stage 2, AC-7). Run: psql -f scripts/audit_leakage.sql
-- 1. data_as_of must not be after created_at, and the observation at data_as_of must have been visible then
--    (first_seen_at <= created_at).
-- 2. inputs_n must equal the number of level rows in the 3 h window ending at data_as_of that were visible at
--    created_at (ts <= created_at and first_seen_at <= created_at): a later-seen row in the inputs would change it.
--    (Each forecast's input_hash can also be recomputed from the public API: scripts/reproduce_forecast.py.)
-- 3. No horizon with valid_at - created_at < 30 min.
WITH f AS (
    SELECT seq, station_id, created_at,
           (canonical::jsonb -> 'data' ->> 'data_as_of')::timestamptz AS asof,
           (canonical::jsonb -> 'data' ->> 'inputs_n')::int AS inputs_n,
           canonical::jsonb -> 'data' -> 'horizons' AS hz
    FROM ledger_entries WHERE entry_type = 'forecast'
)
SELECT count(*) AS forecasts,
       count(*) FILTER (WHERE asof > created_at) AS data_as_of_after_created_at,
       count(*) FILTER (WHERE NOT EXISTS (
           SELECT 1 FROM observations o WHERE o.station_id = f.station_id AND o.param = 'level' AND o.ts = f.asof
             AND o.first_seen_at <= f.created_at)) AS data_as_of_row_not_visible_at_created_at,
       count(*) FILTER (WHERE inputs_n <> (
           SELECT count(*) FROM observations o WHERE o.station_id = f.station_id AND o.param = 'level'
             AND NOT o.is_sentinel AND o.value IS NOT NULL AND o.ts BETWEEN f.asof - interval '3 hours' AND f.asof
             AND o.ts <= f.created_at AND o.first_seen_at <= f.created_at)) AS inputs_count_mismatch,
       (SELECT count(*) FROM f f2, jsonb_array_elements(f2.hz) h
         WHERE (h ->> 'valid_at')::timestamptz - f2.created_at < interval '30 minutes') AS horizons_under_30_min,
       (SELECT count(*) FROM f f3, jsonb_array_elements(f3.hz) h) AS horizons_total
FROM f;
