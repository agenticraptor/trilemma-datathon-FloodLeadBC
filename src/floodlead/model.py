"""The Nooksack hourly model (Stage 4), as fixed in protocol amendment 4.

Targets (derived from the frozen dataset columns; nothing is rebuilt):
- level change d_h = y_lvl_h - nc_lvl at h in HORIZONS;
- window maximum m_H = max(y_lvl_h1 ... y_lvl_hH) - nc_lvl for H in WINDOWS, defined when >= H - 2 hours exist.
Each target gets quantiles at FIT_LEVELS, interpolated linearly in level to the 19 LEVELS and sorted.
Crossing probabilities P(level >= X within H) = 1 - F_H(X - nc_lvl), F_H the CDF of m_H rebuilt from its 19 quantiles:
piecewise linear with the exponential tails of floodlead.crps. Never a classifier on threshold labels.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

HORIZONS = (1, 3, 6, 12, 18, 24, 36, 48)
WINDOWS = (12, 24, 48)
FIT_LEVELS = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
LEVELS = tuple(round(0.05 * i, 2) for i in range(1, 20))
GAUGES = ("nc", "nf", "mf", "sf", "everson", "ferndale")
G = [f"{g}_{s}" for g in GAUGES for s in ("lvl", "d1h", "d3h", "d6h", "d12h", "max24h")] + [
    "nc_mean7d", "nc_mean30d", "doy_sin", "doy_cos"]
R = ["snotel_p1h", "snotel_p3h", "snotel_p6h", "snotel_p12h", "snotel_p24h", "snotel_p48h", "snotel_p72h",
     "snotel_swe_mm", "snotel_swe_d24h", "kbli_p1h", "kbli_p3h", "kbli_p6h", "kbli_p24h", "kbli_p72h"]
F = ["fc_rain_0_18h", "fc_rain_18_42h"]
ORACLE = ["oracle_future_rain_6h", "oracle_future_rain_12h", "oracle_future_rain_24h", "oracle_future_rain_48h"]
GROUPS = {"G": G, "G+R": G + R, "G+R+F": G + R + F, "oracle": G + R + ORACLE}
LINEAR_FEATURES = ["nc_lvl", "nc_d1h", "nc_d3h", "nc_d6h", "nf_d3h", "mf_d3h", "sf_d3h", "snotel_p6h", "snotel_p24h",
                   "kbli_p6h", "doy_sin", "doy_cos"]
LGB_PARAMS = {"n_estimators": 200, "learning_rate": 0.05, "num_leaves": 31, "min_child_samples": 50,
              "verbose": -1, "n_jobs": 1}
LINEAR_MAX_ROWS = 30_000
SEED = 20261010


def targets(df: pd.DataFrame) -> pd.DataFrame:
    """Add d_h and m_H columns (amendment 4, item 2)."""
    out = {}
    for h in HORIZONS:
        out[f"d_{h}"] = df[f"y_lvl_h{h}"] - df["nc_lvl"]
    hourly = df[[f"y_lvl_h{h}" for h in range(1, 49)]].to_numpy(dtype=float)
    for w in WINDOWS:
        sub = hourly[:, :w]
        ok = np.isfinite(sub).sum(axis=1) >= w - 2
        mx = np.where(ok, np.nanmax(np.where(np.isfinite(sub), sub, -np.inf), axis=1), np.nan)
        out[f"m_{w}"] = mx - df["nc_lvl"].to_numpy(dtype=float)
    return pd.concat([df, pd.DataFrame(out, index=df.index)], axis=1)


TARGETS = tuple(f"d_{h}" for h in HORIZONS) + tuple(f"m_{w}" for w in WINDOWS)


def quiet_mask(df: pd.DataFrame) -> np.ndarray:
    """Quiet rows (amendment 4, item 6): |nc_d3h| < 0.1 ft and nc_lvl < 144 ft."""
    return ((df["nc_d3h"].abs() < 0.1) & (df["nc_lvl"] < 144)).to_numpy()


def subsample(df: pd.DataFrame, keep_quiet: float = 0.2, seed: int = SEED) -> pd.DataFrame:
    q = quiet_mask(df)
    rng = np.random.default_rng(seed)
    keep = ~q | (rng.random(len(df)) < keep_quiet)
    return df[keep]


@dataclass
class Fitted:
    family: str
    group: str
    features: list[str]
    sub: bool
    train_years: list[int]
    models: dict[str, list[Any]] = field(default_factory=dict)
    fill: dict[str, float] = field(default_factory=dict)
    fit_seconds: float = 0.0


def fit(train: pd.DataFrame, family: str, group: str, sub: bool, train_years: list[int],
        targets: tuple[str, ...] = TARGETS) -> Fitted:
    """Fit each of `targets` at FIT_LEVELS. `train` must hold only rows of `train_years` (checked by the caller)."""
    feats = LINEAR_FEATURES if family == "linear" else GROUPS[group]
    fm = Fitted(family, group, list(feats), sub, sorted(train_years))
    t0 = time.monotonic()
    data = subsample(train) if sub else train
    data = data[np.isfinite(data["nc_lvl"].to_numpy(dtype=float))]
    if family == "linear":
        from sklearn.linear_model import QuantileRegressor

        fm.fill = {c: float(np.nanmedian(data[c])) if np.isfinite(data[c]).any() else 0.0 for c in feats}
        for tgt in targets:
            d = data[np.isfinite(data[tgt].to_numpy(dtype=float))]
            if len(d) > LINEAR_MAX_ROWS:
                d = d.sample(LINEAR_MAX_ROWS, random_state=SEED)
            x = d[feats].fillna(fm.fill).to_numpy(dtype=float)
            y = d[tgt].to_numpy(dtype=float)
            fm.models[tgt] = [QuantileRegressor(quantile=q, alpha=0.0, solver="highs-ipm").fit(x, y)
                              for q in FIT_LEVELS]
    else:
        import lightgbm as lgb

        for tgt in targets:
            d = data[np.isfinite(data[tgt].to_numpy(dtype=float))]
            x = d[feats].to_numpy(dtype=float)
            y = d[tgt].to_numpy(dtype=float)
            fm.models[tgt] = [lgb.LGBMRegressor(objective="quantile", alpha=q, random_state=SEED, **LGB_PARAMS)
                              .fit(x, y) for q in FIT_LEVELS]
    fm.fit_seconds = round(time.monotonic() - t0, 1)
    return fm


def interp19(q7: np.ndarray) -> np.ndarray:
    """(n, 7) quantiles at FIT_LEVELS -> (n, 19) at LEVELS, linear in level, then sorted (no crossing)."""
    q7 = np.sort(np.asarray(q7, dtype=float), axis=1)
    lv = np.asarray(FIT_LEVELS)
    out = np.empty((q7.shape[0], len(LEVELS)))
    for j, x in enumerate(LEVELS):
        k = min(max(int(np.searchsorted(lv, x, side="right")) - 1, 0), len(lv) - 2)
        w = (x - lv[k]) / (lv[k + 1] - lv[k])
        out[:, j] = q7[:, k] * (1 - w) + q7[:, k + 1] * w
    return np.sort(out, axis=1)


def predict(fm: Fitted, df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Per target, (n, 19) sorted quantiles of the change from nc_lvl."""
    x = df[fm.features]
    x = x.fillna(fm.fill).to_numpy(dtype=float) if fm.family == "linear" else x.to_numpy(dtype=float)
    out = {}
    for tgt, ms in fm.models.items():
        q7 = np.column_stack([m.predict(x) for m in ms])
        out[tgt] = interp19(q7)
    return out


