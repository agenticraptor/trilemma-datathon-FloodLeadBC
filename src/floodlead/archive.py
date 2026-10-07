"""Immutable raw archive on local disk, indexed in `raw_objects`.

Layout: $ARCHIVE_DIR/raw/<source>/YYYY/MM/DD/HH/<name>.<sha8>.gz (UTC fetch time).
Files are gzipped (mtime 0, so the bytes depend only on the payload), written to a temp file
and renamed into place, then made read-only (0444). Nothing is ever overwritten or deleted.
Identical payloads (same sha256 of the uncompressed bytes) are archived and recorded once.
"""

from __future__ import annotations

import gzip
import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import psycopg

from floodlead import log
from floodlead.http import Fetched

L = log.get(__name__)

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class RawRef:
    raw_object_id: int
    sha256: str
    is_new: bool
    archive_path: str | None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(name: str) -> str:
    return _SAFE.sub("_", name).strip("_")[:120] or "payload"


def relative_path(source: str, name: str, sha: str, fetched_at: datetime) -> str:
    t = fetched_at
    return f"raw/{source}/{t:%Y/%m/%d/%H}/{safe_name(name)}.{sha[:8]}.gz"


def write_file(archive_dir: Path, rel: str, data: bytes) -> int:
    """Atomically write gzipped `data` to archive_dir/rel; never overwrite. Returns bytes on disk."""
    dest = archive_dir / rel
    if dest.exists():
        return dest.stat().st_size  # same name implies same sha prefix; keep the existing file
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=dest.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            with gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0) as gz:
                gz.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o444)
        os.link(tmp, dest)  # fails if dest appeared meanwhile: never overwrite
    except FileExistsError:
        pass
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return dest.stat().st_size


def store(
    conn: psycopg.Connection,
    archive_dir: Path,
    source: str,
    name: str,
    fetched: Fetched,
) -> RawRef:
    """Archive the payload (if new) and record it in raw_objects. Archive failures are logged
    loudly and recorded, but never stop ingestion."""
    data = fetched.content
    sha = sha256_hex(data)
    row = conn.execute(
        "SELECT raw_object_id, archive_path FROM raw_objects WHERE sha256 = %s", (sha,)
    ).fetchone()
    if row:
        return RawRef(row[0], sha, False, row[1])

    rel: str | None = relative_path(source, name, sha, fetched.fetched_at)
    err: str | None = None
    disk_bytes: int | None = None
    try:
        disk_bytes = write_file(archive_dir, rel, data)
    except OSError as e:
        err = repr(e)
        L.error("ARCHIVE WRITE FAILED", **log.kv(source=source, url=fetched.url, path=rel, error=err))
        rel = None
    row = conn.execute(
        """
        INSERT INTO raw_objects (source, url, archive_path, archive_error, sha256, bytes, archive_bytes,
                                 http_status, last_modified, fetched_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (sha256) DO NOTHING
        RETURNING raw_object_id
        """,
        (source, fetched.url, rel, err, sha, len(data), disk_bytes, fetched.status,
         fetched.last_modified, fetched.fetched_at),
    ).fetchone()
    if row is None:  # a concurrent writer recorded the same payload first
        row = conn.execute("SELECT raw_object_id FROM raw_objects WHERE sha256 = %s", (sha,)).fetchone()
        assert row is not None
        return RawRef(row[0], sha, False, rel)
    return RawRef(row[0], sha, True, rel)
