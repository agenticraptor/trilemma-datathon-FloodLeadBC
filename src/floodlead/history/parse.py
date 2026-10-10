"""Parse archived history payloads (history_downloads -> raw_objects -> archive) into the new history tables."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg_pool import ConnectionPool

from floodlead import archive, log
from floodlead.config import get_settings

L = log.get(__name__)

_DTYPE = {"Water Level": "level", "Discharge": "discharge"}
_CODE = {"Maximum": "max", "Minimum": "min"}


def _pages(conn: Any, source: str, prefix: str | None = None) -> list[tuple[str, int, str]]:
    return conn.execute(
        "SELECT h.key, r.raw_object_id, r.archive_path FROM history_downloads h JOIN raw_objects r USING"
        " (raw_object_id) WHERE h.source = %s AND h.status = 'ok' AND (%s::text IS NULL OR h.key LIKE %s)"
        " ORDER BY h.key", (source, prefix, f"{prefix}/%" if prefix else None)).fetchall()


def peak_rows(doc: dict[str, Any], raw_id: int) -> list[tuple]:
    out = []
    for f in doc.get("features", []):
        p = f["properties"]
        dt, code = _DTYPE.get(p.get("DATA_TYPE_EN")), _CODE.get(p.get("PEAK_CODE_EN"))
        if dt is None or code is None or p.get("PEAK") is None or not p.get("DATE"):
            continue
        tz = timezone(timedelta(hours=int(p.get("TIMEZONE_OFFSET") or 0)))
        at = datetime.fromisoformat(p["DATE"]).replace(tzinfo=tz)
        out.append((p["STATION_NUMBER"], at.year, dt, code, at, float(p["PEAK"]), p.get("SYMBOL_EN"), raw_id))
    return out


def load_peaks(pool: ConnectionPool) -> dict[str, int]:
    s = get_settings()
    n = 0
    with pool.connection() as conn, conn.transaction():
        for _, rid, path in _pages(conn, "eccc-peaks"):
            rows = peak_rows(json.loads(archive.read(s.archive_dir, path)), rid)
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO eccc_annual_peaks (station_number, year, data_type, peak_code, peak_at, value,"
                    " symbol, raw_object_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                    " ON CONFLICT (station_number, data_type, peak_code, year) DO UPDATE SET"
                    " peak_at = EXCLUDED.peak_at, value = EXCLUDED.value, symbol = EXCLUDED.symbol,"
                    " raw_object_id = EXCLUDED.raw_object_id",
                    rows)
            n += len(rows)
    L.info("peaks loaded", **log.kv(rows=n))
    return {"rows": n}


def daily_rows(doc: dict[str, Any], raw_id: int) -> list[tuple]:
    out = []
    for f in doc.get("features", []):
        p = f["properties"]
        if p.get("LEVEL") is None and p.get("DISCHARGE") is None:
            continue
        out.append((p["STATION_NUMBER"], p["DATE"], p.get("LEVEL"), p.get("DISCHARGE"), p.get("LEVEL_SYMBOL_EN"),
                    p.get("DISCHARGE_SYMBOL_EN"), raw_id))
    return out


def load_daily(pool: ConnectionPool) -> dict[str, Any]:
    """(Re)load every downloaded station: delete its rows, then COPY the parsed pages (derived data)."""
    s = get_settings()
    t0 = time.monotonic()
    with pool.connection() as conn:
        pages = _pages(conn, "eccc-daily")
    by_station: dict[str, list[tuple[int, str]]] = {}
    for key, rid, path in pages:
        by_station.setdefault(key.split("/", 1)[0], []).append((rid, path))
    total = 0
    for stn, plist in sorted(by_station.items()):
        rows: list[tuple] = []
        for rid, path in plist:
            rows += daily_rows(json.loads(archive.read(s.archive_dir, path)), rid)
        with pool.connection() as conn, conn.transaction():
            conn.execute("DELETE FROM eccc_daily WHERE station_number = %s", (stn,))
            with conn.cursor().copy(
                    "COPY eccc_daily (station_number, date, level, discharge, level_symbol, discharge_symbol,"
                    " raw_object_id) FROM STDIN") as cp:
                seen = set()
                for r in rows:
                    if r[1] in seen:  # a page boundary can repeat a day if the listing shifted; keep the first
                        continue
                    seen.add(r[1])
                    cp.write_row(r)
        total += len(seen)
    out = {"stations": len(by_station), "rows": total, "runtime_s": round(time.monotonic() - t0, 1)}
    L.info("daily loaded", **log.kv(**out))
    return out
