-- 013_official_scorecard (Stage 3 addendum 1, item 3.1): materialised scorecard of archived NWS river flood products
-- against our gauge record. Derived; each build appends a new row.
CREATE TABLE official_scorecards (
    scorecard_id  bigserial   PRIMARY KEY,
    generated_at  timestamptz NOT NULL,
    body          jsonb       NOT NULL
);
