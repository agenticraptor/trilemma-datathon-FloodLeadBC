"""Shared ingestion plumbing: conditional-GET state, fetch → archive → parse → upsert."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime

import httpx
import psycopg

from floodlead import archive, http, log, store
from floodlead.config import get_settings

L = log.get(__name__)


def get_last_modified(conn: psycopg.Connection, url: str) -> datetime | None:
    row = conn.execute("SELECT last_modified FROM fetch_state WHERE url = %s", (url,)).fetchone()
    return row[0] if row else None


def load_fetch_state(conn: psycopg.Connection, url_prefix: str) -> dict[str, datetime | None]:
    rows = conn.execute(
        "SELECT url, last_modified FROM fetch_state WHERE url LIKE %s", (url_prefix + "%",)
    ).fetchall()
    return {u: lm for u, lm in rows}


def set_fetch_state(conn: psycopg.Connection, url: str, f: http.Fetched) -> None:
    conn.execute(
        """
        INSERT INTO fetch_state (url, last_modified, last_status, checked_at) VALUES (%s, %s, %s, now())
        ON CONFLICT (url) DO UPDATE SET
            last_modified = COALESCE(EXCLUDED.last_modified, fetch_state.last_modified),
            last_status = EXCLUDED.last_status, checked_at = now()
        """,
        (url, f.last_modified, f.status),
    )


def payload_kind(source: str, url: str) -> str:
    if source == "eccc":
        return "eccc:daily" if "/daily/" in url else "eccc:hourly"
    if source == "usgs":
        return "usgs:nwis" if "nwis" in url else "usgs:ogc"
    return source


def process_payload(
    conn: psycopg.Connection,
    run: store.Run,
    source: str,
    name: str,
    fetched: http.Fetched,
    parse: Callable[[http.Fetched], list[store.Obs]],
    on_parsed: Callable[[psycopg.Connection, list[store.Obs], int], None] | None = None,
) -> archive.RawRef:
    """Archive the payload (own transaction, so the archive index never depends on parsing),
    then parse and upsert in a second transaction."""
    with conn.transaction():
        ref = archive.store(conn, get_settings().archive_dir, source, name, fetched)
    rows = parse(fetched)
    if rows:
        # Own short transaction: the stations row lock must not be held for the whole upsert.
        with conn.transaction():
            store.ensure_stations(
                conn,
                [
                    {"station_id": sid, "source": source, "native_id": sid.split(":", 1)[1],
                     "params": sorted({r.param for r in rows if r.station_id == sid})}
                    for sid in sorted({r.station_id for r in rows})
                ],
            )
    with conn.transaction():
        res = store.upsert_observations(conn, rows, ref.raw_object_id, kind=payload_kind(source, fetched.url))
        if on_parsed is not None:
            on_parsed(conn, rows, ref.raw_object_id)
    run.rows.add(res)
    return ref


def fetch_and_process(
    c: httpx.Client,
    conn: psycopg.Connection,
    run: store.Run,
    source: str,
    url: str,
    name: str,
    parse: Callable[[http.Fetched], list[store.Obs]],
    known_lm: datetime | None = None,
) -> http.Fetched:
    """Conditional GET; on 200 archive + upsert. fetch_state is only advanced after the payload
    has been processed, so a failed parse is retried on the next run instead of being skipped."""
    t0 = time.monotonic()
    f = http.fetch(c, url, if_modified_since=known_lm)
    t1 = time.monotonic()
    if f.not_modified:
        run.items_unchanged += 1
    else:
        run.items_fetched += 1
        process_payload(conn, run, source, name, f, parse)
    timing = run.details.setdefault("timing_s", {"fetch": 0.0, "process": 0.0})
    timing["fetch"] += t1 - t0
    timing["process"] += time.monotonic() - t1
    with conn.transaction():
        set_fetch_state(conn, url, f)
    return f
