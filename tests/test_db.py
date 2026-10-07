"""Upsert idempotency, revision capture, the out-of-order guard, append-only guards and the raw
archive index, against a disposable TimescaleDB database."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from floodlead import archive, store
from floodlead.http import Fetched
from floodlead.sources import eccc, nwps
from tests.conftest import fixture_bytes

PUB = datetime(2026, 10, 7, 21, 1, 28, tzinfo=UTC)  # Last-Modified of the 08MH001 fixture


def _rows() -> list[store.Obs]:
    return eccc.parse_csv(fixture_bytes("eccc_hourly_08MH001.csv"), PUB)


def _upsert(conn: psycopg.Connection, rows: list[store.Obs], now: datetime) -> store.UpsertResult:
    with conn.transaction():
        return store.upsert_observations(conn, rows, None, now=now)


def test_insert_then_identical_refetch_changes_only_last_seen(conn: psycopg.Connection) -> None:
    t1 = datetime(2026, 10, 7, 21, 0, tzinfo=UTC)
    r1 = _upsert(conn, _rows(), t1)
    assert (r1.inserted, r1.updated, r1.unchanged) == (16, 0, 0)
    t2 = t1 + timedelta(hours=1)
    r2 = _upsert(conn, _rows(), t2)
    assert (r2.inserted, r2.updated, r2.unchanged, r2.stale) == (0, 0, 16, 0)
    row = conn.execute(
        "SELECT first_seen_at, last_seen_at, revision_count, revised_at FROM observations"
        " WHERE station_id = 'eccc:08MH001' AND param = 'level' ORDER BY ts LIMIT 1").fetchone()
    assert row == (t1, t2, 0, None)
    assert conn.execute("SELECT count(*) FROM observation_revisions").fetchone()[0] == 0


def test_changed_value_is_revised_and_history_appended(conn: psycopg.Connection) -> None:
    t1 = datetime(2026, 10, 7, 21, 0, tzinfo=UTC)
    rows = _rows()
    _upsert(conn, rows, t1)
    newer = PUB + timedelta(hours=1)
    changed = [dataclasses.replace(r, published_at=newer) for r in rows]
    changed[0] = dataclasses.replace(changed[0], raw_value=1.700, value=1.700,
                                     quality={"grade": None, "symbol": "B", "qaqc": "2"})
    r = _upsert(conn, changed, t1 + timedelta(hours=1))
    assert (r.inserted, r.updated, r.unchanged, r.stale) == (0, 1, 15, 0)
    obs = conn.execute(
        "SELECT value, revision_count, revised_at IS NOT NULL FROM observations"
        " WHERE station_id = %s AND ts = %s AND param = %s",
        (changed[0].station_id, changed[0].ts, changed[0].param)).fetchone()
    assert obs == (1.7, 1, True)
    rev = conn.execute("SELECT old_value, new_value, old_quality->>'qaqc', new_quality->>'qaqc'"
                       " FROM observation_revisions").fetchall()
    assert rev == [(1.618, 1.7, "1", "2")]


def test_older_payload_cannot_revise_newer_value(conn: psycopg.Connection) -> None:
    t1 = datetime(2026, 10, 7, 21, 0, tzinfo=UTC)
    rows = _rows()
    _upsert(conn, rows, t1)
    older = [dataclasses.replace(r, published_at=PUB - timedelta(hours=12)) for r in rows]
    older[0] = dataclasses.replace(older[0], raw_value=9.0, value=9.0)
    r = _upsert(conn, older, t1 + timedelta(hours=1))
    assert (r.updated, r.stale, r.unchanged) == (0, 1, 15)
    v = conn.execute("SELECT value FROM observations WHERE station_id = %s AND ts = %s AND param = %s",
                     (rows[0].station_id, rows[0].ts, rows[0].param)).fetchone()[0]
    assert v == 1.618
    assert conn.execute("SELECT count(*) FROM observation_revisions").fetchone()[0] == 0


def test_sentinels_are_stored_and_flagged(conn: psycopg.Connection) -> None:
    rows = eccc.parse_csv(fixture_bytes("eccc_daily_08NJ026_sentinel.csv"), PUB)
    _upsert(conn, rows, datetime(2026, 10, 7, 21, 0, tzinfo=UTC))
    got = conn.execute("SELECT raw_value, value, is_sentinel FROM observations WHERE is_sentinel").fetchall()
    assert got == [(99999.0, None, True)]


def test_append_only_tables_reject_update_and_delete(conn: psycopg.Connection) -> None:
    rows = _rows()
    _upsert(conn, rows, datetime(2026, 10, 7, 21, 0, tzinfo=UTC))
    changed = [dataclasses.replace(rows[0], raw_value=2.0, value=2.0, published_at=PUB + timedelta(hours=1))]
    _upsert(conn, changed, datetime(2026, 10, 7, 22, 0, tzinfo=UTC))
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        conn.execute("UPDATE observation_revisions SET new_value = 0")
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        conn.execute("DELETE FROM observation_revisions")


def _fetched(content: bytes, url: str = "https://example.test/x.csv") -> Fetched:
    return Fetched(url=url, status=200, content=content, last_modified=PUB,
                   fetched_at=datetime(2026, 10, 7, 21, 3, tzinfo=UTC), elapsed_s=0.1)


def test_raw_objects_dedupe_on_sha256(conn: psycopg.Connection, tmp_path) -> None:
    data = fixture_bytes("eccc_hourly_08MH001.csv")
    with conn.transaction():
        a = archive.store(conn, tmp_path, "eccc", "BC_08MH001_hourly_hydrometric.csv", _fetched(data))
    with conn.transaction():
        b = archive.store(conn, tmp_path, "eccc", "BC_08MH001_hourly_hydrometric.csv", _fetched(data))
    assert a.is_new and not b.is_new and a.raw_object_id == b.raw_object_id
    row = conn.execute("SELECT sha256, bytes, archive_path FROM raw_objects").fetchall()
    assert len(row) == 1 and row[0][0] == archive.sha256_hex(data) and row[0][1] == len(data)
    assert (tmp_path / row[0][2]).exists()
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        conn.execute("DELETE FROM raw_objects")


def test_archive_failure_does_not_block_index(conn: psycopg.Connection, tmp_path) -> None:
    blocker = tmp_path / "raw"
    blocker.write_text("a file where a directory should be")  # makes mkdir fail
    with conn.transaction():
        ref = archive.store(conn, tmp_path, "eccc", "x.csv", _fetched(b"payload"))
    row = conn.execute("SELECT archive_path, archive_error FROM raw_objects WHERE raw_object_id = %s",
                       (ref.raw_object_id,)).fetchone()
    assert row[0] is None and row[1]


def test_official_forecasts_insert_once(conn: psycopg.Connection, tmp_path) -> None:
    import json

    payload = fixture_bytes("nwps_stageflow_NRKW1.json")
    with conn.transaction():
        ref = archive.store(conn, tmp_path, "nwps", "stageflow_NRKW1", _fetched(payload))
    _, rows = nwps.parse_forecast(json.loads(payload))
    with conn.transaction():
        assert nwps.store_forecast(conn, "NRKW1", rows, PUB, ref.raw_object_id) == 4
    with conn.transaction():
        assert nwps.store_forecast(conn, "NRKW1", rows, PUB, ref.raw_object_id) == 0
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        conn.execute("UPDATE official_forecasts SET stage_ft = 0")


def test_nwps_attaches_thresholds_without_renaming_usgs_station(conn: psycopg.Connection) -> None:
    import json

    store.upsert_station_meta(conn, {"station_id": "usgs:12210700", "source": "usgs", "native_id": "12210700",
                                     "name": "NOOKSACK RIVER AT NORTH CEDARVILLE, WA", "region": "WA"})
    g = json.loads(fixture_bytes("nwps_gauge_NRKW1.json"))
    nwps.attach_to_station(conn, "12210700", "NRKW1", g, None)
    name, thr, links = conn.execute(
        "SELECT name, official_thresholds, links FROM stations WHERE station_id = 'usgs:12210700'").fetchone()
    assert name == "NOOKSACK RIVER AT NORTH CEDARVILLE, WA"
    assert thr["categories"]["minor"]["stage_ft"] == 146.5
    assert links["nwps_lid"] == "NRKW1"


def test_migrations_are_recorded(conn: psycopg.Connection) -> None:
    versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY 1")]
    assert versions[0] == "001_init.sql"
    ht = conn.execute("SELECT hypertable_name FROM timescaledb_information.hypertables").fetchall()
    assert ("observations",) in ht
