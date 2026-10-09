"""`floodlead` command line: migrate, ingest (scheduler), run one job, backfills, api."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

from floodlead import db, log
from floodlead.config import get_settings


def _pool(max_size: int = 6):  # type: ignore[no-untyped-def]
    return db.pool(max_size=max_size)


def _jobs(pool):  # type: ignore[no-untyped-def]
    from floodlead import anchor, issuer, scorer
    from floodlead.scheduler import Job
    from floodlead.sources import eccc, nwps, usgs

    return [
        # ECCC rewrites the BC hourly files every 30 min (Last-Modified ~:01:28 and ~:31:18), but they appear
        # on dd.weather.gc.ca 2-6 min later. Polling every 5 min (:02, :07, ...) catches each refresh within
        # ~5 min of it becoming visible; an unchanged poll costs one listing + one conditional GET.
        Job("eccc-hourly", 300, 120, lambda: eccc.ingest_files(pool, "hourly", "live")),
        Job("usgs-live", 900, 120, lambda: usgs.ingest_live(pool)),
        Job("nwps-live", 1800, 300, lambda: nwps.ingest_live(pool)),
        # Station metadata daily (and at start).
        # Hourly forecast issuance into the ledger at HH:15 (after the HH:01 Datamart rewrite has landed).
        Job("ledger-issue", 3600, 900, lambda: issuer.run(pool)),
        # Hourly anchor at HH:30 (after the HH:15 issuance has been written): head + new entries to the `ledger` branch.
        Job("ledger-anchor", 3600, 1800, lambda: anchor.run(pool)),
        # Hourly scoring at HH:40: settled horizons (valid_at >= 3 h old) and rescoring after truth revisions.
        Job("scorer", 3600, 2400, lambda: scorer.run(pool)),
        Job("eccc-stations", 86400, 9 * 3600 + 600, lambda: eccc.refresh_stations(pool)),
        Job("usgs-stations", 86400, 9 * 3600 + 900, lambda: usgs.refresh_stations(pool)),
    ]


def main(argv: list[str] | None = None) -> int:
    log.setup()
    ap = argparse.ArgumentParser(prog="floodlead")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="apply pending SQL migrations")
    sub.add_parser("ingest", help="run the live ingestion scheduler (foreground)")
    r = sub.add_parser("run", help="run one live job once")
    r.add_argument("job", choices=["eccc-hourly", "usgs-live", "nwps-live", "eccc-stations", "usgs-stations"])
    r.add_argument("--force", action="store_true", help="eccc-hourly: re-download every file (ignore Last-Modified)")
    b = sub.add_parser("backfill", help="idempotent, resumable backfills")
    bsub = b.add_subparsers(dest="what", required=True)
    bsub.add_parser("eccc-30d", help="all BC 30-day (Datamart 'daily') files")
    bu = bsub.add_parser("usgs", help="USGS continuous (15-min) history, chunked by month")
    bu.add_argument("--sites", default="all", help="comma-separated USGS site numbers, or 'all'")
    bu.add_argument("--since", default="2004-10-01", help="ISO date (UTC)")
    bu.add_argument("--until", default=None, help="ISO date (UTC); default now")
    bu.add_argument("--chunk-months", type=int, default=6, help="months per request window (default 6)")
    bu.add_argument("--api", choices=["auto", "ogc", "nwis"], default="auto",
                    help="auto: OGC API v1 when USGS_API_KEY is set, else legacy NWIS IV (no key needed)")
    bsub.add_parser("nwps", help="NWPS gauge metadata, flood categories and current forecasts")
    h = sub.add_parser("history", help="Stage 3 history: paced, resumable downloads into the raw archive")
    hsub = h.add_subparsers(dest="hcmd", required=True)
    hd = hsub.add_parser("download", help="download one or more sources, in order (skips finished tasks)")
    hd.add_argument("sources", nargs="+")
    hd.add_argument("--pace", type=float, default=None, help="seconds between requests (default per source)")
    hd.add_argument("--limit", type=int, default=None, help="stop after this many requests per source")
    hsub.add_parser("status", help="tasks done, empty and failed per source")
    sub.add_parser("score", help="score settled forecast horizons now and refresh the summary")
    iss = sub.add_parser("issue", help="run the hourly issuance now (live only; no backdating)")
    iss.add_argument("--dry-run", action="store_true", help="compute forecasts but write nothing")
    lg = sub.add_parser("ledger", help="ledger tools")
    lgs = lg.add_subparsers(dest="ledger_cmd", required=True)
    lgs.add_parser("anchor", help="publish the head and new entries to the `ledger` branch now")
    lv = lgs.add_parser("verify", help="verify the hash chain directly from the database")
    lv.add_argument("--from-seq", type=int, default=1)
    ex = sub.add_parser("export-demo", help="write the app's snapshot JSON (web/data/snapshot/) from the live DB")
    ex.add_argument("--out", default="web/data/snapshot")
    a = sub.add_parser("api", help="serve the read-only API")
    a.add_argument("--host", default="0.0.0.0")
    a.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)

    if args.cmd == "migrate":
        print(db.migrate())
        return 0
    if args.cmd == "api":
        import uvicorn

        db.migrate()
        uvicorn.run("floodlead.api:app", host=args.host, port=args.port, proxy_headers=True,
                    forwarded_allow_ips="*", access_log=False, log_config=None)
        return 0

    if args.cmd == "export-demo":
        from floodlead.snapshot import export

        export(args.out)
        return 0

    db.migrate()
    pool = _pool()
    if args.cmd == "ingest":
        from floodlead.scheduler import run_forever

        get_settings().archive_dir.mkdir(parents=True, exist_ok=True)
        # Live jobs only run inside this scheduler, so any live run still marked 'running' was
        # interrupted by a restart. Backfills (other containers) are left alone.
        with pool.connection() as conn:
            n = conn.execute(
                "UPDATE ingest_runs SET status = 'error', finished_at = now(),"
                " error_text = 'abandoned: process stopped before the run finished'"
                " WHERE status = 'running' AND job IN ('live', 'stations')"
            ).rowcount
            conn.commit()
        log.get(__name__).info("marked abandoned runs", **log.kv(count=n))
        run_forever(_jobs(pool))
        return 0
    if args.cmd == "score":
        import json

        from floodlead import scorer

        print(json.dumps(scorer.run(pool), indent=1, default=str))
        return 0
    if args.cmd == "issue":
        import json

        from floodlead import issuer

        print(json.dumps(issuer.run(pool, dry_run=args.dry_run), indent=1, default=str))
        return 0
    if args.cmd == "ledger" and args.ledger_cmd == "anchor":
        import json

        from floodlead import anchor

        res = anchor.run(pool)
        print(json.dumps(res, indent=1, default=str))
        return 0 if res.get("status") in ("ok", "up-to-date") else 1
    if args.cmd == "ledger" and args.ledger_cmd == "verify":
        from dataclasses import asdict

        from floodlead import ledger

        with pool.connection() as conn:
            res = ledger.verify_db(conn, from_seq=args.from_seq)
        print(asdict(res))
        return 0 if res.ok else 1
    if args.cmd == "run":
        if args.job == "eccc-hourly" and args.force:
            from floodlead.sources import eccc

            eccc.ingest_files(pool, "hourly", "live", force=True)
            return 0
        jobs = {j.name: j for j in _jobs(pool)}
        jobs[args.job].fn()
        return 0
    if args.cmd == "history":
        from floodlead.history import cli as hcli

        return hcli.main(pool, args)
    if args.cmd == "backfill":
        from floodlead.sources import eccc, nwps, usgs

        if args.what == "eccc-30d":
            eccc.ingest_files(pool, "daily", "backfill-eccc-30d")
        elif args.what == "usgs":
            sites = None if args.sites == "all" else [s.strip() for s in args.sites.split(",") if s.strip()]
            since = datetime.fromisoformat(args.since).replace(tzinfo=UTC)
            until = datetime.fromisoformat(args.until).replace(tzinfo=UTC) if args.until else datetime.now(UTC)
            usgs.backfill(pool, sites, since, until, chunk_months=args.chunk_months, api=args.api)
        elif args.what == "nwps":
            nwps.ingest_live(pool, job="backfill-nwps")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
