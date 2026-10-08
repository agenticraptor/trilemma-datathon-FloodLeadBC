"""Hourly issuance: forecasts for every live gauge, fixed in the ledger before the truth exists.

base_time = top of the current UTC hour; the scheduler starts the run at HH:15 (after the HH:01 Datamart
rewrite has landed). A run that starts more than 30 min after its base time is not issued; it is recorded as a
`gap`, as is any earlier base time that has no issuance. Forecasts are never backfilled.
"""

from __future__ import annotations

import hashlib
import json
import math
import resource
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import psycopg
from psycopg_pool import ConnectionPool

from floodlead import baselines as bl
from floodlead import ledger, log

L = log.get(__name__)

STEP = {"eccc": timedelta(minutes=5), "usgs": timedelta(minutes=15)}
STALE_LAG_MIN = {"eccc": 150, "usgs": 120}  # the sources' green lag thresholds in /v1/health
LIVE_WINDOW = timedelta(hours=3)
LATE_LIMIT = timedelta(minutes=30)
MIN_VALID_AFTER_CREATED = timedelta(minutes=30)
TRAILING = timedelta(days=30)
SEASON_HALF = timedelta(days=30)
RISES_M = (0.25, 0.5, 1.0)
MIN_LIBRARY = 50  # error paths needed to issue a station-model forecast

MODEL_CARDS = {
    "persistence-v1": {
        "method": "Point path: the level at data_as_of for every lead. Uncertainty: empirical error paths of the "
                  "same method on the station's own history (rows first seen before created_at), sampled across "
                  "past origins and indexed by lead from data_as_of; q, qmax and p_exceed come from point + error "
                  "samples.",
    },
    "trend3h-v1": {
        "method": "Point path: last observed level + least-squares slope over the 3 h ending at data_as_of "
                  "(>= 50 % of the window's grid points required, else the station is skipped for this model) "
                  "x min(lead, 6 h); the trend is held after 6 h. Uncertainty: empirical error paths of the same "
                  "method, as for persistence-v1.",
    },
}


def floor_hour(t: datetime) -> datetime:
    return t.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def params_hash(obj: Any) -> str:
    return hashlib.sha256(ledger.canonical_json(obj).encode()).hexdigest()


def card_data(model: str) -> dict[str, Any]:
    params = {"model": model, **bl.PARAMS, "stale_lag_min": STALE_LAG_MIN, "rises_m": list(RISES_M),
              "live_window_h": 3, "min_library": MIN_LIBRARY}
    return {"model": model, "method": MODEL_CARDS[model]["method"], "params": params,
            "params_hash": params_hash(params), "code_commit": ledger.code_commit()}


def input_hash(rows: list[tuple[datetime, float]]) -> str:
    return hashlib.sha256(ledger.canonical_json([[ledger.ts(t), ledger.r4(v)] for t, v in rows]).encode()).hexdigest()


def _rows(conn: psycopg.Connection, sid: str, t0: datetime, t1: datetime, created_at: datetime
          ) -> list[tuple[datetime, float]]:
    return conn.execute(
        "SELECT ts, value FROM observations WHERE station_id = %s AND param = 'level' AND NOT is_sentinel"
        " AND value IS NOT NULL AND ts BETWEEN %s AND %s AND ts <= %s AND first_seen_at <= %s ORDER BY ts",
        (sid, t0, t1, created_at, created_at)).fetchall()


def _thresholds(official: dict[str, Any], y_d: float) -> tuple[dict[str, float], list[dict[str, Any]]]:
    thr: dict[str, float] = {}
    meta: list[dict[str, Any]] = []
    for name in ("action", "minor", "moderate", "major"):
        c = (official.get("categories") or {}).get(name)
        if c and c.get("stage_m") is not None:
            key = f"official:{name}"
            thr[key] = float(c["stage_m"])
            meta.append({"key": key, "kind": "official", "level_m": ledger.r4(c["stage_m"]),
                         "level_ft": c.get("stage_ft"), "label": f"NWS {name} flood stage",
                         "source": f"NOAA NWS NWPS {official.get('lid')}"})
    for r in RISES_M:
        key = f"rise:+{r}"
        thr[key] = y_d + r
        meta.append({"key": key, "kind": "rise", "level_m": ledger.r4(y_d + r),
                     "label": f"+{r} m above the level at data time"})
    return thr, meta


