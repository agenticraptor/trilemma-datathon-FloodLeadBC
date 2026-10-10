-- 007_crps_qs (Stage 3, F1): `crps` becomes the fair CRPS (rebuilt CDF, exact integral; D-03.4) and the quantile
-- score used until now moves to a secondary column `crps_qs`. Scores are derived data; the values are recomputed
-- by `floodlead score --recompute-crps` right after this migration. Touches existing tables: a pg_dump of the
-- score tables was taken first (stage doc).
ALTER TABLE forecast_scores ADD COLUMN crps_qs double precision;
ALTER TABLE forecast_scores_naive ADD COLUMN crps_qs double precision;

-- all_scores was created as SELECT * and keeps its original column list; recreate it with the new column.
CREATE OR REPLACE VIEW all_scores AS
    SELECT * FROM forecast_scores
    UNION ALL
    SELECT * FROM forecast_scores_naive;
