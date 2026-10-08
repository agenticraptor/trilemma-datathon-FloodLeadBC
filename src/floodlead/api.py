"""Read-only public API (FastAPI). Every response carries an `attribution` field."""

from __future__ import annotations

import json
import shutil
import statistics
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from floodlead import db, replay
from floodlead.config import ATTRIBUTION, REPO_URL, get_settings

MAX_WINDOW = timedelta(days=7)
NOT_A_WARNING = (
    "FloodLead BC is not an official warning service. Follow EmergencyInfoBC, the BC River Forecast "
    "Centre, NOAA/NWS and your local authority."
)

# Health thresholds (documented in docs/stages/STAGE-01-live-archive.md, D-01.14).
HEALTH = {
    "eccc": {"run_green_min": 30, "run_amber_min": 90, "lag_green_min": 150, "lag_amber_min": 360,
             "reporting_green_frac": 0.8},
    "usgs": {"run_green_min": 45, "run_amber_min": 120, "lag_green_min": 120, "lag_amber_min": 360,
             "reporting_green_frac": 0.8},
    "nwps": {"run_green_min": 90, "run_amber_min": 180, "issuance_green_h": 36, "issuance_amber_h": 72},
    "disk": {"amber_pct": 80, "red_pct": 90},
}
RATE_LIMIT_PER_MIN = 120
_ORDER = {"green": 0, "amber": 1, "red": 2}


class RateLimiter:
    """Token bucket per client IP (in memory, per API process)."""

    def __init__(self, per_min: int) -> None:
        self.rate = per_min / 60.0
        self.cap = float(per_min)
        self.buckets: dict[str, tuple[float, float]] = {}
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            tokens, last = self.buckets.get(key, (self.cap, now))
            tokens = min(self.cap, tokens + (now - last) * self.rate)
            ok = tokens >= 1.0
            self.buckets[key] = (tokens - 1.0 if ok else tokens, now)
            if len(self.buckets) > 10000:
                self.buckets.clear()
            return ok


_state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _state["pool"] = db.pool(min_size=1, max_size=4)

    def warm() -> None:  # the replay takes ~9 s cold; compute it once at start so visitors never wait
        try:
            _replay()
        except Exception:  # noqa: BLE001 - warming is best effort
            pass

    threading.Thread(target=warm, name="warm-replay", daemon=True).start()
    try:
        yield
    finally:
        _state["pool"].close()


