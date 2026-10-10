-- 008_feedback (Stage 3, part 1 item 2): anonymous in-app feedback. New table only.
-- No name, email, phone or IP address is stored. The free text is encrypted at rest (Fernet; key FEEDBACK_KEY in .env,
-- never logged) and is decrypted only by `floodlead feedback list` on the VM. Append-only: UPDATE, DELETE and TRUNCATE
-- are rejected, as for the ledger.
CREATE TABLE feedback (
    feedback_id   bigserial   PRIMARY KEY,
    received_at   timestamptz NOT NULL DEFAULT now(),
    route         text        NOT NULL,
    station_id    text,
    useful        boolean,
    text_enc      bytea,                 -- Fernet token of the UTF-8 text; NULL when no text was given
    text_chars    int         NOT NULL DEFAULT 0,
    key_id        text,                  -- first 8 hex of sha256(key), to tell keys apart after a rotation
    app_version   text
);
CREATE INDEX feedback_received ON feedback (received_at DESC);

CREATE FUNCTION feedback_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'feedback is append-only (% not allowed)', TG_OP;
END $$;
CREATE TRIGGER feedback_no_update BEFORE UPDATE OR DELETE ON feedback
    FOR EACH ROW EXECUTE FUNCTION feedback_append_only();
CREATE TRIGGER feedback_no_truncate BEFORE TRUNCATE ON feedback
    FOR EACH STATEMENT EXECUTE FUNCTION feedback_append_only();
