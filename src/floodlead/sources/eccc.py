"""ECCC Datamart hydrometric CSVs (BC) and station metadata from the ECCC OGC API.

CSV columns: ID, Date, Water Level / Niveau d'eau (m), Grade, Symbol / Symbole, QA/QC,
Discharge / Débit (cms), Grade, Symbol / Symbole, QA/QC. `Date` is ISO 8601 with a fixed
-08:00 offset (standard time, all year); we parse the offset and store UTC.
"""

from __future__ import annotations

import csv
import io
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
from psycopg_pool import ConnectionPool

from floodlead import archive, http, ingest, log, store, units
from floodlead.config import get_settings

L = log.get(__name__)

SOURCE = "eccc"
PROBE_FILE = "BC_08MH001_hourly_hydrometric.csv"  # Chilliwack R. at Vedder Crossing, reports year-round
_LISTING_RE = re.compile(
    r'href="(BC_(?P<station>[0-9A-Z]+)_(?P<kind>hourly|daily)_hydrometric\.csv)">[^<]*</a>\s+'
    r"(?P<date>\d{4}-\d{2}-\d{2} \d{2}:\d{2})"
)


def listing_url(kind: str) -> str:
    return f"{get_settings().eccc_base}/{kind}/"


def dated_base(kind: str, day: date) -> str:
    return f"{get_settings().eccc_root}/{day:%Y%m%d}/WXO-DD/hydrometric/csv/BC/{kind}/"


def candidate_bases(kind: str, now: datetime) -> list[str]:
    """F1: dated directory for the current UTC date first, then the previous date, then the `today/` alias.

    `today/` returned 404 for a few minutes after 00:00 UTC on Oct 8; the dated directories are the stable
    location. The 30-day `daily/` files are written once a day (~08:20Z), so for ~8 h after midnight only the
    previous date's `daily/` exists."""
    d = now.astimezone(UTC).date()
    return [dated_base(kind, d), dated_base(kind, d - timedelta(days=1)), listing_url(kind)]


def fetch_listing(
    c: httpx.Client, kind: str, now: datetime | None = None
) -> tuple[str, dict[str, datetime], list[dict[str, Any]]]:
    """Return (base URL that served the listing, files, fallbacks tried). A 404 or an empty listing moves on to
    the next candidate; inside the rollover window that is expected, not an error."""
    tried: list[dict[str, Any]] = []
    for base in candidate_bases(kind, now or datetime.now(UTC)):
        try:
            f = http.fetch(c, base, attempts=2)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                tried.append({"url": base, "status": 404})
                continue
            raise
        files = parse_listing(f.content.decode("utf-8", "replace"))
        if not files:
            tried.append({"url": base, "status": f.status, "files": 0})
            continue
        return base, files, tried
    raise RuntimeError(f"no ECCC {kind} listing available; tried {tried}")