app = FastAPI(
    title="FloodLead BC — public read API",
    version="0.1.0",
    description=(
        "Read-only access to the river observations, official forecasts and raw-archive index that "
        f"FloodLead BC holds. {NOT_A_WARNING} Source: {REPO_URL}"
    ),
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse({"detail": exc.detail, "attribution": ATTRIBUTION}, status_code=exc.status_code,
                        headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse({"detail": jsonable_encoder(exc.errors()), "attribution": ATTRIBUTION}, status_code=422)
_limiter = RateLimiter(RATE_LIMIT_PER_MIN)


@app.middleware("http")
async def rate_limit(request: Request, call_next):  # type: ignore[no-untyped-def]
    ip = request.client.host if request.client else "unknown"
    if request.url.path.startswith("/v1/") and not _limiter.allow(ip):
        return JSONResponse(
            {"detail": f"rate limit: {RATE_LIMIT_PER_MIN} requests per minute per client",
             "attribution": ATTRIBUTION},
            status_code=429, headers={"Retry-After": "30"},
        )
    return await call_next(request)


def _pool() -> ConnectionPool:
    return _state["pool"]


def _q(sql: str, params: dict[str, Any] | tuple | None = None) -> list[dict[str, Any]]:
    with _pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def _wrap(body: dict[str, Any]) -> dict[str, Any]:
    body["attribution"] = ATTRIBUTION
    return body


def _age_min(ts: datetime | None, now: datetime) -> float | None:
    return None if ts is None else round((now - ts).total_seconds() / 60, 1)


def _worst(*s: str) -> str:
    return max(s, key=lambda x: _ORDER[x])


_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _cached(key: str, ttl: float, fn) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    val = fn()
    _cache[key] = (time.monotonic(), val)
    return val


def _gauge_health(source: str, now: datetime) -> dict[str, Any]:
    t = HEALTH[source]
    run = _q(
        "SELECT run_id, finished_at, status FROM ingest_runs WHERE source = %s AND job = 'live'"
        " AND status IN ('ok', 'partial') ORDER BY finished_at DESC LIMIT 1", (source,))
    last = _q(
        "SELECT status, finished_at, error_text FROM ingest_runs WHERE source = %s AND job = 'live'"
        " AND finished_at IS NOT NULL ORDER BY finished_at DESC LIMIT 1", (source,))
    per_station = _q(
        "SELECT station_id, max(ts) AS newest FROM observations"
        " WHERE station_id LIKE %s AND ts > now() - interval '24 hours' AND NOT is_sentinel GROUP BY station_id",
        (f"{source}:%",))
    known = _q(
        "SELECT count(DISTINCT station_id) AS n FROM observations"
        " WHERE station_id LIKE %s AND ts > now() - interval '7 days'", (f"{source}:%",))[0]["n"]
    newest = max((r["newest"] for r in per_station), default=None)
    lags = [(now - r["newest"]).total_seconds() / 60 for r in per_station]
    reporting_3h = sum(1 for r in per_station if now - r["newest"] <= timedelta(hours=3))
    run_age = _age_min(run[0]["finished_at"], now) if run else None
    lag = _age_min(newest, now)
    reasons = []
    run_s = ("green" if run_age is not None and run_age <= t["run_green_min"] else
             "amber" if run_age is not None and run_age <= t["run_amber_min"] else "red")
    if run_s != "green":
        reasons.append(f"last successful live run {run_age} min ago")
    lag_s = ("green" if lag is not None and lag <= t["lag_green_min"] else
             "amber" if lag is not None and lag <= t["lag_amber_min"] else "red")
    if lag_s != "green":
        reasons.append(f"newest observation {lag} min old")
    frac = reporting_3h / known if known else 0.0
    rep_s = "green" if frac >= t["reporting_green_frac"] else "amber"
    if rep_s != "green":
        reasons.append(f"only {reporting_3h} of {known} stations reported in the last 3 h")
    return {
        "status": _worst(run_s, lag_s, rep_s),
        "reasons": reasons,
        "last_successful_run": {"run_id": run[0]["run_id"], "finished_at": run[0]["finished_at"],
                                "age_min": run_age} if run else None,
        "last_run_status": last[0]["status"] if last else None,
        "newest_observation": newest,
        "lag_min": lag,
        "station_lag_min_p50": round(statistics.median(lags), 1) if lags else None,
        "station_lag_min_p90": round(statistics.quantiles(lags, n=10)[-1], 1) if len(lags) >= 10 else None,
        "stations_reporting_3h": reporting_3h,
        "stations_with_data_7d": known,
        "thresholds": t,
    }


def _nwps_health(now: datetime) -> dict[str, Any]:
    t = HEALTH["nwps"]
    run = _q("SELECT run_id, finished_at FROM ingest_runs WHERE source = 'nwps' AND job = 'live'"
             " AND status IN ('ok', 'partial') ORDER BY finished_at DESC LIMIT 1")
    iss = _q("SELECT lid, max(issued_at) AS issued_at, max(fetched_at) AS fetched_at FROM official_forecasts"
             " GROUP BY lid ORDER BY lid")
    newest = max((r["issued_at"] for r in iss), default=None)
    run_age = _age_min(run[0]["finished_at"], now) if run else None
    iss_age_h = None if newest is None else round((now - newest).total_seconds() / 3600, 2)
    reasons = []
    run_s = ("green" if run_age is not None and run_age <= t["run_green_min"] else
             "amber" if run_age is not None and run_age <= t["run_amber_min"] else "red")
    if run_s != "green":
        reasons.append(f"last successful live run {run_age} min ago")
    iss_s = ("green" if iss_age_h is not None and iss_age_h <= t["issuance_green_h"] else
             "amber" if iss_age_h is not None and iss_age_h <= t["issuance_amber_h"] else "red")
    if iss_s != "green":
        reasons.append(f"newest official forecast issued {iss_age_h} h ago")
    return {
        "status": _worst(run_s, iss_s),
        "reasons": reasons,
        "last_successful_run": {"run_id": run[0]["run_id"], "finished_at": run[0]["finished_at"],
                                "age_min": run_age} if run else None,
        "newest_observation": newest,  # for NWPS: newest forecast issuance
        "lag_min": None if newest is None else round((now - newest).total_seconds() / 60, 1),
        "newest_issuance_age_h": iss_age_h,
        "gauges_with_forecasts": [{"lid": r["lid"], "latest_issued_at": r["issued_at"]} for r in iss],
        "stations_reporting_3h": None,
        "thresholds": t,
    }


def _health() -> dict[str, Any]:
    now = datetime.now(UTC)
    s = get_settings()
    sources = {"eccc": _gauge_health("eccc", now), "usgs": _gauge_health("usgs", now), "nwps": _nwps_health(now)}
    try:
        du = shutil.disk_usage(s.archive_dir)
        used_pct = round(100 * du.used / du.total, 1)
        disk_s = ("red" if used_pct >= HEALTH["disk"]["red_pct"] else
                  "amber" if used_pct >= HEALTH["disk"]["amber_pct"] else "green")
        disk = {"status": disk_s, "used_pct": used_pct, "total_bytes": du.total, "used_bytes": du.used,
                "free_bytes": du.free, "thresholds": HEALTH["disk"]}
    except OSError as e:
        disk = {"status": "red", "error": repr(e)}
    arch = _q("SELECT count(*) FILTER (WHERE archive_path IS NOT NULL) AS files,"
              " coalesce(sum(archive_bytes), 0)::bigint AS bytes_on_disk, coalesce(sum(bytes), 0)::bigint AS raw_bytes,"
              " count(*) FILTER (WHERE archive_error IS NOT NULL) AS write_failures,"
              " count(*) FILTER (WHERE fetched_at > now() - interval '1 hour') AS files_last_hour"
              " FROM raw_objects")[0]
    overall = _worst(*(v["status"] for v in sources.values()), disk["status"])
    return _wrap({"status": overall, "generated_at": now, "sources": sources, "disk": disk,
                  "archive": arch, "notice": NOT_A_WARNING})


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def index() -> dict[str, Any]:
    return _wrap({"name": "FloodLead BC public read API", "docs": "/docs", "health": "/v1/health",
                  "stations": "/v1/stations", "source": REPO_URL, "notice": NOT_A_WARNING})


@app.api_route("/v1/health", methods=["GET", "HEAD"])
def health() -> dict[str, Any]:
    """Per-source freshness (green/amber/red), disk use and archive size. Cached for 30 s."""
    return _cached("health", 30, _health)


_STATION_COLS = ("station_id, source, native_id, name, lat, lon, region, drainage_area_km2, params,"
                 " official_thresholds, links")


def _latest(station_ids: list[str] | None = None) -> dict[str, dict[str, Any]]:
    # One backward primary-key probe per (station, param) instead of sorting 3 days of rows.
    rows = _q(
        "SELECT s.station_id, p.param, o.ts, o.value FROM stations s"
        " CROSS JOIN (VALUES ('level'), ('flow')) AS p(param)"
        " CROSS JOIN LATERAL (SELECT ts, value FROM observations o WHERE o.station_id = s.station_id"
        "   AND o.param = p.param AND o.ts > now() - interval '3 days' AND NOT o.is_sentinel"
        "   ORDER BY o.ts DESC LIMIT 1) o"
        + (" WHERE s.station_id = ANY(%(ids)s)" if station_ids else ""),
        {"ids": station_ids} if station_ids else None,
    )
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        unit = "m" if r["param"] == "level" else "m3/s"
        out.setdefault(r["station_id"], {})[r["param"]] = {"ts": r["ts"], "value": r["value"], "unit": unit}
    return out


@app.api_route("/v1/stations", methods=["GET", "HEAD"])
def stations(
    source: str | None = Query(None, description="eccc | usgs"),
    region: str | None = Query(None, description="province/state code, e.g. BC, WA"),
    q: str | None = Query(None, description="case-insensitive text search in name or id"),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Stations we hold, with metadata and the latest reading per parameter (last 3 days)."""
    where, p = ["TRUE"], {}
    if source:
        where.append("source = %(source)s")
        p["source"] = source
    if region:
        where.append("upper(region) = upper(%(region)s)")
        p["region"] = region
    if q:
        where.append("(name ILIKE %(q)s OR station_id ILIKE %(q)s)")
        p["q"] = f"%{q}%"
    p.update(limit=limit, offset=offset)
    rows = _q(f"SELECT {_STATION_COLS} FROM stations WHERE {' AND '.join(where)}"
              " ORDER BY station_id LIMIT %(limit)s OFFSET %(offset)s", p)
    total = _q(f"SELECT count(*) AS n FROM stations WHERE {' AND '.join(where)}", p)[0]["n"]
    latest = _cached("latest", 60, _latest)
    for r in rows:
        r["latest"] = latest.get(r["station_id"], {})
        r["has_official_thresholds"] = bool((r.get("official_thresholds") or {}).get("categories"))
        r.pop("official_thresholds", None)
    return _wrap({"count": len(rows), "total": total, "limit": limit, "offset": offset, "stations": rows})


@app.api_route("/v1/stations/{station_id}", methods=["GET", "HEAD"])
def station(station_id: str) -> dict[str, Any]:
    """One station, including official thresholds (NOAA NWS flood categories where they exist)."""
    rows = _q(f"SELECT {_STATION_COLS}, meta, first_seen_at, updated_at FROM stations WHERE station_id = %s",
              (station_id,))
    if not rows:
        raise HTTPException(404, f"unknown station {station_id!r} (ids look like eccc:08MH001 or usgs:12210700)")
    r = rows[0]
    r["latest"] = _latest([station_id]).get(station_id, {})
    return _wrap(r)


def _parse_time(v: str | None, name: str) -> datetime | None:
    if v is None:
        return None
    try:
        t = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError as e:
        raise HTTPException(400, f"{name} must be ISO 8601, e.g. 2026-10-07T00:00:00Z") from e
    return t if t.tzinfo else t.replace(tzinfo=UTC)


@app.api_route("/v1/stations/{station_id}/observations", methods=["GET", "HEAD"])
def observations(
    station_id: str,
    param: str | None = Query(None, pattern="^(level|flow)$"),
    since: str | None = Query(None, description="ISO 8601 UTC; default until - 24 h"),
    until: str | None = Query(None, description="ISO 8601 UTC; default now"),
    include_sentinels: bool = Query(False, description="include flagged no-data codes (value is null)"),
    days: int | None = Query(None, ge=1, le=7, description="window length ending at `until` (default 1 day)"),
) -> dict[str, Any]:
    """Observations in SI units (m, m3/s) with the raw published value. At most 7 days per call."""
    t1 = _parse_time(until, "until") or datetime.now(UTC)
    t0 = _parse_time(since, "since") or t1 - timedelta(days=days or 1)
    if t1 <= t0:
        raise HTTPException(400, "until must be after since")
    if t1 - t0 > MAX_WINDOW:
        raise HTTPException(400, "window too large: at most 7 days per call")
    if not _q("SELECT 1 FROM stations WHERE station_id = %s", (station_id,)):
        raise HTTPException(404, f"unknown station {station_id!r}")
    rows = _q(
        "SELECT ts, param, value, raw_value, raw_unit, quality, is_sentinel, revision_count, first_seen_at"
        " FROM observations WHERE station_id = %(sid)s AND ts >= %(t0)s AND ts < %(t1)s"
        + (" AND param = %(param)s" if param else "")
        + ("" if include_sentinels else " AND NOT is_sentinel")
        + " ORDER BY param, ts",
        {"sid": station_id, "t0": t0, "t1": t1, "param": param},
    )
    for r in rows:
        r["unit"] = "m" if r["param"] == "level" else "m3/s"
    return _wrap({"station_id": station_id, "since": t0, "until": t1, "param": param,
                  "include_sentinels": include_sentinels, "count": len(rows), "observations": rows})


@app.api_route("/v1/official-forecasts/{lid}", methods=["GET", "HEAD"])
def official_forecasts(
    lid: str,
    issued_after: str | None = Query(None, description="ISO 8601 UTC; default: latest issuance only"),
) -> dict[str, Any]:
    """NOAA NWS official forecasts for an NWPS gauge (e.g. NRKW1), exactly as published."""
    lid = lid.upper()
    t = _parse_time(issued_after, "issued_after")
    if t is None:
        rows = _q("SELECT * FROM official_forecasts WHERE lid = %(lid)s AND issued_at ="
                  " (SELECT max(issued_at) FROM official_forecasts WHERE lid = %(lid)s) ORDER BY valid_at",
                  {"lid": lid})
    else:
        rows = _q("SELECT * FROM official_forecasts WHERE lid = %(lid)s AND issued_at > %(t)s"
                  " ORDER BY issued_at, valid_at LIMIT 5000", {"lid": lid, "t": t})
    st = _q("SELECT station_id, name, official_thresholds FROM stations WHERE links->>'nwps_lid' = %s", (lid,))
    if not rows and not st:
        raise HTTPException(404, f"no official forecasts or gauge for {lid!r}")
    issuances: dict[datetime, list[dict[str, Any]]] = {}
    for r in rows:
        issuances.setdefault(r["issued_at"], []).append(
            {"valid_at": r["valid_at"], "stage_ft": r["stage_ft"], "flow_kcfs": r["flow_kcfs"],
             "generated_at": r["generated_at"]})
    return _wrap({
        "lid": lid,
        "station": st[0] if st else None,
        "issuances": [{"issued_at": k, "points": v} for k, v in issuances.items()],
        "note": "Official NOAA NWS forecast, stored and served unmodified. Not affiliated with or endorsed "
                "by NOAA/NWS.",
    })


_REPLAY_TTL_S = 3600


def _replay() -> dict[str, Any]:
    def build() -> dict[str, Any]:
        with _pool().connection() as conn:
            r = replay.compute(conn)
        r["gauges"] = {
            "cedarville": {"station_id": replay.CEDARVILLE, "name": "Nooksack River at North Cedarville, WA",
                           "stages_ft": replay.CEDARVILLE_STAGES_FT},
            "overflow": {"station_id": replay.OVERFLOW, "name": "Nooksack River overflow at SR 544, Everson, WA",
                         "stages_ft": replay.OVERFLOW_STAGES_FT, "record_begins": r.pop("overflow_record_begins"),
                         "note": "Reported only while water was flowing until 2026-10-01; continuous since."},
            "everson": {"station_id": replay.EVERSON, "name": "Nooksack River at Everson, WA",
                        "stages_ft": {"action": replay.EVERSON_ACTION_FT}},
        }
        r["caveats"] = replay.CAVEATS
        r["method"] = (replay.__doc__ or "").strip()
        return r

    return _cached("replay", _REPLAY_TTL_S, build)


@app.api_route("/v1/replay/overflow", methods=["GET", "HEAD"])
def replay_overflow() -> dict[str, Any]:
    """Every North Cedarville minor-stage event since 2007 and when the Sumas Prairie overflow (Overflow at SR 544)
    began, computed from stored USGS data. Approved historical data, not what was visible in real time."""
    return _wrap(dict(_replay()))


@app.api_route("/v1/replay/overflow/{event_id}/series", methods=["GET", "HEAD"])
def replay_series(event_id: str) -> dict[str, Any]:
    """Levels (ft, as published) at North Cedarville, the overflow gauge and Everson around one event."""
    ev = next((e for e in _replay()["events"] if e["event_id"] == event_id), None)
    if ev is None:
        raise HTTPException(404, f"unknown event {event_id!r}; see /v1/replay/overflow")

    def build() -> dict[str, Any]:
        with _pool().connection() as conn:
            return replay.series(conn, ev)

    return _wrap(dict(_cached(f"replay-series-{event_id}", _REPLAY_TTL_S, build)))


SPEC_URL = f"{REPO_URL}/blob/main/docs/ledger-spec.md"
_ENTRY_COLS = "seq, entry_type, created_at, canonical, prev_hash, entry_hash"


def _entry(r: dict[str, Any]) -> dict[str, Any]:
    return {"seq": r["seq"], "entry_type": r["entry_type"], "created_at": r["created_at"],
            "canonical": r["canonical"], "prev_hash": r["prev_hash"], "entry_hash": r["entry_hash"]}


@app.api_route("/v1/ledger", methods=["GET", "HEAD"])
def ledger_page(after_seq: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=1000)) -> dict[str, Any]:
    """Ledger entries in seq order, with the exact canonical text that was hashed. Verify with
    entry_hash = sha256(prev_hash + "\\n" + canonical); see the spec."""
    rows = _q(f"SELECT {_ENTRY_COLS} FROM ledger_entries WHERE seq > %s ORDER BY seq LIMIT %s", (after_seq, limit))
    entries = [_entry(r) for r in rows]
    return _wrap({"after_seq": after_seq, "limit": limit, "count": len(entries),
                  "next_after_seq": entries[-1]["seq"] if len(entries) == limit else None,
                  "entries": entries, "spec_url": SPEC_URL})


def _anchor() -> dict[str, Any] | None:
    try:
        rows = _q("SELECT seq, entry_hash, anchored_at, commit_sha, commit_url, entries_path, status"
                  " FROM ledger_anchors WHERE status = 'ok' ORDER BY anchor_id DESC LIMIT 1")
    except Exception:  # noqa: BLE001 - table absent before migration 002
        return None
    if not rows:
        return {"status": "pending", "note": "hourly anchoring to the `ledger` branch starts in Stage 2 part 2"}
    a = rows[0]
    age_h = (datetime.now(UTC) - a["anchored_at"]).total_seconds() / 3600
    return {**{k: a[k] for k in ("seq", "entry_hash", "anchored_at", "commit_sha", "commit_url", "entries_path")},
            "status": "ok" if age_h <= 2 else "stale"}


@app.api_route("/v1/ledger/head", methods=["GET", "HEAD"])
def ledger_head() -> dict[str, Any]:
    """The newest ledger entry and the latest external anchor."""
    rows = _q(f"SELECT {_ENTRY_COLS} FROM ledger_entries ORDER BY seq DESC LIMIT 1")
    if not rows:
        raise HTTPException(404, "the ledger has no entries yet")
    r = rows[0]
    return _wrap({"seq": r["seq"], "entry_hash": r["entry_hash"], "created_at": r["created_at"],
                  "entry_type": r["entry_type"], "anchor": _anchor(), "spec_url": SPEC_URL})


@app.api_route("/v1/ledger/{seq}", methods=["GET", "HEAD"])
def ledger_entry(seq: int) -> dict[str, Any]:
    rows = _q(f"SELECT {_ENTRY_COLS} FROM ledger_entries WHERE seq = %s", (seq,))
    if not rows:
        raise HTTPException(404, f"no ledger entry {seq}")
    return _wrap({**_entry(rows[0]), "spec_url": SPEC_URL})


FORECAST_LABEL = "FloodLead baseline (persistence / trend), live skill being measured"


@app.api_route("/v1/stations/{station_id}/forecast", methods=["GET", "HEAD"])
def station_forecast(station_id: str) -> dict[str, Any]:
    """The latest FloodLead baseline forecast per model (as fixed in the ledger, with its seq and hash), plus the
    linked NOAA NWS official forecast's latest issuance, unmodified."""
    rows = _q("SELECT DISTINCT ON (model) seq, entry_hash, created_at, canonical FROM ledger_entries"
              " WHERE entry_type = 'forecast' AND station_id = %s AND base_time > now() - interval '3 days'"
              " ORDER BY model, base_time DESC", (station_id,))
    st = _q("SELECT links FROM stations WHERE station_id = %s", (station_id,))
    if not rows and not st:
        raise HTTPException(404, f"unknown station {station_id!r}")
    if not rows:
        raise HTTPException(404, f"no FloodLead forecast issued for {station_id} in the last 3 days")
    models = []
    for r in rows:
        d = json.loads(r["canonical"])["data"]
        models.append({"model": d["model"], "seq": r["seq"], "entry_hash": r["entry_hash"],
                       "created_at": r["created_at"], **{k: v for k, v in d.items() if k != "model"}})
    official = None
    lid = ((st[0]["links"] or {}) if st else {}).get("nwps_lid")
    if lid:
        pts = _q("SELECT issued_at, valid_at, stage_ft, flow_kcfs FROM official_forecasts WHERE lid = %(lid)s AND"
                 " issued_at = (SELECT max(issued_at) FROM official_forecasts WHERE lid = %(lid)s) ORDER BY valid_at",
                 {"lid": lid})
        if pts:
            official = {"lid": lid, "issued_at": pts[0]["issued_at"],
                        "label": "NOAA NWS official forecast (unmodified)",
                        "points": [{"valid_at": p["valid_at"], "stage_ft": p["stage_ft"], "flow_kcfs": p["flow_kcfs"]}
                                   for p in pts]}
    return _wrap({"station_id": station_id, "generated_at": datetime.now(UTC), "label": FORECAST_LABEL,
                  "models": models, "official": official, "spec_url": SPEC_URL})
