-- 002_ledger: the public forecast ledger. Additive: new tables only.
-- One global append-only, hash-chained sequence of entries. The database itself enforces the chain on insert:
-- seq = previous seq + 1 (genesis = 1), prev_hash = previous entry_hash (genesis: 64 zeros) and
-- entry_hash = hex(sha256(prev_hash || '\n' || canonical)). UPDATE, DELETE and TRUNCATE are rejected.
-- Tamper-evident, not tamper-proof: a superuser can disable triggers; external anchors (ledger branch) catch that.

CREATE TABLE ledger_entries (
    seq         bigint      PRIMARY KEY,
    entry_type  text        NOT NULL CHECK (entry_type IN
                    ('genesis', 'model_card', 'issuance', 'forecast', 'official_forecast', 'gap')),
    created_at  timestamptz NOT NULL,
    canonical   text        NOT NULL,          -- the exact UTF-8 JSON text that was hashed
    prev_hash   text        NOT NULL CHECK (prev_hash ~ '^[0-9a-f]{64}$'),
    entry_hash  text        NOT NULL UNIQUE CHECK (entry_hash ~ '^[0-9a-f]{64}$'),
    -- query columns (copies of values inside `canonical`; never used for verification)
    station_id  text,
    model       text,
    base_time   timestamptz,
    lid         text
);
CREATE INDEX ledger_forecast_lookup ON ledger_entries (station_id, model, base_time DESC) WHERE entry_type = 'forecast';
CREATE INDEX ledger_type_base ON ledger_entries (entry_type, base_time DESC);

CREATE FUNCTION ledger_check_append() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    last_seq  bigint;
    last_hash text;
BEGIN
    SELECT seq, entry_hash INTO last_seq, last_hash FROM ledger_entries ORDER BY seq DESC LIMIT 1;
    IF last_seq IS NULL THEN
        IF NEW.seq <> 1 OR NEW.prev_hash <> repeat('0', 64) OR NEW.entry_type <> 'genesis' THEN
            RAISE EXCEPTION 'ledger: first entry must be genesis with seq 1 and a zero prev_hash';
        END IF;
    ELSIF NEW.seq <> last_seq + 1 OR NEW.prev_hash <> last_hash THEN
        RAISE EXCEPTION 'ledger: append must have seq % and prev_hash %', last_seq + 1, last_hash;
    END IF;
    IF NEW.entry_hash <> encode(sha256(convert_to(NEW.prev_hash || E'\n' || NEW.canonical, 'UTF8')), 'hex') THEN
        RAISE EXCEPTION 'ledger: entry_hash does not match sha256(prev_hash || newline || canonical)';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER ledger_entries_check_append BEFORE INSERT ON ledger_entries
    FOR EACH ROW EXECUTE FUNCTION ledger_check_append();
CREATE TRIGGER ledger_entries_append_only BEFORE UPDATE OR DELETE ON ledger_entries
    FOR EACH ROW EXECUTE FUNCTION forbid_change();

CREATE FUNCTION forbid_truncate() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only (TRUNCATE not allowed)', TG_TABLE_NAME;
END;
$$;
CREATE TRIGGER ledger_entries_no_truncate BEFORE TRUNCATE ON ledger_entries
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_truncate();

-- Anchors: each hourly publication of the chain head (and that hour's entries) to the `ledger` branch.
CREATE TABLE ledger_anchors (
    anchor_id    bigserial   PRIMARY KEY,
    seq          bigint      NOT NULL REFERENCES ledger_entries (seq),
    entry_hash   text        NOT NULL,
    anchored_at  timestamptz NOT NULL,
    commit_sha   text,
    commit_url   text,
    entries_path text,
    entries_bytes bigint,
    status       text        NOT NULL CHECK (status IN ('ok', 'error')),
    error_text   text
);
CREATE TRIGGER ledger_anchors_append_only BEFORE UPDATE OR DELETE ON ledger_anchors
    FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER ledger_anchors_no_truncate BEFORE TRUNCATE ON ledger_anchors
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_truncate();
