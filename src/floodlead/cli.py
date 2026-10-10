"""`floodlead` command line: migrate, ingest (scheduler), run one job, backfills, api."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

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


def model_targets() -> tuple[str, ...]:
    from floodlead.model import TARGETS

    return TARGETS


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
    bw = bsub.add_parser("usgs-window", help="forced NWIS IV re-fetch of one site and window (with a 1-day margin)")
    bw.add_argument("--site", required=True)
    bw.add_argument("--start", required=True, help="ISO time (UTC)")
    bw.add_argument("--end", required=True, help="ISO time (UTC)")
    h = sub.add_parser("history", help="Stage 3 history: paced, resumable downloads into the raw archive")
    hsub = h.add_subparsers(dest="hcmd", required=True)
    hd = hsub.add_parser("download", help="download one or more sources, in order (skips finished tasks)")
    hd.add_argument("sources", nargs="+")
    hd.add_argument("--pace", type=float, default=None, help="seconds between requests (default per source)")
    hd.add_argument("--limit", type=int, default=None, help="stop after this many requests per source")
    hsub.add_parser("status", help="tasks done, empty and failed per source")
    hl = hsub.add_parser("load", help="parse archived downloads into the history tables")
    hl.add_argument("what", choices=["peaks", "daily", "nws", "rain"])
    hb = hsub.add_parser("build", help="build a derived product from the history tables")
    hb.add_argument("what", choices=["scorecard", "relay", "catalogue", "datasets", "trust"])
    hb.add_argument("--out", default="/srv/floodlead/datasets", help="output directory (datasets, json outputs)")
    hsub.add_parser("typical-peaks", help="compute the typical yearly peak per BC station (with datum checks)")
    fb = sub.add_parser("feedback", help="read the in-app feedback (decrypted only here, on the VM)")
    fbs = fb.add_subparsers(dest="fcmd", required=True)
    fbl = fbs.add_parser("list", help="print every feedback item, oldest first")
    fbl.add_argument("--since", default=None, help="ISO date/time (UTC), e.g. 2026-10-09T20:00")
    sc = sub.add_parser("score", help="score settled forecast horizons now and refresh the summary")
    sc.add_argument("--recompute-crps", action="store_true",
                    help="recompute crps (fair) and crps_qs for every stored score, then refresh the summary")
    iss = sub.add_parser("issue", help="run the hourly issuance now (live only; no backdating)")
    iss.add_argument("--dry-run", action="store_true", help="compute forecasts but write nothing")
    lg = sub.add_parser("ledger", help="ledger tools")
    lgs = lg.add_subparsers(dest="ledger_cmd", required=True)
    lgs.add_parser("anchor", help="publish the head and new entries to the `ledger` branch now")
    lv = lgs.add_parser("verify", help="verify the hash chain directly from the database")
    lv.add_argument("--from-seq", type=int, default=1)
    ex = sub.add_parser("export-demo", help="write the app's snapshot JSON (web/data/snapshot/) from the live DB")
    ex.add_argument("--out", default="web/data/snapshot")
    md = sub.add_parser("model", help="Stage 4 model (run only in a capped one-off container)")
    mds = md.add_subparsers(dest="model_cmd", required=True)
    mf = mds.add_parser("dev-fit", help="walk-forward fits on development years; saves validation predictions")
    mf.add_argument("--datasets", default="/datasets")
    mf.add_argument("--out", required=True)
    mf.add_argument("--candidate", action="append", required=True, help="family:group:sub|full, e.g. lgb:G+R:sub")
    mf.add_argument("--targets", default=",".join(model_targets()), help="comma-separated, e.g. d_6,d_12,d_24,m_24")
    mf.add_argument("--folds", default="", help="validation water years to run (default: all)")
    ms = mds.add_parser("dev-score", help="score saved walk-forward predictions into the development report")
    ms.add_argument("--datasets", default="/datasets")
    ms.add_argument("--preds", action="append", required=True, help="a directory of preds-*.npz (repeatable)")
    ms.add_argument("--inputs", default="docs/data/stage4-inputs-v1.json")
    ms.add_argument("--catalogue", default="docs/data/catalogue-v1.json")
    ms.add_argument("--relay", default="docs/data/relay-v1.json")
    ms.add_argument("--chosen", default=None)
    ms.add_argument("--out", required=True)
    mg = mds.add_parser("merge-preds", help="merge one candidate's prediction files (same rows) into one")
    mg.add_argument("--out", required=True)
    mg.add_argument("paths", nargs="+")
    ft = mds.add_parser("final-train", help="train the A2 final models (final_training_rows) into a new run dir")
    ft.add_argument("--datasets", default="/datasets")
    ft.add_argument("--out", required=True)
    ft.add_argument("--family", required=True, choices=["lgb", "linear"])
    ft.add_argument("--subsample", action="store_true")
    ft.add_argument("--only", default="", help="comma-separated artifact names (default: the whole plan)")
    mm = mds.add_parser("manifest", help="write the final manifest from the run dir and the development report")
    mm.add_argument("--datasets", default="/datasets")
    mm.add_argument("--run-dir", required=True)
    mm.add_argument("--dev-report", required=True)
    mm.add_argument("--chosen", required=True)
    mm.add_argument("--chosen-preds", required=True)
    mm.add_argument("--inputs", default="docs/data/stage4-inputs-v1.json")
    mm.add_argument("--protocol", default="docs/evaluation-protocol.md")
    mm.add_argument("--out", required=True)
    fr = mds.add_parser("final-run", help="THE single final run on held-out rows: only after the supervisor's go")
    fr.add_argument("--supervisor-go", required=True, help="who gave the go and when (recorded in the results)")
    fr.add_argument("--datasets", default="/datasets")
    fr.add_argument("--manifest", default="docs/data/stage4-final-manifest-v1.json")
    fr.add_argument("--run-dir", required=True)
    fr.add_argument("--inputs", default="docs/data/stage4-inputs-v1.json")
    fr.add_argument("--catalogue", default="docs/data/catalogue-v1.json")
    fr.add_argument("--relay", default="docs/data/relay-v1.json")
    fr.add_argument("--trust", default="docs/data/trust-v2.json")
    fr.add_argument("--out", required=True)
    mc = mds.add_parser("ledger-card", help="append the manifest's model_card to the ledger (once)")
    mc.add_argument("--manifest", required=True)
    a = sub.add_parser("api", help="serve the read-only API")
    a.add_argument("--host", default="0.0.0.0")
    a.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)

    if args.cmd == "model" and args.model_cmd == "dev-fit":
        from floodlead import model_dev

        folds = [int(x) for x in args.folds.split(",") if x]
        model_dev.fit_candidates(Path(args.datasets), Path(args.out), args.candidate, tuple(args.targets.split(",")),
                                 folds or None)
        return 0
    if args.cmd == "model" and args.model_cmd == "dev-score":
        import json

        from floodlead import model_report

        rep = model_report.development_report(Path(args.datasets), [Path(p) for p in args.preds], Path(args.inputs),
                                              Path(args.catalogue), Path(args.relay), args.chosen)
        Path(args.out).write_text(json.dumps(rep, indent=1, default=float))
        for r in rep["ranking_G+R"]:
            print(json.dumps(r))
        return 0
    if args.cmd == "model" and args.model_cmd == "merge-preds":
        from floodlead import model_dev

        print(model_dev.merge_preds([Path(p) for p in args.paths], Path(args.out)))
        return 0
    if args.cmd == "model" and args.model_cmd == "final-train":
        from floodlead import model_final

        model_final.train(Path(args.datasets), Path(args.out), args.family, args.subsample,
                          [x for x in args.only.split(",") if x] or None)
        return 0
    if args.cmd == "model" and args.model_cmd == "final-run":
        import json

        from floodlead import model_final

        out = Path(args.out)
        if out.exists():
            raise SystemExit(f"{out} exists: the final run happens once (amendment 4, item 9)")
        res = model_final.final_run(Path(args.datasets), Path(args.manifest), Path(args.run_dir), Path(args.inputs),
                                    Path(args.catalogue), Path(args.relay), Path(args.trust))
        res["supervisor_go"] = args.supervisor_go
        out.write_text(json.dumps(res, indent=1, default=float) + "\n")
        print(json.dumps({"run_id": res["run_id"], "kill_criteria": res["kill_criteria"]}))
        return 0
    if args.cmd == "model" and args.model_cmd == "manifest":
        import json

        from floodlead import model_final

        dev = json.loads(Path(args.dev_report).read_text())
        m = model_final.manifest(Path(args.run_dir), Path(args.datasets), dev, args.chosen,
                                 model_final.freeze_from_dev(dev, args.chosen),
                                 model_final.calibration_maps(Path(args.datasets), Path(args.chosen_preds), dev,
                                                              args.chosen),
                                 Path(args.inputs), Path(args.protocol))
        Path(args.out).write_text(json.dumps(m, indent=1) + "\n")
        print(model_final.sha256_file(Path(args.out)))
        return 0
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

        if args.recompute_crps:
            print(json.dumps(scorer.recompute_crps(pool), indent=1, default=str))
            return 0
        print(json.dumps(scorer.run(pool), indent=1, default=str))
        return 0
    if args.cmd == "issue":
        import json

        from floodlead import issuer

        print(json.dumps(issuer.run(pool, dry_run=args.dry_run), indent=1, default=str))
        return 0
    if args.cmd == "model" and args.model_cmd == "ledger-card":
        import json

        from floodlead import model_final

        with pool.connection() as conn:
            print(json.dumps(model_final.append_card(conn, Path(args.manifest))))
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
    if args.cmd == "feedback":
        from floodlead import feedback

        since = datetime.fromisoformat(args.since).replace(tzinfo=UTC) if args.since else None
        with pool.connection() as conn:
            items = feedback.read_all(conn, get_settings().feedback_key, since)
        for it in items:
            useful = {True: "yes", False: "no", None: "-"}[it["useful"]]
            text = it["text"].encode("unicode_escape").decode("ascii")  # no terminal control sequences
            print(f"#{it['id']} {it['received_at']:%Y-%m-%d %H:%MZ} useful={useful} route={it['route']}"
                  f" station={it['station_id'] or '-'} v={it['app_version'] or '-'}\n    {text}")
        print(f"{len(items)} item(s)")
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
        elif args.what == "usgs-window":
            a = datetime.fromisoformat(args.start).replace(tzinfo=UTC)
            b = datetime.fromisoformat(args.end).replace(tzinfo=UTC)
            print(usgs.refetch_window(pool, args.site, a, b))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
