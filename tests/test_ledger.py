"""Ledger: golden vector, canonicalisation, tamper detection, database guards, gapless concurrent appends."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import UTC, datetime

import psycopg
import pytest

from floodlead import db, ledger

GOLDEN = [
    ('{"created_at":"2026-10-08T20:00:00.000Z","data":{"chain":"floodlead-ledger-v1","note":"golden vector",'
     '"π":3.1416},"entry_type":"genesis","seq":1}',
     "4f02a159d797b56810d422afce63f20d47455a086f83bf582263d35985e2fa4e"),
    ('{"created_at":"2026-10-08T20:15:03.123Z","data":{"p":0.0001,"q":{"0.5":42.0685},"stale":false,'
     '"station_id":"usgs:12210700","x":null},"entry_type":"forecast","seq":2}',
     "74873df1285247e90aa859d27b11ba17d66b2c76c03e129f3c7b0bc9b5cd4b1e"),
]


def test_golden_vector() -> None:
    """Also in docs/ledger-spec.md; cross-checked with `sha256sum` (printf '%s\\n%s' prev canonical)."""
    c1 = ledger.canonical_json({"seq": 1, "entry_type": "genesis", "created_at": "2026-10-08T20:00:00.000Z",
                                "data": {"chain": "floodlead-ledger-v1", "note": "golden vector", "π": 3.1416}})
    c2 = ledger.canonical_json({"seq": 2, "entry_type": "forecast", "created_at": "2026-10-08T20:15:03.123Z",
                                "data": {"station_id": "usgs:12210700", "q": {"0.5": 42.0685}, "p": 0.0001,
                                         "stale": False, "x": None}})
    assert (c1, c2) == (GOLDEN[0][0], GOLDEN[1][0])
    h1 = ledger.entry_hash(ledger.ZERO_HASH, c1)
    assert h1 == GOLDEN[0][1]
    assert ledger.entry_hash(h1, c2) == GOLDEN[1][1]


def test_rounding_and_timestamps() -> None:
    assert ledger.r4(42.06851) == 42.0685 and ledger.r4(-0.00001) == 0.0 and ledger.r4(float("nan")) is None
    assert ledger.ts(datetime(2026, 10, 8, 20, 15, 3, 123456, tzinfo=UTC), ms=True) == "2026-10-08T20:15:03.123Z"
    assert ledger.ts(datetime(2026, 10, 8, 20, 0, tzinfo=UTC)) == "2026-10-08T20:00:00Z"
    with pytest.raises(ValueError):
        ledger.canonical_json({"x": float("inf")})


def _chain(n: int) -> list[tuple[int, str, str, str, str]]:
    rows, prev = [], ledger.ZERO_HASH
    for seq in range(1, n + 1):
        c = ledger.canonical_json({"seq": seq, "entry_type": "genesis" if seq == 1 else "forecast",
                                   "created_at": "2026-10-08T20:00:00.000Z", "data": {"v": seq / 10}})
        h = ledger.entry_hash(prev, c)
        rows.append((seq, "genesis" if seq == 1 else "forecast", c, prev, h))
        prev = h
    return rows


def test_verify_detects_tampering_at_the_right_seq() -> None:
    rows = _chain(6)
    assert ledger.verify_rows(rows).ok
    # one changed byte in entry 4's canonical text
    bad = list(rows)
    s, t, c, p, h = bad[3]
    bad[3] = (s, t, c.replace('"v":0.4', '"v":0.5'), p, h)
    r = ledger.verify_rows(bad)
    assert not r.ok and r.failed_seq == 4 and "canonical" in (r.error or "")
    # a swapped pair (entries 3 and 4)
    sw = list(rows)
    sw[2], sw[3] = sw[3], sw[2]
    r = ledger.verify_rows(sw)
    assert not r.ok and r.failed_seq == 4
    # a deleted entry (5)
    r = ledger.verify_rows(rows[:4] + rows[5:])
    assert not r.ok and r.failed_seq == 6 and "gap" in (r.error or "")
    # starting mid-chain from an anchored entry
    r = ledger.verify_rows(rows[3:], start_prev=rows[2][4], start_seq=4)
    assert r.ok and r.entries == 3


@pytest.fixture
def lconn(test_dsn: str) -> Iterator[psycopg.Connection]:
    with db.connect(test_dsn, autocommit=True) as c:
        yield c
        # Disposable test database only: bypass the append-only triggers to reset between tests.
        c.execute("SET session_replication_role = replica")
        c.execute("TRUNCATE forecast_scores, score_summaries, scorer_runs, ledger_anchors, ledger_entries")
        c.execute("SET session_replication_role = DEFAULT")


def _pend(i: int) -> ledger.Pending:
    return ledger.Pending("forecast", {"i": i}, datetime(2026, 10, 8, 20, 15, tzinfo=UTC), station_id="s",
                          model="m", base_time=datetime(2026, 10, 8, 20, tzinfo=UTC))


def test_append_creates_genesis_and_db_verifies(lconn: psycopg.Connection) -> None:
    with lconn.transaction():
        written = ledger.append(lconn, [_pend(1), _pend(2)])
    assert [e.seq for e in written] == [1, 2, 3] and written[0].entry_type == "genesis"
    assert written[0].prev_hash == ledger.ZERO_HASH and written[1].prev_hash == written[0].entry_hash
    r = ledger.verify_db(lconn)
    assert r.ok and r.entries == 3 and r.by_type == {"genesis": 1, "forecast": 2}


def test_db_rejects_update_delete_truncate_and_bad_appends(lconn: psycopg.Connection) -> None:
    with lconn.transaction():
        ledger.append(lconn, [_pend(1)])
    for sql in ("UPDATE ledger_entries SET canonical = canonical WHERE seq = 2",
                "DELETE FROM ledger_entries WHERE seq = 2",
                "TRUNCATE forecast_scores, ledger_anchors, ledger_entries"):
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            lconn.execute(sql)
    last_seq, last_hash = ledger.head(lconn)
    c = ledger.canonical_json({"seq": last_seq + 2, "entry_type": "gap", "created_at": "x", "data": {}})
    with pytest.raises(psycopg.errors.RaiseException, match="append must have seq"):  # skipped seq
        lconn.execute("INSERT INTO ledger_entries (seq, entry_type, created_at, canonical, prev_hash, entry_hash)"
                      " VALUES (%s, 'gap', now(), %s, %s, %s)",
                      (last_seq + 2, c, last_hash, ledger.entry_hash(last_hash, c)))
    c = ledger.canonical_json({"seq": last_seq + 1, "entry_type": "gap", "created_at": "x", "data": {}})
    with pytest.raises(psycopg.errors.RaiseException, match="entry_hash does not match"):  # wrong hash
        lconn.execute("INSERT INTO ledger_entries (seq, entry_type, created_at, canonical, prev_hash, entry_hash)"
                      " VALUES (%s, 'gap', now(), %s, %s, %s)", (last_seq + 1, c, last_hash, "0" * 64))


def test_concurrent_appends_stay_gapless(lconn: psycopg.Connection, test_dsn: str) -> None:
    with lconn.transaction():
        ledger.append(lconn, [_pend(0)])
    start = ledger.head(lconn)[0]
    errors: list[BaseException] = []

    def worker(k: int) -> None:
        try:
            with db.connect(test_dsn, autocommit=True) as c:
                for j in range(5):
                    with c.transaction():
                        ledger.append(c, [_pend(k * 100 + j), _pend(k * 100 + j + 50)])
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    r = ledger.verify_db(lconn)
    assert r.ok and r.entries == start + 4 * 5 * 2 and r.last_seq == r.entries
