"""Leakage-safe training sets for Stage 4 (Stage 3 part 2 item 5; D-03.17).

Nooksack, hourly issue times t (on the hour, UTC), 2004-10-01 to 48 h before the build:
- every feature uses only data a live forecast at t could have seen: each source is cut at t - its latency (LATENCY)
  and the `*_asof` columns record the newest source timestamp used, which the leakage test checks;
- targets are North Cedarville's level at t + 1 ... 48 h and threshold crossings / overflow onset in (t, t + H];
- two variants, never mixed: `honest` (past observations; as-issued forecast rain only where it exists, from
  2024-01-19) and `oracle` (adds future *observed* reanalysis rain in (t, t + H]: an upper bound, always labelled);
- NWS-derived comparators at t: the latest North Cedarville warning product in force, its forecast crest and the
  0/1 "probabilities" crest >= 148 ft / >= 150 ft;
- `wy` (water year, Oct-Sep) and `holdout` (WY2022 = Nov 2021 flood, WY2026 = Dec 2025 flood; untouched until the single
  final Stage 4 run). History values are USGS-approved data, revised after the fact, not what was visible live;
  rows carry `data_status` = 'approved history' or 'provisional (live archive)'.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import math
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import psycopg

STEP = timedelta(minutes=15)
HOUR = timedelta(hours=1)
FT = {"action": 144.8, "minor": 146.5, "moderate": 148.0, "major": 150.0}
GAUGES = {"nc": "usgs:12210700", "nf": "usgs:12205000", "mf": "usgs:12208000", "sf": "usgs:12210000",
          "everson": "usgs:12211200", "ferndale": "usgs:12213100"}
OVERFLOW = "usgs:12211195"
OVERFLOW_CONTINUOUS_FROM = datetime(2026, 10, 1, tzinfo=UTC)
OVERFLOW_BEGINS = datetime(2015, 11, 14, tzinfo=UTC)
SNOTEL_SITES = ("909:WA:SNTL", "910:WA:SNTL", "1011:WA:SNTL")
KBLI = "72797624217"
NOOKSACK_POINTS = ("nooksack-nf", "nooksack-mf", "nooksack-sf", "nooksack-lower")
PREVRUNS_FROM = datetime(2024, 1, 19, tzinfo=UTC)
# Publication latency per source (minutes). USGS: newest value 14-52 min old (Stage 1); SNOTEL: ~40 min in the first
# probe, 120 used until the overnight probes are summarised; KBLI: hourly METAR, live within minutes via NWS (20 used).
LATENCY = {"usgs": 60, "snotel": 120, "kbli": 20}
# As-issued forecast rain (Open-Meteo previous runs): a day-1 value for valid hour v was issued about 24 h before v
# (plus run availability); usable at t only for v <= t + 18 h. Day-2 values: v <= t + 42 h.
DAY1_MAX_H, DAY2_MAX_H = 18, 42
HOLDOUT_WY = (2022, 2026)
H_LEVEL = tuple(range(1, 49))
H_CROSS = (6, 12, 24, 48)
H_OVERFLOW = (6, 12, 24)


def wy(t: datetime) -> int:
    return t.year + 1 if t.month >= 10 else t.year


@dataclass
class Grid:
    t0: datetime
    step: timedelta
    v: np.ndarray

    def idx(self, t: datetime) -> int:
        return int((t - self.t0) / self.step)

    def last_at_or_before(self, t: datetime, max_age: timedelta) -> tuple[float, datetime | None]:
        i = self.idx(t)
        n = int(max_age / self.step)  # the cell containing t, then n earlier cells
        for k in range(i, max(i - n - 1, -1), -1):
            if 0 <= k < len(self.v) and not math.isnan(self.v[k]):
                return float(self.v[k]), self.t0 + k * self.step
        return math.nan, None

    def window(self, a: datetime, b: datetime) -> np.ndarray:
        """Values with timestamps in (a, b]."""
        i, j = self.idx(a) + 1, self.idx(b) + 1
        return self.v[max(i, 0): max(j, 0)]


def grid_from(rows: Iterator[tuple[datetime, float]], t0: datetime, t1: datetime, step: timedelta) -> Grid:
    n = int((t1 - t0) / step) + 1
    a = np.full(n, np.nan)
    for t, v in rows:
        k = int((t - t0) / step)
        if 0 <= k < n and v is not None:
            a[k] = v
    return Grid(t0, step, a)


def _nansum(a: np.ndarray, min_frac: float = 0.8) -> float:
    fin = np.isfinite(a)
    if len(a) == 0 or fin.mean() < min_frac:
        return math.nan
    return float(np.nansum(a))


def _nanmax(a: np.ndarray) -> float:
    return float(np.nanmax(a)) if np.isfinite(a).any() else math.nan


def _first_true_h(a: np.ndarray, step_h: float) -> float:
    k = np.flatnonzero(a)
    return float((k[0] + 1) * step_h) if len(k) else math.nan


@dataclass
class Inputs:
    gauges: dict[str, Grid]          # 15-min stage (ft) per gauge key
    overflow: Grid                   # 15-min SR 544 stage (ft)
    snotel: dict[str, Grid]          # hourly (hour ending) per site: precip mm
    snotel_swe: dict[str, Grid]
    kbli: Grid                       # hourly precip mm (hour ending)
    prev_day1: Grid                  # hourly basin-mean as-issued forecast precip (day 1), by valid hour
    prev_day2: Grid
    era5: Grid                       # hourly basin-mean reanalysis precip (oracle only)
    nws: list[dict[str, Any]]        # NRKW1 FL.W products: issued_at, end, action, severity, crest_ft, event
    live_from: datetime              # from here the gauge values are provisional live-archive values


def nws_in_force(products: list[dict[str, Any]], t: datetime) -> dict[str, Any] | None:
    """The latest NRKW1 flood-warning product issued at or before t whose event is still in force at t."""
    latest: dict[Any, dict[str, Any]] = {}
    for p in products:
        if p["issued_at"] > t:
            break
        latest[p["event"]] = p
    live = [p for p in latest.values() if p["action"] not in ("CAN", "EXP") and (p["end"] is None or p["end"] > t)]
    return max(live, key=lambda p: p["issued_at"]) if live else None


def row(inp: Inputs, t: datetime, oracle: bool) -> dict[str, Any]:
    r: dict[str, Any] = {"issue_time": t, "wy": wy(t), "holdout": wy(t) in HOLDOUT_WY,
                         "variant": "oracle" if oracle else "honest",
                         "data_status": "provisional (live archive)" if t >= inp.live_from else "approved history"}
    cu = t - timedelta(minutes=LATENCY["usgs"])
    newest: datetime | None = None
    for k, g in inp.gauges.items():
        lvl, at = g.last_at_or_before(cu, timedelta(hours=2))
        r[f"{k}_lvl"] = lvl
        for dh in (1, 3, 6, 12):
            prev, _ = g.last_at_or_before(cu - timedelta(hours=dh), timedelta(minutes=30))
            r[f"{k}_d{dh}h"] = lvl - prev if not (math.isnan(lvl) or math.isnan(prev)) else math.nan
        r[f"{k}_max24h"] = _nanmax(g.window(cu - timedelta(hours=24), cu))
        if at is not None and (newest is None or at > newest):
            newest = at
    nc = inp.gauges["nc"]
    r["nc_mean7d"] = float(np.nanmean(w)) if np.isfinite(w := nc.window(cu - timedelta(days=7), cu)).any() else math.nan
    r["nc_mean30d"] = (float(np.nanmean(w)) if np.isfinite(w := nc.window(cu - timedelta(days=30), cu)).any()
                       else math.nan)
    r["asof_usgs"] = newest
    ov_lvl, ov_at = inp.overflow.last_at_or_before(cu, timedelta(hours=2))
    r["overflow_lvl"] = ov_lvl
    r["overflow_flowing"] = (ov_at is not None and (ov_at < OVERFLOW_CONTINUOUS_FROM or ov_lvl >= 3.6)) \
        if t >= OVERFLOW_BEGINS else math.nan
    if ov_at is not None and (newest is None or ov_at > newest):
        r["asof_usgs"] = ov_at
    # SNOTEL (hour-ending values at or before the cut-off)
    cs = t - timedelta(minutes=LATENCY["snotel"])
    cs_h = cs.replace(minute=0, second=0, microsecond=0)
    for hh in (1, 3, 6, 12, 24, 48, 72):
        vals = [_nansum(g.window(cs_h - timedelta(hours=hh), cs_h)) for g in inp.snotel.values()]
        fin = [v for v in vals if not math.isnan(v)]
        r[f"snotel_p{hh}h"] = sum(fin) / len(fin) if fin else math.nan
    swe = [g.last_at_or_before(cs_h, timedelta(hours=3)) for g in inp.snotel_swe.values()]
    swe24 = [g.last_at_or_before(cs_h - timedelta(hours=24), timedelta(hours=3)) for g in inp.snotel_swe.values()]
    fin = [(a[0], b[0]) for a, b in zip(swe, swe24, strict=True) if not (math.isnan(a[0]) or math.isnan(b[0]))]
    r["snotel_swe_mm"] = sum(a for a, _ in fin) / len(fin) if fin else math.nan
    r["snotel_swe_d24h"] = sum(a - b for a, b in fin) / len(fin) if fin else math.nan
    r["asof_snotel"] = max((a[1] for a in swe if a[1] is not None), default=None)
    # KBLI hourly precipitation
    ck = (t - timedelta(minutes=LATENCY["kbli"])).replace(minute=0, second=0, microsecond=0)
    for hh in (1, 3, 6, 24, 72):
        r[f"kbli_p{hh}h"] = _nansum(inp.kbli.window(ck - timedelta(hours=hh), ck))
    r["asof_kbli"] = ck
    # As-issued forecast rain (honest): only valid hours the forecast had been issued for by t
    if t >= PREVRUNS_FROM:
        r["fc_rain_0_18h"] = _nansum(inp.prev_day1.window(t, t + timedelta(hours=DAY1_MAX_H)))
        r["fc_rain_18_42h"] = _nansum(inp.prev_day2.window(t + timedelta(hours=DAY1_MAX_H),
                                                           t + timedelta(hours=DAY2_MAX_H)))
    else:
        r["fc_rain_0_18h"] = r["fc_rain_18_42h"] = math.nan
    doy = t.timetuple().tm_yday
    r["doy_sin"], r["doy_cos"] = math.sin(2 * math.pi * doy / 365.25), math.cos(2 * math.pi * doy / 365.25)
    # NWS comparator in force at t (issued_at <= t: no latency beyond issuance)
    p = nws_in_force(inp.nws, t)
    r["nws_in_force"] = p is not None
    r["nws_issued_at"] = p["issued_at"] if p else None
    r["nws_crest_ft"] = p["crest_ft"] if p else math.nan
    r["nws_severity"] = p["severity"] if p else None
    crest = p["crest_ft"] if p and p["crest_ft"] is not None else None
    r["nws_p_ge_148"] = 1.0 if crest is not None and crest >= 148.0 else 0.0
    r["nws_p_ge_150"] = 1.0 if crest is not None and crest >= 150.0 else 0.0
    if oracle:
        for hh in (6, 12, 24, 48):
            r[f"oracle_future_rain_{hh}h"] = _nansum(inp.era5.window(t, t + timedelta(hours=hh)))
    # Targets (North Cedarville 15-min stage after t)
    for h in H_LEVEL:
        v, at = nc.last_at_or_before(t + timedelta(hours=h), timedelta(minutes=10))
        r[f"y_lvl_h{h}"] = v
    for name in ("minor", "moderate", "major"):
        for hh in H_CROSS:
            mx = _nanmax(nc.window(t, t + timedelta(hours=hh)))
            r[f"y_{name}_{hh}h"] = math.nan if math.isnan(mx) else float(mx >= FT[name])
    if t >= OVERFLOW_BEGINS:
        w = inp.overflow.window(t, t + timedelta(hours=max(H_OVERFLOW)))
        times = [t + (k + 1) * STEP for k in range(len(w))]
        flow = np.array([(not math.isnan(v)) and (tt < OVERFLOW_CONTINUOUS_FROM or v >= 3.6)
                         for v, tt in zip(w, times, strict=True)])
        already = r["overflow_flowing"] is True
        r["y_overflow_onset_h"] = math.nan if already else _first_true_h(flow, 0.25)
        for hh in H_OVERFLOW:
            r[f"y_overflow_{hh}h"] = math.nan if already else float(flow[: hh * 4].any())
    else:
        r["y_overflow_onset_h"] = math.nan
        for hh in H_OVERFLOW:
            r[f"y_overflow_{hh}h"] = math.nan
    return r


def issue_times(t0: datetime, t1: datetime) -> Iterator[datetime]:
    t = t0
    while t <= t1:
        yield t
        t += HOUR


def load_inputs(conn: psycopg.Connection, t0: datetime, t1: datetime) -> Inputs:
    """Read every input once, with constant time bounds per year on the observations hypertable (F3)."""
    conn.execute("SET statement_timeout = '30min'")

    def usgs(sid: str) -> Grid:
        rows: list[tuple[datetime, float]] = []
        a = t0 - timedelta(days=31)
        while a < t1:
            b = min(a + timedelta(days=366), t1)
            rows += conn.execute(
                "SELECT ts, raw_value FROM observations WHERE station_id = %s AND param = 'level'"
                " AND NOT is_sentinel AND raw_value IS NOT NULL AND ts > %s AND ts <= %s", (sid, a, b)).fetchall()
            a = b
        return grid_from(iter(rows), t0 - timedelta(days=31), t1, STEP)

    def hourly(sql: str, params: tuple) -> Grid:
        return grid_from(iter(conn.execute(sql, params).fetchall()), t0 - timedelta(days=31), t1, HOUR)

    gauges = {k: usgs(sid) for k, sid in GAUGES.items()}
    overflow = usgs(OVERFLOW)
    sn = {s: hourly("SELECT ts, precip_mm FROM rain_hourly WHERE source = 'snotel' AND site = %s AND ts > %s"
                    " AND ts <= %s", (s, t0 - timedelta(days=31), t1)) for s in SNOTEL_SITES}
    swe = {s: hourly("SELECT ts, swe_mm FROM rain_hourly WHERE source = 'snotel' AND site = %s AND ts > %s"
                     " AND ts <= %s", (s, t0 - timedelta(days=31), t1)) for s in SNOTEL_SITES}
    kbli = hourly("SELECT ts, precip_mm FROM rain_hourly WHERE source = 'ncei' AND site = %s AND ts > %s AND ts <= %s",
                  (KBLI, t0 - timedelta(days=31), t1))

    def basin(col: str, kind: str) -> Grid:
        return hourly(f"SELECT ts, avg({col}) FROM openmeteo_hourly WHERE kind = %s AND point = ANY(%s) AND ts > %s"
                      f" AND ts <= %s AND {col} IS NOT NULL GROUP BY ts HAVING count(*) = %s",
                      (kind, list(NOOKSACK_POINTS), t0 - timedelta(days=31), t1 + timedelta(days=3),
                       len(NOOKSACK_POINTS)))

    nws = [{"issued_at": i, "end": e, "action": a, "severity": s, "crest_ft": c, "event": (etn, wy(i))}
           for i, e, a, s, c, etn in conn.execute(
               "SELECT issued_at, vtec_end, action, severity, forecast_crest_ft, etn FROM nws_vtec"
               " WHERE nwsli = 'NRKW1' AND phenomena = 'FL' AND significance = 'W' ORDER BY issued_at").fetchall()]
    live_from = conn.execute("SELECT min(first_seen_at) FROM observations WHERE station_id = %s AND ts > %s",
                             (GAUGES["nc"], datetime(2026, 9, 1, tzinfo=UTC))).fetchone()[0]
    return Inputs(gauges, overflow, sn, swe, kbli, basin("precip_prev_day1_mm", "prevruns"),
                  basin("precip_prev_day2_mm", "prevruns"), basin("precip_mm", "archive"), nws,
                  live_from or datetime(2026, 10, 7, tzinfo=UTC))


def write(inp: Inputs, out_dir: Path, t0: datetime, t1: datetime) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {}
    for variant in ("honest", "oracle"):
        path = out_dir / f"nooksack_hourly_{variant}_v1.csv.gz"
        n = 0
        cols: list[str] | None = None
        with gzip.open(path, "wt", newline="", compresslevel=6) as fh:
            w = None
            for t in issue_times(t0, t1):
                r = row(inp, t, oracle=variant == "oracle")
                if w is None:
                    cols = list(r)
                    w = csv.DictWriter(fh, fieldnames=cols)
                    w.writeheader()
                w.writerow({k: ("" if v is None or (isinstance(v, float) and math.isnan(v)) else
                                v.strftime("%Y-%m-%dT%H:%M:%SZ") if isinstance(v, datetime) else v)
                            for k, v in r.items()})
                n += 1
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest[variant] = {"file": path.name, "rows": n, "columns": len(cols or []), "bytes": path.stat().st_size,
                             "sha256": sha, "label": "UPPER BOUND: uses future observed rain" if variant == "oracle"
                             else "honest: only information available at issue time"}
    return manifest


# Fraser Valley (BC) daily dataset: ECCC daily means (HYDAT, approved, to 2024). Issue at the end of day d, using days
# <= d (daily means are published after the day ends; in live use the day's provisional mean is known the next
# morning, so a day-d issue is made early on d+1). Targets: daily mean level on d+1..d+3 and whether any of them
# reaches the station's typical yearly peak (typical-peak-v1). Rain: daily sums at Hope (1113542/1113543) and Pitt
# Meadows (1106178), where reported; the oracle variant adds the next 3 days of reanalysis rain at the basin point.
FV_TARGETS = {"eccc:08MH029": ("sumas-abbotsford", ("usgs:12214500",)),
              "eccc:08MH001": ("chilliwack-upper", ("eccc:08MH103", "eccc:08MH056", "eccc:08MH016")),
              "eccc:08MH103": ("chilliwack-upper", ("eccc:08MH016",)),
              "eccc:08MF005": ("coquihalla-hope", ("eccc:08MF040", "eccc:08LF051")),
              "eccc:08MH024": ("coquihalla-hope", ("eccc:08MF005",)),
              "eccc:08MH155": ("nicomekl-langley", ()),
              "eccc:08MF062": ("coquihalla-hope", ("eccc:08MF068",))}
FV_RAIN = {"hope": ("1113542", "1113543"), "pitt_meadows": ("1106178",)}


def fraser_valley_daily(conn: psycopg.Connection, out_dir: Path) -> dict[str, Any]:
    conn.execute("SET statement_timeout = '15min'")
    from datetime import date

    def daily_level(sid: str) -> dict[date, float]:
        stn = sid.split(":", 1)[1]
        return {d: float(v) for d, v in conn.execute(
            "SELECT date, level FROM eccc_daily WHERE station_number = %s AND level IS NOT NULL", (stn,))}

    rain = {}
    for name, ids in FV_RAIN.items():
        rain[name] = {d: float(v) for d, v in conn.execute(
            "SELECT (ts - interval '1 second')::date, sum(precip_mm) FROM rain_hourly WHERE source = 'eccc-climate'"
            " AND site = ANY(%s) AND precip_mm IS NOT NULL GROUP BY 1 HAVING count(*) >= 20", (list(ids),))}
    tp = {sid: v for sid, v in conn.execute("SELECT station_id, value_m FROM typical_peaks WHERE method ="
                                             " 'typical-peak-v1' AND status IN ('ok', 'flagged')")}
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {}
    for variant in ("honest", "oracle"):
        path = out_dir / f"fraser_valley_daily_{variant}_v1.csv.gz"
        n = 0
        with gzip.open(path, "wt", newline="") as fh:
            w: csv.DictWriter | None = None
            for sid, (point, ups) in FV_TARGETS.items():
                lv = daily_level(sid)
                up = {u: daily_level(u) if u.startswith("eccc:") else {} for u in ups}
                era = {d: float(v) for d, v in conn.execute(
                    "SELECT (ts - interval '1 second')::date, sum(precip_mm) FROM openmeteo_hourly WHERE kind ="
                    " 'archive' AND point = %s GROUP BY 1", (point,))} if variant == "oracle" else {}
                for d in sorted(lv):
                    r: dict[str, Any] = {"station_id": sid, "issue_date": d.isoformat(),
                                         "wy": d.year + 1 if d.month >= 10 else d.year, "variant": variant,
                                         "data_status": "approved history (HYDAT)"}
                    r["holdout"] = r["wy"] in HOLDOUT_WY
                    for lag in (0, 1, 2, 7):
                        r[f"lvl_d{lag}"] = lv.get(d - timedelta(days=lag), "")
                    for u, s in up.items():
                        r[f"up_{u.split(':')[1]}_d0"] = s.get(d, "")
                        r[f"up_{u.split(':')[1]}_d1"] = s.get(d - timedelta(days=1), "")
                    for name, rr in rain.items():
                        r[f"rain_{name}_d0"] = rr.get(d, "")
                        r[f"rain_{name}_3d"] = (sum(rr[x] for x in (d - timedelta(days=k) for k in range(3)) if x in rr)
                                                if any((d - timedelta(days=k)) in rr for k in range(3)) else "")
                    doy = d.timetuple().tm_yday
                    r["doy_sin"], r["doy_cos"] = math.sin(2 * math.pi * doy / 365.25), math.cos(2 * math.pi * doy /
                                                                                                   365.25)
                    if variant == "oracle":
                        r["oracle_future_rain_3d"] = sum(era.get(d + timedelta(days=k), 0.0) for k in (1, 2, 3))
                    fut = [lv.get(d + timedelta(days=k)) for k in (1, 2, 3)]
                    for k, v in zip((1, 2, 3), fut, strict=True):
                        r[f"y_lvl_d{k}"] = "" if v is None else v
                    peak = tp.get(sid)
                    r["typical_peak_m"] = "" if peak is None else peak
                    r["y_reach_typical_peak_3d"] = ("" if peak is None or all(v is None for v in fut) else
                                                    float(any(v is not None and v >= peak for v in fut)))
                    if w is None:
                        w = csv.DictWriter(fh, fieldnames=_fv_columns(variant), extrasaction="raise")
                        w.writeheader()
                    w.writerow({c: r.get(c, "") for c in _fv_columns(variant)})
                    n += 1
        manifest[variant] = {"file": path.name, "rows": n, "bytes": path.stat().st_size,
                             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return manifest


def _fv_columns(variant: str) -> list[str]:
    ups = sorted({u.split(":")[1] for _, us in FV_TARGETS.values() for u in us if u.startswith("eccc:")})
    cols = ["station_id", "issue_date", "wy", "variant", "data_status", "holdout"]
    cols += [f"lvl_d{lag}" for lag in (0, 1, 2, 7)]
    cols += [f"up_{u}_d{k}" for u in ups for k in (0, 1)]
    cols += [f"rain_{n}_{p}" for n in FV_RAIN for p in ("d0", "3d")]
    cols += ["doy_sin", "doy_cos"] + (["oracle_future_rain_3d"] if variant == "oracle" else [])
    cols += ["y_lvl_d1", "y_lvl_d2", "y_lvl_d3", "typical_peak_m", "y_reach_typical_peak_3d"]
    return cols
