"""USGS Water Data OGC API (v1): 15-min stage (00065, ft) and discharge (00060, ft3/s).

Only the *primary* instantaneous series (statistic 00011) per site and parameter is used, as
listed by the `time-series-metadata` collection, so a site with several sensors cannot write two
different values to the same (station, ts, param) key.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import psycopg
from psycopg_pool import ConnectionPool

from floodlead import archive, http, ingest, log, store, units
from floodlead.config import get_settings

L = log.get(__name__)

SOURCE = "usgs"

# Nooksack and Sumas gauges (Washington). The Sumas gauge id comes from NWPS gauge SUMW1 (usgsId).
SITES: dict[str, str] = {
    "12205000": "NF Nooksack River near Glacier",
    "12208000": "MF Nooksack River near Deming",
    "12210000": "SF Nooksack River at Saxon Bridge",
    "12210500": "Nooksack River at Deming",
    "12210700": "Nooksack River at North Cedarville",
    "12211190": "Nooksack River overflow at Everson (12211190)",
    "12211195": "Nooksack River overflow at SR544, Everson",
    "12211200": "Nooksack River at Everson",
    "12211500": "Nooksack River near Lynden",
    "12213100": "Nooksack River at Ferndale",
    "12214500": "Sumas River near Sumas",
}
PARAMS = {"00065": ("level", "ft"), "00060": ("flow", "ft3/s")}
_STATE_CODES = {"Washington": "WA"}
_UNIT_MAP = {"ft": "ft", "ft^3/s": "ft3/s", "ft3/s": "ft3/s"}
_PROPS = ",".join([
    "time", "value", "parameter_code", "statistic_id", "time_series_id", "approval_status", "qualifier",
    "unit_of_measure", "monitoring_location_id", "last_modified",
])


@dataclass(frozen=True)
class Series:
    site: str
    param_code: str
    time_series_id: str
    begin: datetime | None
    end: datetime | None


def _base() -> str:
    return get_settings().usgs_ogc_base


def _headers() -> dict[str, str]:
    key = get_settings().usgs_api_key
    return {"X-Api-Key": key} if key else {}


# Process-wide: after a 429, no live USGS request is made until this monotonic time. Requests made
# while limited appeared to extend the limit (Retry-After moved from 21:45 to 21:49 UTC after more
# 429s), so we stop asking instead of probing.
_blocked_until = 0.0


def _check_not_blocked() -> None:
    remaining = _blocked_until - time.monotonic()
    if remaining > 0:
        raise http.RateLimited("(skipped locally)", int(remaining))


def _note_rate_limited(e: http.RateLimited) -> None:
    global _blocked_until
    _blocked_until = max(_blocked_until, time.monotonic() + e.retry_after_s + 5)


class Pacer:
    """Shared minimum interval between request starts, plus a global pause after a 429."""

    def __init__(self, min_interval_s: float) -> None:
        self.min_interval_s = min_interval_s
        self.lock = threading.Lock()
        self.next_at = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_at - now)
            self.next_at = max(now, self.next_at) + self.min_interval_s
        if delay:
            time.sleep(delay)

    def pause(self, seconds: float) -> None:
        with self.lock:
            self.next_at = max(self.next_at, time.monotonic() + seconds)


def _ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s).astimezone(UTC)


def parse_series_metadata(payload: dict[str, Any]) -> dict[tuple[str, str], Series]:
    """Primary instantaneous (00011) series per (site, parameter code)."""
    out: dict[tuple[str, str], Series] = {}
    for f in payload.get("features", []):
        p = f["properties"]
        if p.get("statistic_id") != "00011" or p.get("parameter_code") not in PARAMS:
            continue
        site = p["monitoring_location_id"].removeprefix("USGS-")
        key = (site, p["parameter_code"])
        s = Series(site, p["parameter_code"], p["id"], _ts(p.get("begin")), _ts(p.get("end")))
        if p.get("primary") == "Primary" or key not in out:
            out[key] = s
    return out


def fetch_series_metadata(c: httpx.Client, sites: list[str]) -> tuple[http.Fetched, dict[tuple[str, str], Series]]:
    f = http.fetch(c, f"{_base()}/collections/time-series-metadata/items", params={
        "f": "json", "monitoring_location_id": ",".join(f"USGS-{s}" for s in sites),
        "parameter_code": ",".join(PARAMS), "limit": "1000", "skipGeometry": "true",
    }, headers=_headers())
    return f, parse_series_metadata(json.loads(f.content))


def parse_items(content: bytes, allowed_series: set[str] | None) -> tuple[list[store.Obs], dict[str, int]]:
    payload = json.loads(content)
    out: list[store.Obs] = []
    stats = {"features": 0, "skipped_series": 0, "null_values": 0}
    for f in payload.get("features", []):
        stats["features"] += 1
        p = f["properties"]
        if allowed_series is not None and p.get("time_series_id") not in allowed_series:
            stats["skipped_series"] += 1
            continue
        code = p.get("parameter_code")
        if code not in PARAMS or p.get("statistic_id", "00011") != "00011":
            stats["skipped_series"] += 1
            continue
        param, default_unit = PARAMS[code]
        raw_unit = _UNIT_MAP.get(p.get("unit_of_measure") or "", default_unit)
        if p.get("value") in (None, ""):
            stats["null_values"] += 1
            continue
        raw = float(p["value"])
        value, sentinel = units.si_value(param, raw, raw_unit)
        q = {"approval_status": p.get("approval_status"), "qualifier": p.get("qualifier"),
             "time_series_id": p.get("time_series_id")}
        out.append(store.Obs(
            f"usgs:{p['monitoring_location_id'].removeprefix('USGS-')}",
            datetime.fromisoformat(p["time"]).astimezone(UTC),
            param, value, raw, raw_unit, q, sentinel, _ts(p.get("last_modified")),
        ))
    return out, stats


def next_link(content: bytes) -> str | None:
    for link in json.loads(content).get("links", []):
        if link.get("rel") == "next":
            return link.get("href")
    return None


def _items_url() -> str:
    return f"{_base()}/collections/continuous/items"


def fetch_window(
    c: httpx.Client,
    conn: psycopg.Connection,
    run: store.Run,
    site: str,
    start: datetime,
    end: datetime,
    allowed: set[str] | None,
    pacer: Pacer | None = None,
) -> int:
    """Fetch [start, end) for one site (both parameters), following pagination. Returns rows."""
    params: dict[str, str] | None = {
        "f": "json", "monitoring_location_id": f"USGS-{site}", "parameter_code": ",".join(PARAMS),
        "datetime": f"{start:%Y-%m-%dT%H:%M:%SZ}/{end:%Y-%m-%dT%H:%M:%SZ}", "limit": "50000",
        "skipGeometry": "true", "properties": _PROPS,
    }
    url: str | None = _items_url()
    n = 0
    page = 0
    while url:
        if pacer is not None:
            pacer.wait()
        f = http.fetch(c, url, params=params, headers=_headers())
        run.items_fetched += 1
        page += 1
        name = f"{site}_{start:%Y%m%dT%H%M}_{end:%Y%m%dT%H%M}_p{page}"
        rows_box: list[int] = []

        def parse(fx: http.Fetched, _box: list[int] = rows_box, _name: str = name) -> list[store.Obs]:
            rows, stats = parse_items(fx.content, allowed)
            # The OGC `datetime` interval is closed; each window owns [start, end) so chunks never overlap.
            rows = [r for r in rows if start <= r.ts < end]
            _box.append(len(rows))
            if stats["null_values"] or stats["skipped_series"]:
                run.details.setdefault("parse_stats", {})[_name] = stats
            return rows

        ingest.process_payload(conn, run, SOURCE, name, f, parse)
        n += rows_box[0] if rows_box else 0
        url, params = next_link(f.content), None
    return n


def _allowed(meta: dict[tuple[str, str], Series], site: str) -> set[str] | None:
    ids = {s.time_series_id for (st, _), s in meta.items() if st == site}
    return ids or None


def live_sites(meta: dict[tuple[str, str], Series], now: datetime) -> list[str]:
    """Sites whose primary series reported within the last 7 days (per metadata)."""
    live = set()
    for (site, _), s in meta.items():
        if s.end is not None and now - s.end < timedelta(days=7):
            live.add(site)
    return sorted(live)


def ingest_live_nwis(pool: ConnectionPool, conn: psycopg.Connection, c: httpx.Client, run: store.Run,
                     start: datetime, end: datetime, reason: str, sites: list[str] | None = None) -> None:
    """Fallback for live ingestion while the OGC API is rate-limited: one NWIS IV request for the given
    sites (default: all live sites from the newest archived metadata)."""
    s = get_settings()
    meta, meta_src = archived_series_metadata(conn, s.archive_dir)
    if sites is None:
        sites = live_sites(meta, end)
        run.items_total = len(sites)
    f = http.fetch(c, NWIS_IV_URL, params={
        "format": "json", "sites": ",".join(sites), "parameterCd": ",".join(PARAMS), "siteStatus": "all",
        "startDT": f"{start:%Y-%m-%dT%H:%MZ}", "endDT": f"{end:%Y-%m-%dT%H:%MZ}",
    })
    run.items_fetched += 1
    box: list[int] = []

    def parse(fx: http.Fetched) -> list[store.Obs]:
        rows, _ = parse_nwis_iv(fx.content)
        box.append(len({r.station_id for r in rows}))
        return rows

    ingest.process_payload(conn, run, SOURCE, f"nwis-iv_live_{end:%Y%m%dT%H%M}", f, parse)
    run.details["nwis_fallback"] = {"reason": reason, "sites": sites, "sites_with_data": box[0] if box else 0,
                                    "metadata_raw_object_id": meta_src}


def ingest_live(pool: ConnectionPool, hours: int = 6) -> int:
    s = get_settings()
    now = datetime.now(UTC)
    with pool.connection() as conn, http.client() as c:
        conn.autocommit = True
        with store.Run(conn, SOURCE, "live") as run:
            try:
                _check_not_blocked()
                mf, meta = fetch_series_metadata(c, list(SITES))
            except http.RateLimited as e:
                _note_rate_limited(e)
                run.details = {"api": "nwis-iv (fallback)"}
                ingest_live_nwis(pool, conn, c, run, now - timedelta(hours=hours), now,
                                 f"OGC API rate-limited (retry after {e.retry_after_s} s)")
                return run.run_id
            with conn.transaction():
                archive.store(conn, s.archive_dir, SOURCE, "time-series-metadata", mf)
            sites = live_sites(meta, now)
            dropped = sorted(set(SITES) - set(sites))
            run.items_total = len(sites)
            run.details = {"sites": sites, "dropped_no_recent_data": dropped}
            lock = threading.Lock()
            start = now - timedelta(hours=hours)

            limited: list[http.RateLimited] = []

            def work(site: str) -> None:
                if limited:  # quota exhausted: do not spend more requests this cycle
                    raise limited[0]
                with pool.connection() as wconn:
                    wconn.autocommit = True
                    sub = store.Run(wconn, SOURCE, "live")
                    fetch_window(c, wconn, sub, site, start, now, _allowed(meta, site))
                    with lock:
                        run.items_fetched += sub.items_fetched
                        run.rows.add(sub.rows)

            limited_sites: list[str] = []
            with ThreadPoolExecutor(max_workers=s.http_max_parallel) as ex:
                futs = {ex.submit(work, site): site for site in sites}
                for fut in as_completed(futs):
                    try:
                        fut.result()
                    except http.RateLimited as e:
                        limited.append(e)
                        _note_rate_limited(e)
                        limited_sites.append(futs[fut])
                    except Exception as e:  # noqa: BLE001 - one site never stops the others
                        run.fail(futs[fut], e)
            if limited_sites:
                # Sites the OGC API refused mid-run get one NWIS IV request in the same run.
                try:
                    ingest_live_nwis(pool, conn, c, run, start, now,
                                     f"OGC API rate-limited mid-run (retry after {limited[0].retry_after_s} s)",
                                     sites=sorted(limited_sites))
                except Exception as e:  # noqa: BLE001 - record each site as failed
                    for site in limited_sites:
                        run.fail(site, e)
            return run.run_id


def refresh_stations(pool: ConnectionPool) -> int:
    s = get_settings()
    with pool.connection() as conn, http.client() as c:
        conn.autocommit = True
        with store.Run(conn, SOURCE, "stations") as run:
            _check_not_blocked()
            try:
                f = http.fetch(c, f"{_base()}/collections/monitoring-locations/items", params={
                    "f": "json", "id": ",".join(f"USGS-{x}" for x in SITES), "limit": "100",
                }, headers=_headers())
            except http.RateLimited as e:
                _note_rate_limited(e)
                raise
            run.items_fetched = 1
            with conn.transaction():
                ref = archive.store(conn, s.archive_dir, SOURCE, "monitoring-locations", f)
            mf, meta = fetch_series_metadata(c, list(SITES))
            with conn.transaction():
                archive.store(conn, s.archive_dir, SOURCE, "time-series-metadata", mf)
            feats = json.loads(f.content).get("features", [])
            run.items_total = len(feats)
            with conn.transaction():
                for feat in feats:
                    p = feat["properties"]
                    site = str(feat.get("id", p.get("id", ""))).removeprefix("USGS-")
                    coords = (feat.get("geometry") or {}).get("coordinates") or [None, None]
                    area_mi2 = p.get("drainage_area")
                    series = {
                        code: {"time_series_id": sr.time_series_id,
                               "begin": sr.begin.isoformat() if sr.begin else None,
                               "end": sr.end.isoformat() if sr.end else None}
                        for (st, code), sr in meta.items() if st == site
                    }
                    store.upsert_station_meta(conn, {
                        "station_id": f"usgs:{site}", "source": SOURCE, "native_id": site,
                        "name": p.get("monitoring_location_name") or SITES.get(site),
                        "lon": coords[0], "lat": coords[1],
                        "region": _STATE_CODES.get(p.get("state_name") or "", p.get("state_name") or "WA"),
                        "drainage_area_km2": float(area_mi2) * 2.589988110336 if area_mi2 else None,
                        "params": sorted(PARAMS[c][0] for (st, c) in meta if st == site),
                        "links": {"usgs": f"https://waterdata.usgs.gov/monitoring-location/USGS-{site}/"},
                        "meta": {"series_00011": series, "metadata_raw_object_id": ref.raw_object_id},
                    })
            return run.run_id


NWIS_IV_URL = "https://waterservices.usgs.gov/nwis/iv/"
_NWIS_UNITS = {"ft": "ft", "ft3/s": "ft3/s"}


def parse_nwis_iv(content: bytes) -> tuple[list[store.Obs], dict[str, int]]:
    """Legacy NWIS IV (WaterML-JSON). Used for the history backfill while the OGC API is rate-limited
    (data-contract record 6 lists NWIS as the fallback). Values keep their published offsets; the NWIS
    noDataValue (-999999) is flagged as a sentinel by the shared rule."""
    payload = json.loads(content)
    out: list[store.Obs] = []
    stats = {"series": 0, "values": 0, "extra_methods_skipped": 0}
    for t in payload.get("value", {}).get("timeSeries", []):
        stats["series"] += 1
        code = t["variable"]["variableCode"][0]["value"]
        if code not in PARAMS:
            continue
        param, default_unit = PARAMS[code]
        raw_unit = _NWIS_UNITS.get(t["variable"]["unit"]["unitCode"], default_unit)
        site = t["sourceInfo"]["siteCode"][0]["value"]
        methods = t.get("values") or []
        stats["extra_methods_skipped"] += max(0, len(methods) - 1)
        for v in (methods[0]["value"] if methods else []):
            stats["values"] += 1
            raw = float(v["value"])
            value, sentinel = units.si_value(param, raw, raw_unit)
            quals = v.get("qualifiers") or []
            appr = "Approved" if "A" in quals else "Provisional" if "P" in quals else None
            other = [q for q in quals if q not in ("A", "P")]
            q = {"approval_status": appr, "qualifier": ",".join(other) or None, "time_series_id": None,
                 "source_api": "nwis-iv"}
            out.append(store.Obs(f"usgs:{site}", datetime.fromisoformat(v["dateTime"]).astimezone(UTC), param,
                                 value, raw, raw_unit, q, sentinel, None))
    return out, stats


def fetch_nwis_window(
    c: httpx.Client,
    conn: psycopg.Connection,
    run: store.Run,
    site: str,
    start: datetime,
    end: datetime,
    skip: list[tuple[datetime, datetime]],
    pacer: Pacer | None = None,
) -> int:
    """One NWIS IV request for [start, end); rows inside `skip` intervals (already loaded from the OGC API)
    are dropped so the two APIs never write the same key."""
    if pacer is not None:
        pacer.wait()
    f = http.fetch(c, NWIS_IV_URL, params={
        "format": "json", "sites": site, "parameterCd": ",".join(PARAMS), "siteStatus": "all",
        "startDT": f"{start:%Y-%m-%dT%H:%MZ}", "endDT": f"{end:%Y-%m-%dT%H:%MZ}",
    })
    run.items_fetched += 1
    name = f"nwis-iv_{site}_{start:%Y%m%dT%H%M}_{end:%Y%m%dT%H%M}"
    box: list[int] = []

    def parse(fx: http.Fetched) -> list[store.Obs]:
        rows, _ = parse_nwis_iv(fx.content)
        # Closed bounds on skip intervals: OGC `datetime` intervals are closed, so earlier OGC chunks may hold
        # the row exactly at their end.
        rows = [r for r in rows if start <= r.ts < end and not any(a <= r.ts <= b for a, b in skip)]
        box.append(len(rows))
        return rows

    ingest.process_payload(conn, run, SOURCE, name, f, parse)
    return box[0] if box else 0


def archived_series_metadata(conn: psycopg.Connection, archive_dir: Any) -> tuple[dict[tuple[str, str], Series], int]:
    row = conn.execute(
        "SELECT raw_object_id, archive_path FROM raw_objects WHERE source = 'usgs' AND archive_path LIKE %s"
        " ORDER BY fetched_at DESC LIMIT 1", ("%/time-series-metadata.%",)).fetchone()
    if row is None:
        raise RuntimeError("no archived USGS time-series-metadata payload; run usgs-stations first")
    import gzip

    with gzip.open(archive_dir / row[1]) as fh:
        return parse_series_metadata(json.load(fh)), row[0]


def month_chunks(start: datetime, end: datetime, months: int = 1) -> list[tuple[datetime, datetime]]:
    """Calendar-aligned chunks of `months` months covering [start, end)."""
    out = []
    cur = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    cur = cur.replace(month=1 + ((cur.month - 1) // months) * months)
    while cur < end:
        nxt = cur
        for _ in range(months):
            nxt = (nxt.replace(day=28) + timedelta(days=4)).replace(day=1)
        out.append((max(cur, start), min(nxt, end)))
        cur = nxt
    return out


def covered(intervals: list[tuple[datetime, datetime]], a: datetime, b: datetime) -> bool:
    """True if the union of `intervals` covers [a, b)."""
    pos = a
    for s0, s1 in sorted(intervals):
        if s0 > pos:
            break
        pos = max(pos, s1)
        if pos >= b:
            return True
    return pos >= b


# Sites the acceptance checks depend on go first; the rest follow.
PRIORITY = ["12210700", "12211200", "12211195", "12214500", "12213100", "12208000", "12205000", "12210000",
            "12211500", "12211190"]


def backfill(
    pool: ConnectionPool,
    sites: list[str] | None,
    since: datetime,
    until: datetime,
    chunk_months: int = 6,
    max_attempts: int = 6,
    api: str = "auto",
) -> int:
    """Chunked per site (both parameters per request), resumable: a chunk already covered by recorded
    chunks (any size) is skipped. Requests are paced (usgs_backfill_min_interval_s) and the whole
    backfill pauses for Retry-After when the API rate-limits, then retries the chunk."""
    s = get_settings()
    job = "backfill-usgs"
    if api == "auto":
        api = "ogc" if s.usgs_api_key else "nwis"
    if api == "nwis":
        # Leave the most recent day to live ingestion (OGC), so the APIs never overlap.
        until = min(until, datetime.now(UTC) - timedelta(days=1))
    pacer = Pacer(1.0 if (api == "nwis" or s.usgs_api_key) else s.usgs_backfill_min_interval_s)
    workers = 2  # each 6-month page is ~15-25 MB of JSON; keep memory well under the 1 GiB limit
    with pool.connection() as conn, http.client() as c:
        conn.autocommit = True
        with store.Run(conn, SOURCE, job) as run:
            if api == "nwis":
                # Do not touch the (rate-limited) OGC API at all: use the newest archived metadata payload.
                meta, meta_src = archived_series_metadata(conn, s.archive_dir)
            else:
                while True:
                    try:
                        mf, meta = fetch_series_metadata(c, list(SITES))
                        break
                    except http.RateLimited as e:
                        L.warning("usgs rate limited before start; waiting", **log.kv(retry_after_s=e.retry_after_s))
                        time.sleep(e.retry_after_s + 5)
                with conn.transaction():
                    meta_src = archive.store(conn, s.archive_dir, SOURCE, "time-series-metadata", mf).raw_object_id
            wanted = sites or live_sites(meta, datetime.now(UTC))
            done: dict[str, list[tuple[datetime, datetime]]] = {}
            for k, a, b in conn.execute(
                "SELECT key, chunk_start, chunk_end FROM backfill_chunks WHERE job = %s", (job,)
            ):
                done.setdefault(k, []).append((a, b))
            by_site: dict[str, list[tuple[str, datetime, datetime]]] = {}
            plan: dict[str, Any] = {}
            for site in wanted:
                begins = [sr.begin for (st, _), sr in meta.items() if st == site and sr.begin]
                if not begins:
                    plan[site] = "no 00011 series; skipped"
                    continue
                site_start = max(since, min(begins))
                chunks = month_chunks(site_start, until, chunk_months)
                todo = [(site, a, b) for a, b in chunks if not covered(done.get(f"usgs:{site}", []), a, b)]
                plan[site] = {"from": site_start.isoformat(), "chunks": len(chunks), "todo": len(todo)}
                by_site[site] = sorted(todo, key=lambda t: t[1], reverse=True)  # newest first
            order = [x for x in PRIORITY if x in by_site] + [x for x in by_site if x not in PRIORITY]
            tasks = [t for site in order for t in by_site[site]]
            run.items_total = len(tasks)
            run.details = {"plan": plan, "since": since.isoformat(), "until": until.isoformat(),
                           "chunk_months": chunk_months, "min_interval_s": pacer.min_interval_s, "api": api,
                           "metadata_raw_object_id": meta_src,
                           "api_key": bool(s.usgs_api_key)}
            L.info("usgs backfill plan", **log.kv(tasks=len(tasks), plan=plan))
            lock = threading.Lock()
            rate_limited = {"count": 0}

            def work(site: str, a: datetime, b: datetime) -> None:
                for attempt in range(1, max_attempts + 1):
                    try:
                        with pool.connection() as wconn:
                            wconn.autocommit = True
                            sub = store.Run(wconn, SOURCE, job)
                            if api == "nwis":
                                n = fetch_nwis_window(c, wconn, sub, site, a, b, done.get(f"usgs:{site}", []), pacer)
                            else:
                                n = fetch_window(c, wconn, sub, site, a, b, _allowed(meta, site), pacer)
                            with wconn.transaction():
                                wconn.execute(
                                    "INSERT INTO backfill_chunks (job, key, chunk_start, chunk_end, rows)"
                                    " VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                                    (job, f"usgs:{site}", a, b, n),
                                )
                            with lock:
                                run.items_fetched += sub.items_fetched
                                run.rows.add(sub.rows)
                            return
                    except http.RateLimited as e:
                        with lock:
                            rate_limited["count"] += 1
                        L.warning("usgs rate limited; pausing backfill",
                                  **log.kv(site=site, chunk=a.isoformat(), retry_after_s=e.retry_after_s,
                                           attempt=attempt))
                        pacer.pause(e.retry_after_s + 5)
                raise RuntimeError(f"still rate limited after {max_attempts} attempts")

            with ThreadPoolExecutor(max_workers=workers) as ex:
                futs = {ex.submit(work, *t): t for t in tasks}
                for i, fut in enumerate(as_completed(futs), 1):
                    site, a, _ = futs[fut]
                    try:
                        fut.result()
                    except Exception as e:  # noqa: BLE001 - one chunk never stops the others
                        run.fail(f"{site}@{a:%Y-%m}", e)
                    if i % 20 == 0:
                        L.info("usgs backfill progress", **log.kv(done=i, total=len(tasks),
                                                                  rows=run.rows.inserted))
            run.details["rate_limited_events"] = rate_limited["count"]
            return run.run_id
