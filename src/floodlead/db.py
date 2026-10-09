"""Database connections and the SQL migration runner."""

from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

from floodlead import log
from floodlead.config import get_settings

L = log.get(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


# Server-side prepared statements are disabled: after 5 executions psycopg would prepare the
# upsert statements, and PostgreSQL's generic plan for the hypertable join (no plan-time chunk
# exclusion, no knowledge of the staging batch) took seconds per file instead of ~50 ms.
NO_PREPARE = {"prepare_threshold": None}


def connect(dsn: str | None = None, **kw: object) -> psycopg.Connection:
    return psycopg.connect(dsn or get_settings().dsn(), **{**NO_PREPARE, **kw})


def pool(dsn: str | None = None, min_size: int = 1, max_size: int = 6) -> ConnectionPool:
    # `check`: test each connection before handing it out. Without it, after a PostgreSQL restart every idle pooled
    # connection was dead and each next job failed once on it (2026-10-09 01:38Z: scorer, ECCC x2, USGS).
    p = ConnectionPool(dsn or get_settings().dsn(), min_size=min_size, max_size=max_size, open=False,
                       kwargs=dict(NO_PREPARE), check=ConnectionPool.check_connection)
    p.open(wait=True, timeout=60)
    return p


def migrate(dsn: str | None = None, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending `NNN_*.sql` files in order, each in its own transaction. Returns applied names."""
    applied: list[str] = []
    with connect(dsn, autocommit=True) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        # Serialise concurrent runners (ingest and api both migrate on start).
        conn.execute("SELECT pg_advisory_lock(hashtext('floodlead.migrate'))")
        try:
            done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
            for path in sorted(migrations_dir.glob("[0-9][0-9][0-9]_*.sql")):
                if path.name in done:
                    continue
                with conn.transaction():
                    conn.execute(path.read_text())
                    conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,))
                applied.append(path.name)
                L.info("migration applied", **log.kv(version=path.name))
        finally:
            conn.execute("SELECT pg_advisory_unlock(hashtext('floodlead.migrate'))")
    return applied
