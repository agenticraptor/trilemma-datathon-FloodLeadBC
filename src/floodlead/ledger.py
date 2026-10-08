"""The public forecast ledger: one global append-only, SHA-256 hash-chained sequence of entries.

Spec: docs/ledger-spec.md. In short:

- canonical = JSON with sorted keys, no insignificant whitespace, UTF-8 (non-ASCII kept), containing `seq`,
  `entry_type`, `created_at` and `data`; numbers are rounded before serialisation (levels 1e-4 m = 0.1 mm,
  probabilities 1e-4) and timestamps are RFC 3339 UTC with `Z`.
- entry_hash = hex(sha256(prev_hash_hex + "\\n" + canonical_utf8)); the genesis prev_hash is 64 zeros.
- Verifiers hash the stored canonical text; they never re-serialise numbers.

Appends are serialised with an advisory lock and checked again by a database trigger (migration 002).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psycopg

from floodlead import log
from floodlead.config import REPO_URL

L = log.get(__name__)

ZERO_HASH = "0" * 64
SPEC_VERSION = "floodlead-ledger-v1"
LOCK_KEY = "floodlead.ledger.append"


def ts(t: datetime, ms: bool = False) -> str:
    """RFC 3339 UTC with Z; whole seconds, or milliseconds when `ms`."""
    t = t.astimezone(UTC)
    if ms:
        return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def r4(x: float | None) -> float | None:
    """Round to 4 decimals (0.1 mm for metres, 1e-4 for probabilities); -0.0 becomes 0.0; NaN becomes None."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    v = round(float(x), 4)
    return 0.0 if v == 0 else v


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def entry_hash(prev_hash: str, canonical: str) -> str:
    return hashlib.sha256((prev_hash + "\n" + canonical).encode("utf-8")).hexdigest()


def code_commit() -> str:
    return os.environ.get("FLOODLEAD_GIT_SHA", "unknown")


@dataclass(frozen=True)
class Entry:
    seq: int
    entry_type: str
    created_at: datetime
    canonical: str
    prev_hash: str
    entry_hash: str


@dataclass
class Pending:
    entry_type: str
    data: dict[str, Any]
    created_at: datetime
    station_id: str | None = None
    model: str | None = None
    base_time: datetime | None = None
    lid: str | None = None


def head(conn: psycopg.Connection) -> tuple[int, str] | None:
    row = conn.execute("SELECT seq, entry_hash FROM ledger_entries ORDER BY seq DESC LIMIT 1").fetchone()
    return (row[0], row[1]) if row else None


def genesis_data() -> dict[str, Any]:
    return {
        "chain": SPEC_VERSION,
        "hash_rule": "entry_hash = hex(sha256(prev_hash_hex + '\\n' + canonical_utf8)); genesis prev_hash = 64 zeros",
        "canonical_rule": "JSON, sorted keys, separators (',', ':'), UTF-8, keys seq/entry_type/created_at/data; "
                          "levels and probabilities rounded to 4 decimals; timestamps RFC 3339 UTC with Z",
        "spec": "docs/ledger-spec.md",
        "repo": REPO_URL,
        "repo_commit": code_commit(),
        "purpose": "FloodLead BC forecasts and official forecasts, fixed in time before the truth is known.",
    }


def append(conn: psycopg.Connection, items: Iterable[Pending]) -> list[Entry]:
    """Append entries in order, inside the caller's transaction. Takes the ledger advisory lock (released at
    commit), so concurrent writers queue instead of forking; the insert trigger re-checks seq, prev_hash and the
    hash. Creates the genesis entry first if the ledger is empty."""
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK_KEY,))
    h = head(conn)
    items = list(items)
    if h is None:
        items.insert(0, Pending("genesis", genesis_data(), items[0].created_at if items else datetime.now(UTC)))
        seq, prev = 0, ZERO_HASH
    else:
        seq, prev = h
    out: list[Entry] = []
    for it in items:
        seq += 1
        canonical = canonical_json({"seq": seq, "entry_type": it.entry_type, "created_at": ts(it.created_at, ms=True),
                                    "data": it.data})
        eh = entry_hash(prev, canonical)
        conn.execute(
            "INSERT INTO ledger_entries (seq, entry_type, created_at, canonical, prev_hash, entry_hash, station_id,"
            " model, base_time, lid) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (seq, it.entry_type, it.created_at, canonical, prev, eh, it.station_id, it.model, it.base_time, it.lid),
        )
        out.append(Entry(seq, it.entry_type, it.created_at, canonical, prev, eh))
        prev = eh
    return out


@dataclass
class VerifyResult:
    ok: bool
    entries: int
    first_seq: int | None
    last_seq: int | None
    last_hash: str | None
    error: str | None = None
    failed_seq: int | None = None
    by_type: dict[str, int] | None = None


def verify_rows(rows: Iterable[tuple[int, str, str, str, str]], start_prev: str | None = None,
                start_seq: int | None = None) -> VerifyResult:
    """Verify (seq, entry_type, canonical, prev_hash, entry_hash) rows in seq order. Shared by the DB verifier and
    tests; scripts/verify_ledger.py re-implements the same rule with the standard library only."""
    expected_prev, expected_seq = start_prev, start_seq
    n = 0
    first = last = None
    last_hash = None
    by_type: dict[str, int] = {}
    for seq, etype, canonical, prev, eh in rows:
        if expected_seq is not None and seq != expected_seq:
            return VerifyResult(False, n, first, last, last_hash, f"seq gap: expected {expected_seq}, got {seq}", seq)
        # Entry 1 must be a genesis entry with a zero prev_hash, however verification was started (addendum 2, 5).
        if seq == 1 and (prev != ZERO_HASH or etype != "genesis"):
            return VerifyResult(False, n, first, last, last_hash, "entry 1 must be genesis with a zero prev_hash", seq)
        if expected_prev is not None and prev != expected_prev:
            return VerifyResult(False, n, first, last, last_hash, "prev_hash does not link to the previous entry", seq)
        if entry_hash(prev, canonical) != eh:
            return VerifyResult(False, n, first, last, last_hash, "entry_hash does not match the canonical text", seq)
        try:
            body = json.loads(canonical)
        except ValueError:
            return VerifyResult(False, n, first, last, last_hash, "canonical text is not JSON", seq)
        if body.get("seq") != seq or body.get("entry_type") != etype:
            return VerifyResult(False, n, first, last, last_hash, "seq/entry_type differ from the canonical text", seq)
        n += 1
        first = seq if first is None else first
        last, last_hash = seq, eh
        by_type[etype] = by_type.get(etype, 0) + 1
        expected_prev, expected_seq = eh, seq + 1
    return VerifyResult(True, n, first, last, last_hash, by_type=by_type)


def verify_db(conn: psycopg.Connection, from_seq: int = 1, batch: int = 5000) -> VerifyResult:
    start_prev = None
    if from_seq > 1:
        r = conn.execute("SELECT entry_hash FROM ledger_entries WHERE seq = %s", (from_seq - 1,)).fetchone()
        start_prev = r[0] if r else None

    def rows() -> Iterable[tuple[int, str, str, str, str]]:
        after = from_seq - 1
        while True:
            chunk = conn.execute(
                "SELECT seq, entry_type, canonical, prev_hash, entry_hash FROM ledger_entries WHERE seq > %s"
                " ORDER BY seq LIMIT %s", (after, batch)).fetchall()
            if not chunk:
                return
            yield from chunk
            after = chunk[-1][0]

    return verify_rows(rows(), start_prev=start_prev, start_seq=from_seq)
