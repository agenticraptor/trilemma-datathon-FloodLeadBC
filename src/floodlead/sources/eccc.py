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
from datetime import UTC, datetime
from typing import Any

import httpx
from psycopg_pool import ConnectionPool

from floodlead import archive, http, ingest, log, store, units
from floodlead.config import get_settings

L = log.get(__name__)

SOURCE = "eccc"
_LISTING_RE = re.compile(
    r'href="(BC_(?P<station>[0-9A-Z]+)_(?P<kind>hourly|daily)_hydrometric\.csv)">[^<]*</a>\s+'
    r"(?P<date>\d{4}-\d{2}-\d{2} \d{2}:\d{2})"
)


def listing_url(kind: str) -> str:
    return f"{get_settings().eccc_base}/{kind}/"


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
    base = listing_url(kind)
    with pool.connection() as conn, http.client() as c:
        conn.autocommit = True
        with store.Run(conn, SOURCE, job) as run:
            lst = http.fetch(c, base)
            files = parse_listing(lst.content.decode("utf-8", "replace"))
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
            run.items_total = len(files)
            run.details.update({"listing_files": len(files), "to_fetch": len(todo), "force": force})
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
