"""`floodlead history ...`: which task list, pace and paging each source uses."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from psycopg_pool import ConnectionPool

from floodlead.history import download, tasks

# source -> (task list, default pace in seconds, empty test, paging)
SOURCES: dict[str, tuple[Callable[[ConnectionPool], list[download.Task]], float, Any, Any]] = {
    "eccc-peaks": (lambda p: tasks.eccc_peaks(), 1.0, tasks.ogc_empty, tasks.ogc_next_page),
    "eccc-daily": (tasks.eccc_daily, 1.0, tasks.ogc_empty, tasks.ogc_next_page),
    "eccc-climate": (lambda p: tasks.eccc_climate(), 1.0, tasks.ogc_empty, tasks.ogc_next_page),
    "iem-nws": (lambda p: tasks.iem_nws(), 2.0, lambda b: not b.strip(), None),
    "ncei": (lambda p: tasks.ncei(), 3.0, lambda b: b.count(b"\n") <= 1, None),
    "snotel": (lambda p: tasks.snotel(), 2.0, lambda b: b.strip() in (b"", b"[]"), None),
    # Open-Meteo free tier: < 600 calls/min, 5,000/h, 10,000/day; one point-year counts as ~26 calls.
    "openmeteo-archive": (lambda p: tasks.openmeteo_archive(), 30.0, None, None),
    "openmeteo-histfc": (lambda p: tasks.openmeteo_histfc(), 30.0, None, None),
    "openmeteo-prevruns": (lambda p: tasks.openmeteo_prevruns(), 30.0, None, None),
}


def main(pool: ConnectionPool, args: argparse.Namespace) -> int:
    if args.hcmd == "load":
        from floodlead.history import parse

        fn = {"peaks": parse.load_peaks, "daily": parse.load_daily}[args.what]
        print(fn(pool))
        return 0
    if args.hcmd == "typical-peaks":
        from floodlead import typical_peaks

        with pool.connection() as conn:
            print(typical_peaks.compute(conn))
        return 0
    if args.hcmd == "status":
        with pool.connection() as conn:
            rows = conn.execute(
                "SELECT source, count(*) FILTER (WHERE status = 'ok'), count(*) FILTER (WHERE status = 'empty'),"
                " count(*) FILTER (WHERE status = 'error'), coalesce(sum(bytes), 0), min(fetched_at), max(fetched_at)"
                " FROM history_downloads GROUP BY source ORDER BY source").fetchall()
        for r in rows:
            print(" | ".join("" if v is None else str(v) for v in r))
        return 0
    unknown = [s for s in args.sources if s not in SOURCES]
    if unknown:
        print(f"unknown sources: {unknown}; known: {sorted(SOURCES)}")
        return 2
    ok = True
    for src in args.sources:
        make, pace, empty, expand = SOURCES[src]
        kw: dict[str, Any] = {"pace_s": args.pace if args.pace is not None else pace, "limit": args.limit}
        if empty is not None:
            kw["is_empty"] = empty
        if expand is not None:
            kw["expand"] = expand
        rep = download.run(pool, src, make(pool), **kw)
        print({k: (str(v) if v is not None and not isinstance(v, int | str) else v) for k, v in asdict(rep).items()})
        ok = ok and rep.errors == 0
    return 0 if ok else 1
