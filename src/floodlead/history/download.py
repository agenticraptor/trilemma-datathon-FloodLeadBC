"""Paced, resumable download of history payloads.

Every response is archived unchanged (gzip, sha256) through `archive.store` and recorded in `history_downloads`
under (source, key). A task whose key is already `ok` or `empty` is skipped, so a run can be stopped and restarted
at any time. Parsing happens later, from the archive, never during the download.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from psycopg_pool import ConnectionPool

from floodlead import archive, http, log
from floodlead.config import get_settings

L = log.get(__name__)


@dataclass(frozen=True)
class Task:
    key: str
    url: str
    params: dict[str, str] = field(default_factory=dict)
    name: str = ""  # archive file name stem


@dataclass
class Report:
    source: str
    done: int = 0
    skipped: int = 0
    errors: int = 0
    bytes: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None


def done_keys(pool: ConnectionPool, source: str) -> set[str]:
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT key FROM history_downloads WHERE source = %s AND status IN ('ok', 'empty')", (source,)
        ).fetchall()
    return {r[0] for r in rows}


def record(conn: Any, source: str, t: Task, url: str, status: str, http_status: int | None, nbytes: int | None,
           raw_id: int | None, fetched_at: datetime, elapsed: float | None, error: str | None) -> None:
    conn.execute(
        """
        INSERT INTO history_downloads (source, key, url, status, http_status, bytes, raw_object_id, fetched_at,
                                       elapsed_s, error)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (source, key) DO UPDATE SET url = EXCLUDED.url, status = EXCLUDED.status,
            http_status = EXCLUDED.http_status, bytes = EXCLUDED.bytes, raw_object_id = EXCLUDED.raw_object_id,
            fetched_at = EXCLUDED.fetched_at, elapsed_s = EXCLUDED.elapsed_s, error = EXCLUDED.error
        """,
        (source, t.key, url, status, http_status, nbytes, raw_id, fetched_at, elapsed, error),
    )


def run(
    pool: ConnectionPool,
    source: str,
    tasks: Iterable[Task],
    *,
    pace_s: float,
    is_empty: Callable[[bytes], bool] = lambda b: len(b) == 0,
    expand: Callable[[Task, bytes], Iterator[Task]] | None = None,
    limit: int | None = None,
) -> Report:
    """Fetch every task not yet done, at most one request per `pace_s` seconds.

    `expand(task, content)` may yield follow-up tasks (for example the next page), which run before the next task."""
    s = get_settings()
    rep = Report(source)
    done = done_keys(pool, source)
    queue: list[Task] = list(tasks)
    queue.reverse()
    last = 0.0
    with http.client() as c:
        while queue:
            t = queue.pop()
            if t.key in done:
                rep.skipped += 1
                if expand is not None:  # follow-ups of a finished page may still be missing
                    with pool.connection() as conn:
                        row = conn.execute(
                            "SELECT r.archive_path FROM history_downloads h JOIN raw_objects r USING (raw_object_id)"
                            " WHERE h.source = %s AND h.key = %s", (source, t.key)).fetchone()
                    if row and row[0]:
                        content = archive.read(s.archive_dir, row[0])
                        queue.extend(reversed(list(expand(t, content))))
                continue
            if limit is not None and rep.done + rep.errors >= limit:
                break
            wait = pace_s - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
            last = time.monotonic()
            now = datetime.now(UTC)
            try:
                f = http.fetch(c, t.url, params=t.params or None)
            except (httpx.HTTPError, http.RateLimited) as e:
                status = getattr(getattr(e, "response", None), "status_code", None)
                L.warning("history fetch failed", **log.kv(source=source, key=t.key, error=repr(e)[:300]))
                with pool.connection() as conn:
                    record(conn, source, t, t.url, "error", status, None, None, now, None, repr(e)[:1000])
                rep.errors += 1
                if isinstance(e, http.RateLimited):
                    L.error("rate limited: stopping this source",
                            **log.kv(source=source, retry_after_s=e.retry_after_s))
                    break
                continue
            empty = is_empty(f.content)
            with pool.connection() as conn, conn.transaction():
                ref = archive.store(conn, s.archive_dir, source, t.name or t.key, f)
                record(conn, source, t, f.url, "empty" if empty else "ok", f.status, len(f.content),
                       ref.raw_object_id, f.fetched_at, round(f.elapsed_s, 3), None)
            rep.done += 1
            rep.bytes += len(f.content)
            if rep.done % 25 == 0:
                L.info("history progress", **log.kv(source=source, done=rep.done, skipped=rep.skipped,
                                                    errors=rep.errors, bytes=rep.bytes, queued=len(queue)))
            if expand is not None and not empty:
                queue.extend(reversed(list(expand(t, f.content))))
    rep.finished_at = datetime.now(UTC)
    L.info("history done", **log.kv(source=source, done=rep.done, skipped=rep.skipped, errors=rep.errors,
                                    bytes=rep.bytes))
    return rep
