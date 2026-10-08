-- 003_scores: derived scores (not ledger entries). Reproducible from the ledger plus observations; rewritten when a
-- truth observation is revised. Additive: new tables only.

CREATE TABLE scorer_runs (
    scorer_run_id bigserial PRIMARY KEY,
    started_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz,
    status        text NOT NULL DEFAULT 'running',
    scored        int NOT NULL DEFAULT 0,
    rescored      int NOT NULL DEFAULT 0,
    details       jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE forecast_scores (
    seq                   bigint      NOT NULL REFERENCES ledger_entries (seq),
    h                     int         NOT NULL,
    station_id            text        NOT NULL,
    source                text        NOT NULL,      -- 'eccc' | 'usgs'
    model                 text        NOT NULL,
    base_time             timestamptz NOT NULL,
    valid_at              timestamptz NOT NULL,
    stale_inputs          boolean     NOT NULL,
    status                text        NOT NULL CHECK (status IN ('scored', 'no_truth')),
    truth_ts              timestamptz,
    truth_m               double precision,
    truth_first_seen_at   timestamptz,
    truth_revision_count  int,
    q50_m                 double precision,
    crps                  double precision,             -- quantile-score approximation (2 x mean pinball loss)
    ae_median             double precision,
    in_50                 boolean,
    in_80                 boolean,
    in_90                 boolean,
    pit_bin               int,                          -- 0..7: below q05, q05-q10, ..., above q95
    event_status          text CHECK (event_status IN ('ok', 'insufficient_truth')),
    window_coverage       double precision,
    window_max_m          double precision,
    events                jsonb NOT NULL DEFAULT '{}'::jsonb,  -- {threshold_key: {p, outcome, brier}}
    noaa                  jsonb,                             -- matched NOAA comparison where applicable
    scored_at             timestamptz NOT NULL,
    scorer_run_id         bigint REFERENCES scorer_runs (scorer_run_id),
    PRIMARY KEY (seq, h)
);
CREATE INDEX forecast_scores_lookup ON forecast_scores (model, h, source, base_time);
CREATE INDEX forecast_scores_pair ON forecast_scores (station_id, base_time, h);

CREATE TABLE score_summaries (
    scorer_run_id bigint PRIMARY KEY REFERENCES scorer_runs (scorer_run_id),
    generated_at  timestamptz NOT NULL,
    body          jsonb NOT NULL
);
