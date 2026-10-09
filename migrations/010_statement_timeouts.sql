-- 010_statement_timeouts (Stage 3, F3): a backstop for every new session of this database that does not set its own:
-- no statement may run longer than 15 minutes, and no session may sit idle inside a transaction for more than 30
-- minutes. Ad-hoc and maintenance sessions use scripts/dbshell, which sets a tighter 5-minute limit and a smaller
-- work_mem. Long jobs that need more set their own (e.g. pg_dump sets 0). Applied to the current database by name, so
-- the disposable test database never changes production.
DO $$
BEGIN
    EXECUTE format('ALTER DATABASE %I SET statement_timeout = %L', current_database(), '15min');
    EXECUTE format('ALTER DATABASE %I SET idle_in_transaction_session_timeout = %L', current_database(), '30min');
END $$;
