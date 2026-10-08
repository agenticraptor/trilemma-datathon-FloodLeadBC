"""Baseline forecasters: `persistence-v1` and `trend3h-v1`, with empirical error paths.

Both use the same method: a point path from the model, plus empirical error paths of that same model on the
station's own history (rows first seen before the forecast's created_at), sampled across past origins.
samples[o, l] = point(l) + error(o, l), for leads l (grid steps after `data_as_of`). Quantiles of the level at
`valid_at` (q), of the running maximum over (data_as_of, valid_at] (qmax), and exceedance probabilities
(fraction of samples whose running maximum reaches the threshold) all come from these samples.

- persistence-v1: point(l) = y(d).
- trend3h-v1: least-squares slope over the 3 h of observations ending at d (needs >= 50 % of the window's grid
  points); point(l) = y(d) + slope * min(l, 6 h). The trend is held after 6 h so the 48 h trend is not a strawman.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

QUANTILES = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)
QKEYS = tuple(str(q) for q in QUANTILES)  # "0.05", "0.1", ...
HORIZONS_H = (1, 3, 6, 12, 18, 24, 36, 48)
TREND_WINDOW = timedelta(hours=3)
TREND_CAP = timedelta(hours=6)
TREND_MIN_COVERAGE = 0.5
FFILL_LIMIT = timedelta(minutes=30)  # gaps up to 30 min are carried forward when building error paths
MAX_LEAD = timedelta(hours=51)  # 48 h horizon + up to 3 h input age
MODELS = ("persistence-v1", "trend3h-v1")

PARAMS = {
    "quantiles": list(QUANTILES), "horizons_h": list(HORIZONS_H), "quantile_method": "numpy.quantile linear",
    "trend_window_h": 3, "trend_cap_h": 6, "trend_min_coverage": TREND_MIN_COVERAGE,
    "ffill_limit_min": 30, "max_lead_h": 51,
    "library": {"eccc": "trailing 30 days, origins every 1 h",
                "usgs": "trailing 30 days (origins every 1 h) + the same season (day of year +/- 30 days) in every "
                        "prior year (origins every 3 h)"},
    "leakage": "only rows with ts <= created_at and first_seen_at <= created_at",
}


@dataclass
class Grid:
    start: datetime  # time of index 0
    step: timedelta
    y: np.ndarray  # float64, NaN where missing

    def time(self, i: int) -> datetime:
        return self.start + self.step * i

    def index(self, t: datetime) -> int:
        return int(round((t - self.start) / self.step))


def to_grid(rows: list[tuple[datetime, float]], step: timedelta, start: datetime | None = None,
            end: datetime | None = None) -> Grid:
    """Place observations on a regular grid (timestamps are already on the station's 5- or 15-min grid)."""
    if not rows:
        raise ValueError("no rows")
    s = start or rows[0][0]
    e = end or rows[-1][0]
    n = int((e - s) / step) + 1
    y = np.full(n, np.nan)
    for t, v in rows:
        i = int(round((t - s) / step))
        if 0 <= i < n:
            y[i] = v
    return Grid(s, step, y)


def ffill(y: np.ndarray, limit: int) -> np.ndarray:
    """Forward-fill NaNs, at most `limit` consecutive points."""
    out = y.copy()
    idx = np.where(~np.isnan(y), np.arange(len(y)), -1)
    np.maximum.accumulate(idx, out=idx)
    fill = (idx >= 0) & np.isnan(y) & (np.arange(len(y)) - idx <= limit)
    out[fill] = y[idx[fill]]
    return out


def slopes(y: np.ndarray, ends: np.ndarray, window_pts: int, min_cov: float) -> np.ndarray:
    """Least-squares slope (per grid step) over points [end-window_pts, end] for each end index; NaN if fewer than
    min_cov of the window's points exist."""
    w = window_pts + 1
    x = np.arange(-window_pts, 1, dtype=float)
    idx = ends[:, None] + np.arange(-window_pts, 1)[None, :]
    valid_idx = (idx >= 0) & (idx < len(y))
    vals = np.where(valid_idx, y[np.clip(idx, 0, len(y) - 1)], np.nan)
    m = ~np.isnan(vals)
    n = m.sum(axis=1)
    xs = np.where(m, x[None, :], 0.0)
    ys = np.where(m, vals, 0.0)
    sx, sy = xs.sum(1), ys.sum(1)
    sxx, sxy = (xs * xs).sum(1), (xs * ys).sum(1)
    den = n * sxx - sx * sx
    with np.errstate(invalid="ignore", divide="ignore"):
        slope = (n * sxy - sx * sy) / den
    slope[(n < min_cov * w) | (den == 0)] = np.nan
    return slope


def point_path(model: str, y_d: float, slope_d: float, leads: np.ndarray, cap_pts: int) -> np.ndarray:
    if model == "persistence-v1":
        return np.full(len(leads), y_d)
    return y_d + slope_d * np.minimum(leads, cap_pts)


def error_paths(model: str, g: Grid, origins: np.ndarray, max_lead_pts: int, window_pts: int, cap_pts: int,
                ffill_pts: int) -> tuple[np.ndarray, np.ndarray]:
    """Return (E, used_origins): E[o, l-1] = y(o + l) - point_o(l) for l = 1..max_lead_pts, rows without gaps."""
    yf = ffill(g.y, ffill_pts)
    origins = origins[(origins >= window_pts) & (origins + max_lead_pts < len(yf))]
    if len(origins) == 0:
        return np.empty((0, max_lead_pts)), origins
    leads = np.arange(1, max_lead_pts + 1)
    Y = yf[origins[:, None] + leads[None, :]]
    base = g.y[origins]  # the origin's own observation (not filled)
    if model == "persistence-v1":
        P = np.repeat(base[:, None], max_lead_pts, axis=1)
        ok = ~np.isnan(base)
    else:
        sl = slopes(g.y, origins, window_pts, TREND_MIN_COVERAGE)
        P = base[:, None] + sl[:, None] * np.minimum(leads, cap_pts)[None, :]
        ok = ~np.isnan(base) & ~np.isnan(sl)
    E = Y - P
    ok &= ~np.isnan(E).any(axis=1)
    return E[ok], origins[ok]


def library_hash(model: str, station_id: str, E: np.ndarray, origin_times: list[datetime]) -> str:
    h = hashlib.sha256()
    h.update(f"{model}|{station_id}|{len(origin_times)}|".encode())
    h.update("|".join(t.strftime("%Y%m%dT%H%M") for t in origin_times).encode())
    h.update(np.round(E, 4).astype(np.float32).tobytes())
    return h.hexdigest()


def summarise(samples: np.ndarray, lead_idx: list[int], thresholds: dict[str, float]
              ) -> list[tuple[dict[str, float], dict[str, float], dict[str, float]]]:
    """For each lead index (1-based lead in grid steps): (q, qmax, p_exceed) from the sample matrix."""
    run_max = np.maximum.accumulate(samples, axis=1)
    out = []
    for li in lead_idx:
        col = samples[:, li - 1]
        mcol = run_max[:, li - 1]
        q = dict(zip(QKEYS, np.quantile(col, QUANTILES).tolist(), strict=True))
        qm = dict(zip(QKEYS, np.quantile(mcol, QUANTILES).tolist(), strict=True))
        pe = {k: float(np.mean(mcol >= thr)) for k, thr in thresholds.items()}
        out.append((q, qm, pe))
    return out
