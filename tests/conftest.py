"""Shared fixtures. DB tests run against a disposable database created on the server named by
FLOODLEAD_TEST_DSN (an admin DSN), or by the settings in .env with host localhost. The database is
created per test session with a `floodlead_test_` prefix and dropped afterwards; the production
database is never touched. If no server is reachable, DB tests are skipped (reported as skips)."""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from floodlead import db
from floodlead.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _admin_dsn() -> str:
    env = os.environ.get("FLOODLEAD_TEST_DSN")
    if env:
        return env
    s = Settings(postgres_host=os.environ.get("POSTGRES_HOST", "localhost"))
    return s.dsn().rsplit("/", 1)[0] + "/postgres"


@pytest.fixture(scope="session")
def test_dsn() -> Iterator[str]:
    admin = _admin_dsn()
    try:
        conn = psycopg.connect(admin, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError as e:
        pytest.skip(f"no PostgreSQL/TimescaleDB server for DB tests: {e}")
    name = f"floodlead_test_{secrets.token_hex(4)}"
    assert name.startswith("floodlead_test_")
    conn.execute(f'CREATE DATABASE "{name}"')
    dsn = admin.rsplit("/", 1)[0] + "/" + name
    try:
        db.migrate(dsn)
        yield dsn
    finally:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.close()


@pytest.fixture
def conn(test_dsn: str) -> Iterator[psycopg.Connection]:
    with db.connect(test_dsn, autocommit=True) as c:
        yield c
        # Clean mutable tables between tests (append-only guards apply to the production tables'
        # semantics; in the disposable DB we truncate, which is not blocked by row triggers).
        c.execute("TRUNCATE observations, observation_revisions, official_forecasts, raw_objects, stations,"
                  " ingest_runs, fetch_state, backfill_chunks")
