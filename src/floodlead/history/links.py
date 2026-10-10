"""Upstream links and typical travel times from the history (Stage 3 part 2 item 4; D-03.14).

For each (upstream, target) pair, on hourly mean levels (reads use constant time bounds per water year, F3):
- rise correlation: Pearson correlation of 1-hour level rises, upstream at t and target at t + lag, for lags 0-36 h,
  in Oct-Mar; the lag with the highest correlation is reported with that correlation and the n of hour pairs;
- peak-to-peak: for every target event (an hourly peak above the target's 95th percentile, events at least 72 h
  apart), the upstream maximum in the 48 h before the target peak; median lag with the IQR and n.
Daily (BC history) pairs use daily means and lags 0-3 days; sub-daily travel times cannot be resolved from them.
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import psycopg

NOOKSACK_TARGET = "usgs:12210700"
NOOKSACK_PAIRS = (
    ("usgs:12205000", NOOKSACK_TARGET, "North Fork below Cascade Creek near Glacier → North Cedarville"),
    ("usgs:12208000", NOOKSACK_TARGET, "Middle Fork near Deming → North Cedarville"),
    ("usgs:12210000", NOOKSACK_TARGET, "South Fork at Saxon Bridge → North Cedarville"),
    (NOOKSACK_TARGET, "usgs:12211200", "North Cedarville → Everson"),
    (NOOKSACK_TARGET, "usgs:12213100", "North Cedarville → Ferndale"),
)


def hourly(conn: psycopg.Connection, sid: str, t0: datetime, t1: datetime) -> dict[datetime, float]:
    out: dict[datetime, float] = {}
    y = t0
    while y < t1:
        y1 = min(y + timedelta(days=366), t1)
        for h, v in conn.execute(
                "SELECT date_trunc('hour', ts), avg(value) FROM observations WHERE station_id = %s AND param = 'level'"
                " AND NOT is_sentinel AND value IS NOT NULL AND ts >= %s AND ts < %s GROUP BY 1", (sid, y, y1)):
            out[h] = float(v)
        y = y1
    return out


def _grid(series: dict[datetime, float], t0: datetime, n: int, step: timedelta) -> np.ndarray:
    a = np.full(n, np.nan)
    for t, v in series.items():
        i = int((t - t0) / step)
        if 0 <= i < n:
            a[i] = v
    return a


def rise_correlation(up: np.ndarray, down: np.ndarray, months: np.ndarray, max_lag: int, step_h: float = 1.0,
                     wet: tuple[int, ...] = (10, 11, 12, 1, 2, 3)) -> dict[str, Any]:
    du, dd = np.diff(up), np.diff(down)
    wet_mask = np.isin(months[1:], wet)
    best: dict[str, Any] = {"lag_h": None, "r": None, "n": 0}
    for lag in range(0, max_lag + 1):
        a = du[: len(du) - lag] if lag else du
        b = dd[lag:]
        m = wet_mask[: len(a)] & np.isfinite(a) & np.isfinite(b)
        if m.sum() < 200:
            continue
        r = float(np.corrcoef(a[m], b[m])[0, 1])
        if best["r"] is None or r > best["r"]:
            best = {"lag_h": lag * step_h, "r": round(r, 3), "n": int(m.sum())}
    return best


def peak_lags(up: np.ndarray, down: np.ndarray, window: int, sep: int, step_h: float = 1.0) -> dict[str, Any]:
    fin = down[np.isfinite(down)]
    if len(fin) == 0:
        return {"n": 0}
    thr = float(np.percentile(fin, 95))
    order = np.argsort(-np.nan_to_num(down, nan=-np.inf))
    taken: list[int] = []
    lags: list[float] = []
    for i in order:
        if not np.isfinite(down[i]) or down[i] < thr:
            break
        if any(abs(int(i) - j) < sep for j in taken):
            continue
        taken.append(int(i))
        w = up[max(0, i - window): i + 1]
        if np.isfinite(w).sum() < window * 0.8:
            continue
        lags.append((len(w) - 1 - int(np.nanargmax(w))) * step_h)
    if not lags:
        return {"n": 0, "threshold": round(thr, 3)}
    q = statistics.quantiles(lags, n=4) if len(lags) >= 4 else [min(lags), statistics.median(lags), max(lags)]
    return {"n": len(lags), "median_h": statistics.median(lags), "iqr_h": [q[0], q[-1]], "threshold": round(thr, 3)}


def nooksack(conn: psycopg.Connection, t0: datetime = datetime(2004, 10, 1, tzinfo=UTC),
             t1: datetime | None = None) -> list[dict[str, Any]]:
    t1 = t1 or datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    conn.execute("SET statement_timeout = '15min'")
    step = timedelta(hours=1)
    n = int((t1 - t0) / step)
    months = np.array([(t0 + i * step).month for i in range(n)])
    cache: dict[str, np.ndarray] = {}
    out = []
    for up_id, down_id, label in NOOKSACK_PAIRS:
        for sid in (up_id, down_id):
            if sid not in cache:
                cache[sid] = _grid(hourly(conn, sid, t0, t1), t0, n, step)
        up, down = cache[up_id], cache[down_id]
        out.append({"upstream": up_id, "target": down_id, "label": label, "resolution": "hourly",
                    "period": [t0.date().isoformat(), t1.date().isoformat()],
                    "rise_correlation": rise_correlation(up, down, months, 36),
                    "peak_to_peak": peak_lags(up, down, window=48, sep=72),
                    "source": "USGS 15-min levels (approved and provisional), hourly means; this repository's history"})
    return out


BC_PAIRS = (
    ("eccc:08MH016", "eccc:08MH001", "Chilliwack R. at outlet of Chilliwack Lake → Vedder Crossing"),
    ("eccc:08MH103", "eccc:08MH001", "Chilliwack R. above Slesse Ck → Vedder Crossing"),
    ("eccc:08MH056", "eccc:08MH001", "Slesse Ck near Vedder Crossing → Chilliwack R. at Vedder Crossing"),
    ("usgs:12214500", "eccc:08MH029", "Sumas R. near Sumas, WA (USGS) → Sumas R. near Huntingdon, BC"),
    ("usgs:12210700", "eccc:08MH029", "Nooksack at North Cedarville (overflow source) → Sumas R. near Huntingdon"),
    ("eccc:08MF040", "eccc:08MF005", "Fraser R. above Texas Creek → Fraser R. at Hope"),
    ("eccc:08LF051", "eccc:08MF005", "Thompson R. near Spences Bridge → Fraser R. at Hope"),
    ("eccc:08MF005", "eccc:08MH024", "Fraser R. at Hope → Fraser R. at Mission (tidal)"),
    ("eccc:08MF068", "eccc:08MF062", "Coquihalla R. above Alexander Ck → below Needle Ck"),
)


def daily(conn: psycopg.Connection, sid: str, t0: datetime, t1: datetime) -> dict[datetime, float]:
    if sid.startswith("eccc:"):
        return {datetime(d.year, d.month, d.day, tzinfo=UTC): float(v) for d, v in conn.execute(
            "SELECT date, level FROM eccc_daily WHERE station_number = %s AND level IS NOT NULL AND date >= %s"
            " AND date < %s", (sid.split(":", 1)[1], t0.date(), t1.date()))}
    out: dict[datetime, list[float]] = {}
    for h, v in hourly(conn, sid, t0, t1).items():
        out.setdefault(h.replace(hour=0), []).append(v)
    return {d: sum(v) / len(v) for d, v in out.items() if len(v) >= 18}


def bc(conn: psycopg.Connection, t0: datetime = datetime(1990, 1, 1, tzinfo=UTC),
       t1: datetime = datetime(2025, 1, 1, tzinfo=UTC)) -> list[dict[str, Any]]:
    conn.execute("SET statement_timeout = '15min'")
    step = timedelta(days=1)
    n = int((t1 - t0) / step)
    months = np.array([(t0 + i * step).month for i in range(n)])
    out = []
    for up_id, down_id, label in BC_PAIRS:
        up = _grid(daily(conn, up_id, t0, t1), t0, n, step)
        down = _grid(daily(conn, down_id, t0, t1), t0, n, step)
        both = np.isfinite(up) & np.isfinite(down)
        span = None
        if both.any():
            idx = np.flatnonzero(both)
            span = [(t0 + int(idx[0]) * step).date().isoformat(), (t0 + int(idx[-1]) * step).date().isoformat()]
        out.append({"upstream": up_id, "target": down_id, "label": label, "resolution": "daily",
                    "overlap": span, "overlap_days": int(both.sum()),
                    "rise_correlation": rise_correlation(up, down, months, 3, step_h=24.0,
                                                         wet=tuple(range(1, 13))),
                    "peak_to_peak": peak_lags(up, down, window=3, sep=5, step_h=24.0),
                    "source": "ECCC daily means (HYDAT, to 2024); USGS hourly means aggregated to days",
                    "note": "daily resolution: lags under a day cannot be resolved"})
    return out