def forecast_station(conn: psycopg.Connection, sid: str, data_as_of: datetime, base: datetime, created_at: datetime,
                     official: dict[str, Any], skipped: dict[str, int]) -> list[ledger.Pending]:
    src = sid.split(":", 1)[0]
    step = STEP[src]
    start = data_as_of - TRAILING
    rows = _rows(conn, sid, start, data_as_of, created_at)
    g = bl.to_grid(rows, step, start=start, end=data_as_of)
    d_idx = len(g.y) - 1
    y_d = float(g.y[d_idx])
    window_pts = int(bl.TREND_WINDOW / step)
    cap_pts = int(bl.TREND_CAP / step)
    max_lead_pts = math.ceil(bl.MAX_LEAD / step)
    ffill_pts = int(bl.FFILL_LIMIT / step)
    inputs = [(t, v) for t, v in rows if t >= data_as_of - bl.TREND_WINDOW]
    slope_d = float(bl.slopes(g.y, np.array([d_idx]), window_pts, bl.TREND_MIN_COVERAGE)[0])

    # Horizons: valid_at = base + h; lead counted from data_as_of; drop if valid_at - created_at < 30 min.
    horizons = []
    for h in bl.HORIZONS_H:
        valid_at = base + timedelta(hours=h)
        if valid_at - created_at < MIN_VALID_AFTER_CREATED:
            continue
        lead = int(round((valid_at - data_as_of) / step))
        if 1 <= lead <= max_lead_pts:
            horizons.append((h, valid_at, lead))

    # Error-path libraries (trailing 30 days; USGS adds the same season in prior years).
    hourly = int(timedelta(hours=1) / step)
    seasonal: list[tuple[bl.Grid, np.ndarray]] = []
    if src == "usgs":
        for years_back in range(1, 30):
            centre = data_as_of.replace(year=data_as_of.year - years_back) if not (
                data_as_of.month == 2 and data_as_of.day == 29) else data_as_of - timedelta(days=365 * years_back)
            s0, s1 = centre - SEASON_HALF - bl.TREND_WINDOW, centre + SEASON_HALF + bl.MAX_LEAD
            yr = _rows(conn, sid, s0, s1, created_at)
            if len(yr) < 100:
                continue
            gy = bl.to_grid(yr, step, start=s0, end=s1)
            seasonal.append((gy, np.arange(window_pts, len(gy.y), 3 * hourly)))
    thr, thr_meta = _thresholds(official, y_d)
    stale = (created_at - data_as_of) > timedelta(minutes=STALE_LAG_MIN[src])
    out: list[ledger.Pending] = []
    for model in bl.MODELS:
        if model == "trend3h-v1" and math.isnan(slope_d):
            skipped["trend3h-v1: < 50 % coverage of the 3 h window"] = skipped.get(
                "trend3h-v1: < 50 % coverage of the 3 h window", 0) + 1
            continue
        origins = np.arange(window_pts, d_idx - max_lead_pts + 1, hourly)
        E, used = bl.error_paths(model, g, origins, max_lead_pts, window_pts, cap_pts, ffill_pts)
        times = [g.time(int(i)) for i in used]
        parts = [E]
        for gy, oy in seasonal:
            Ey, uy = bl.error_paths(model, gy, oy, max_lead_pts, window_pts, cap_pts, ffill_pts)
            parts.append(Ey)
            times += [gy.time(int(i)) for i in uy]
        E = np.vstack(parts) if len(parts) > 1 else E
        if len(E) < MIN_LIBRARY:
            k = f"{model}: error library < {MIN_LIBRARY} paths"
            skipped[k] = skipped.get(k, 0) + 1
            continue
        pp = bl.point_path(model, y_d, 0.0 if math.isnan(slope_d) else slope_d,
                           np.arange(1, max_lead_pts + 1), cap_pts)
        samples = pp[None, :] + E
        summ = bl.summarise(samples, [lead for _, _, lead in horizons], thr)
        hz = []
        for (h, valid_at, _lead), (q, qm, pe) in zip(horizons, summ, strict=True):
            hz.append({"h": h, "valid_at": ledger.ts(valid_at),
                       "q": {k: ledger.r4(v) for k, v in q.items()},
                       "qmax": {k: ledger.r4(v) for k, v in qm.items()},
                       "p_exceed": {k: ledger.r4(v) for k, v in pe.items()}})
        data = {
            "station_id": sid, "model": model, "base_time": ledger.ts(base), "data_as_of": ledger.ts(data_as_of),
            "input_age_min": round((created_at - data_as_of).total_seconds() / 60, 1), "stale_inputs": stale,
            "level_at_data_as_of_m": ledger.r4(y_d), "units": "m",
            "trend_slope_m_per_h": ledger.r4(slope_d * hourly) if model == "trend3h-v1" else None,
            "input_hash": input_hash(inputs), "inputs_n": len(inputs),
            "error_library": {"hash": bl.library_hash(model, sid, E, times), "paths": int(len(E)),
                              "definition": bl.PARAMS["library"][src]},
            "thresholds": thr_meta, "horizons": hz,
        }
        out.append(ledger.Pending("forecast", data, created_at, station_id=sid, model=model, base_time=base))
    return out