def parse_listing(html: str) -> dict[str, datetime]:
    """Return {file name: listing modification time (UTC, minute precision)}."""
    out: dict[str, datetime] = {}
    for m in _LISTING_RE.finditer(html):
        out[m.group(1)] = datetime.strptime(m.group("date"), "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
    return out


def _num(s: str) -> float | None:
    s = s.strip()
    if not s:
        return None
    return float(s)


def _q(grade: str, symbol: str, qaqc: str) -> dict[str, Any]:
    return {"grade": grade.strip() or None, "symbol": symbol.strip() or None, "qaqc": qaqc.strip() or None}


def parse_csv(content: bytes, published_at: datetime | None) -> list[store.Obs]:
    text = content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if header is None:
        return []
    if len(header) < 10 or header[0].strip() != "ID" or not header[1].strip().startswith("Date"):
        raise ValueError(f"unexpected ECCC CSV header: {header!r}")
    out: list[store.Obs] = []
    for rec in reader:
        if not rec or not rec[0].strip():
            continue
        sid = "eccc:" + rec[0].strip()
        ts = datetime.fromisoformat(rec[1].strip())
        if ts.tzinfo is None:
            raise ValueError(f"timestamp without offset: {rec[1]!r}")
        ts = ts.astimezone(UTC)
        for param, idx, unit in (("level", 2, "m"), ("flow", 6, "m3/s")):
            raw = _num(rec[idx]) if len(rec) > idx else None
            if raw is None:
                continue
            value, sentinel = units.si_value(param, raw, unit)
            out.append(store.Obs(sid, ts, param, value, raw, unit,
                                 _q(rec[idx + 1], rec[idx + 2], rec[idx + 3]), sentinel, published_at))
    return out


def _parser(f: http.Fetched) -> list[store.Obs]:
    return parse_csv(f.content, f.last_modified or f.fetched_at)


def ingest_files(
    pool: ConnectionPool,
    kind: str,
    job: str,
    only_changed: bool = True,
    force: bool = False,
) -> int:
    """Fetch the `kind` ('hourly' | 'daily') listing and ingest files that changed since the
    last successful fetch. Returns the ingest run id."""
    s = get_settings()
    with pool.connection() as conn, http.client() as c:
        conn.autocommit = True
        with store.Run(conn, SOURCE, job) as run:
            base, files, fallbacks = fetch_listing(c, kind)
            run.details.update({"listing_dir": base, "listing_fallbacks": fallbacks})
            state = ingest.load_fetch_state(conn, base)
            todo: list[tuple[str, datetime | None]] = []
            for name, listed in sorted(files.items()):
                url = base + name
                known = state.get(url)
                if force:
                    known = None
                elif only_changed and known is not None and listed <= known.replace(second=0, microsecond=0):
                    run.items_unchanged += 1
                    continue
                todo.append((name, known))
            # The directory listing can lag the files: on Oct 7 the files were rewritten at 21:31:14-20 but the
            # listing still showed 21:01 at 21:36. So when the listing shows nothing new, one conditional GET on a
            # probe file decides; if it changed, every file is re-checked with conditional GETs (304s are cheap).
            probe_changed = False
            if not todo and files and not force:
                probe = PROBE_FILE if PROBE_FILE in files else sorted(files)[0]
                probe_url = base + probe
                pf = http.fetch(c, probe_url, if_modified_since=state.get(probe_url))
                if not pf.not_modified:
                    probe_changed = True
                    run.items_unchanged = 0
                    todo = [(name, state.get(base + name)) for name in sorted(files)]
            run.items_total = len(files)
            run.details.update({"listing_files": len(files), "to_fetch": len(todo), "force": force,
                                "listing_stale_probe_changed": probe_changed})
            lock = threading.Lock()

            def work(name: str, known: datetime | None) -> None:
                with pool.connection() as wconn:
                    wconn.autocommit = True
                    sub = store.Run(wconn, SOURCE, job)  # counters only; not entered
                    ingest.fetch_and_process(c, wconn, sub, SOURCE, base + name, name,
                                             _parser, known_lm=known)
                    with lock:
                        run.items_fetched += sub.items_fetched
                        run.items_unchanged += sub.items_unchanged
                        run.rows.add(sub.rows)
                        t = run.details.setdefault("timing_s", {"fetch": 0.0, "process": 0.0})
                        for k, v in sub.details.get("timing_s", {}).items():
                            t[k] = round(t.get(k, 0.0) + v, 3)

            with ThreadPoolExecutor(max_workers=s.http_max_parallel) as ex:
                futs = {ex.submit(work, n, k): n for n, k in todo}
                for fut in as_completed(futs):
                    try:
                        fut.result()
                    except (httpx.HTTPError, ValueError, OSError) as e:
                        run.fail(futs[fut], e)
                    except Exception as e:  # noqa: BLE001 - one station never stops the others
                        run.fail(futs[fut], e)
            return run.run_id


def refresh_stations(pool: ConnectionPool) -> int:
    """Station metadata for BC from the ECCC OGC API (real-time stations plus any we hold)."""
    s = get_settings()
    url = f"{s.eccc_ogc_base}/collections/hydrometric-stations/items"
    with pool.connection() as conn, http.client() as c:
        conn.autocommit = True
        with store.Run(conn, SOURCE, "stations") as run:
            f = http.fetch(c, url, params={"f": "json", "PROV_TERR_STATE_LOC": "BC", "limit": "10000"})
            run.items_fetched = 1
            with conn.transaction():
                meta_ref = archive.store(conn, s.archive_dir, SOURCE, "hydrometric-stations-BC", f)
            feats = json.loads(f.content)["features"]
            held = {r[0] for r in conn.execute("SELECT native_id FROM stations WHERE source = 'eccc'")}
            n = 0
            with conn.transaction():
                for feat in feats:
                    p = feat["properties"]
                    sid = p["STATION_NUMBER"]
                    if not (p.get("REAL_TIME") == 1 or sid in held):
                        continue
                    coords = (feat.get("geometry") or {}).get("coordinates") or [None, None]
                    store.upsert_station_meta(conn, {
                        "station_id": f"eccc:{sid}", "source": SOURCE, "native_id": sid,
                        "name": p.get("STATION_NAME"), "lon": coords[0], "lat": coords[1],
                        "region": p.get("PROV_TERR_STATE_LOC"),
                        "drainage_area_km2": p.get("DRAINAGE_AREA_GROSS"),
                        "links": {"wateroffice": "https://wateroffice.ec.gc.ca/report/real_time_e.html"
                                                 f"?stn={sid}"},
                        "meta": {"real_time": p.get("REAL_TIME"), "status": p.get("STATUS_EN"),
                                 "drainage_area_effective_km2": p.get("DRAINAGE_AREA_EFFECT"),
                                 "metadata_raw_object_id": meta_ref.raw_object_id},
                    })
                    n += 1
            run.items_total = len(feats)
            run.details = {"features": len(feats), "upserted": n}
            return run.run_id
