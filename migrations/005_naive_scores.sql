-- 005_naive_scores (Stage 2, addendum 2 item 4): scores for pure persistence ("persistence-naive"): the level at
-- data_as_of as a point forecast at every horizon, computed by the scorer from the existing persistence-v1 ledger
-- entries (the value is already fixed there, so no new ledger entries). Additive: a new table and a view.

CREATE TABLE forecast_scores_naive (LIKE forecast_scores INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES);

CREATE VIEW all_scores AS
    SELECT * FROM forecast_scores
    UNION ALL
    SELECT * FROM forecast_scores_naive;