def run(pool: ConnectionPool, now: datetime | None = None, dry_run: bool = False) -> dict[str, Any]:
    t0 = time.monotonic()
    created_at = now or datetime.now(UTC)
    base = floor_hour(created_at)
    with pool.connection() as conn:
        conn.autocommit = True
        if conn.execute("SELECT 1 FROM ledger_entries WHERE entry_type IN ('issuance', 'gap') AND base_time = %s",
                        (base,)).fetchone():
            L.info("issuance exists for base time; nothing to do", **log.kv(base_time=ledger.ts(base)))
            return {"status": "exists", "base_time": ledger.ts(base)}
        late = created_at - base > LATE_LIMIT
        pend: list[ledger.Pending] = []
        skipped: dict[str, int] = {}
        stations_live: list[tuple[str, datetime]] = []
        if not late or dry_run:  # a dry run computes even when late (it writes nothing)
            stations_live = conn.execute(
                "SELECT station_id, max(ts) FROM observations WHERE param = 'level' AND NOT is_sentinel"
                " AND value IS NOT NULL AND ts > %s AND ts <= %s AND first_seen_at <= %s GROUP BY station_id"
                " ORDER BY station_id", (created_at - LIVE_WINDOW, created_at, created_at)).fetchall()
            n_level = conn.execute("SELECT count(*) FROM stations WHERE 'level' = ANY(params)").fetchone()[0]
            skipped["no level observation in the last 3 h"] = max(0, n_level - len(stations_live))
            official = {sid: thr for sid, thr in conn.execute(
                "SELECT station_id, official_thresholds FROM stations WHERE official_thresholds <> '{}'::jsonb")}
            for sid, data_as_of in stations_live:
                try:
                    pend += forecast_station(conn, sid, data_as_of, base, created_at, official.get(sid, {}), skipped)
                except Exception as e:  # noqa: BLE001 - one station never stops the run
                    k = f"error: {type(e).__name__}"
                    skipped[k] = skipped.get(k, 0) + 1
                    L.exception("forecast failed", **log.kv(station_id=sid))
        runtime = time.monotonic() - t0
        peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        if dry_run:
            counts_d: dict[str, int] = {}
            for p in pend:
                counts_d[p.model or ""] = counts_d.get(p.model or "", 0) + 1
            sample = next((p.data for p in pend if p.station_id == "usgs:12210700"), pend[0].data if pend else None)
            return {"status": "dry-run", "base_time": ledger.ts(base), "late": late, "forecasts": counts_d,
                    "skipped": skipped, "runtime_s": round(runtime, 1), "peak_rss_mb": round(peak_mb, 1),
                    "bytes_per_forecast": round(sum(len(ledger.canonical_json(p.data)) for p in pend)
                                                / max(1, len(pend))),
                    "sample": sample}
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (ledger.LOCK_KEY,))
            if conn.execute("SELECT 1 FROM ledger_entries WHERE entry_type IN ('issuance', 'gap')"
                            " AND base_time = %s", (base,)).fetchone():
                return {"status": "exists", "base_time": ledger.ts(base)}
            head: list[ledger.Pending] = []
            # Model cards: a new card whenever a model's parameters change (or on first use).
            for model in bl.MODELS:
                card = card_data(model)
                last = conn.execute("SELECT canonical FROM ledger_entries WHERE entry_type = 'model_card'"
                                    " AND model = %s ORDER BY seq DESC LIMIT 1", (model,)).fetchone()
                if last is None or json.loads(last[0])["data"]["params_hash"] != card["params_hash"]:
                    head.append(ledger.Pending("model_card", card, created_at, model=model))
            # Gaps: every base time after the last issuance/gap that has neither.
            last_base = conn.execute("SELECT max(base_time) FROM ledger_entries WHERE entry_type IN"
                                     " ('issuance', 'gap')").fetchone()[0]
            if last_base is not None:
                t = last_base + timedelta(hours=1)
                while t < base:
                    head.append(ledger.Pending("gap", {"base_time": ledger.ts(t), "detected_at": ledger.ts(created_at),
                                                       "reason": "no issuance run within 30 min of the base time"},
                                               created_at, base_time=t))
                    t += timedelta(hours=1)
            if late:
                if last_base is None:  # the ledger has not started issuing yet: nothing to record
                    return {"status": "late-before-first-issuance", "base_time": ledger.ts(base)}
                late_min = round((created_at - base).total_seconds() / 60)
                reason = f"run started {late_min} min after the base time (limit 30)"
                head.append(ledger.Pending("gap", {"base_time": ledger.ts(base), "detected_at": ledger.ts(created_at),
                                                   "reason": reason}, created_at, base_time=base))
                written = ledger.append(conn, head)
                return {"status": "gap", "base_time": ledger.ts(base), "entries": len(written)}
            written = ledger.append(conn, head + pend)
            fseqs = [e.seq for e in written if e.entry_type == "forecast"]
            counts: dict[str, int] = {}
            for p in pend:
                counts[p.model or ""] = counts.get(p.model or "", 0) + 1
            issuance = {
                "base_time": ledger.ts(base), "models": list(bl.MODELS), "horizons_h": list(bl.HORIZONS_H),
                "stations_with_recent_level": len(stations_live), "forecasts": counts,
                "forecast_seq": [fseqs[0], fseqs[-1]] if fseqs else None, "skipped": skipped,
                "runtime_s": round(runtime, 1), "peak_rss_mb": round(peak_mb, 1), "code_commit": ledger.code_commit(),
            }
            written += ledger.append(conn, [ledger.Pending("issuance", issuance, created_at, base_time=base)])
        L.info("issuance written", **log.kv(base_time=ledger.ts(base), entries=len(written), forecasts=counts,
                                            skipped=skipped, runtime_s=round(runtime, 1),
                                            peak_rss_mb=round(peak_mb, 1)))
        return {"status": "issued", "base_time": ledger.ts(base), "entries": len(written), "forecasts": counts,
                "skipped": skipped, "runtime_s": round(runtime, 1)}