def cdf_at(q: np.ndarray, c: float) -> float:
    """F(c) of the distribution rebuilt from quantiles q at LEVELS: linear between quantiles; below q[0] and above
    q[-1], exponential tails with the edge segment's density (floodlead.crps); a zero-width edge is a point mass."""
    t = LEVELS
    if c < q[0]:
        w = q[1] - q[0]
        return t[0] * math.exp((t[1] - t[0]) / w / t[0] * (c - q[0])) if w > 0 else 0.0
    if c >= q[-1]:
        w = q[-1] - q[-2]
        return 1 - (1 - t[-1]) * math.exp(-(t[-1] - t[-2]) / w / (1 - t[-1]) * (c - q[-1])) if w > 0 else \
            (t[-1] if c == q[-1] else 1.0)
    k = int(np.searchsorted(q, c, side="right")) - 1
    a, b = q[k], q[k + 1]
    return t[k] if b <= a else t[k] + (t[k + 1] - t[k]) * (c - a) / (b - a)


def exceed_prob(q19: np.ndarray, threshold_change: np.ndarray) -> np.ndarray:
    """P(X > c) = 1 - F(c) per row, X with quantiles q19 at LEVELS."""
    out = np.full(q19.shape[0], np.nan)
    for i in range(q19.shape[0]):
        q, c = q19[i], threshold_change[i]
        if np.isfinite(c) and np.isfinite(q).all():
            out[i] = 1.0 - cdf_at(q, float(c))
    return out


def crossing_prob(q19_window: np.ndarray, nc_lvl: np.ndarray, level_ft: float) -> np.ndarray:
    """P(North Cedarville >= level_ft within the window) from the window-maximum quantiles."""
    return exceed_prob(q19_window, level_ft - np.asarray(nc_lvl, dtype=float))


def overflow_prob(q19_window: np.ndarray, nc_lvl: np.ndarray, onset_levels: list[float]) -> np.ndarray:
    """Default overflow model (amendment 4, item 5): mean over development onsets j of P(M_H >= L_j)."""
    ps = [crossing_prob(q19_window, nc_lvl, lv) for lv in onset_levels]
    return np.mean(ps, axis=0)
