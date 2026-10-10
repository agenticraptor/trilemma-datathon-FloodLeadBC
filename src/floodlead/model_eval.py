"""Scoring for Stage 4 (protocol §4, §6 with amendments 1-4): level skill (T6), crossing probabilities (T3, T5),
overflow (T4), alert rules (T1, T2). Used for development (walk-forward validation predictions) and, after the
supervisor's go, for the single final run.

Comparators on the same rows:
- pure persistence: the level at the cut-off held flat (a point forecast; its fair CRPS is the absolute error);
- 3 h trend: nc_lvl + (nc_d3h / 3) x min(h, 6) (the trend3h-v1 rule as a point forecast);
- for probabilities, persistence is 1 if nc_lvl >= X else 0; NWS-derived is nws_p_ge_148 / nws_p_ge_150.
Rising limb: nc_d3h >= 0.5 ft (§4).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from floodlead import crps
from floodlead.model import LEVELS
from floodlead.trust import clopper_pearson

RISING_FT = 0.5
BOOT = 1000
SEED = 7


def fair_crps_rows(q19: np.ndarray, y: np.ndarray) -> np.ndarray:
    lv = list(LEVELS)
    return np.array([crps.crps_pl(lv, q, yy) if np.isfinite(yy) and np.isfinite(q).all() else np.nan
                     for q, yy in zip(q19, y, strict=True)])


def trend_point(nc_lvl: np.ndarray, nc_d3h: np.ndarray, h: int) -> np.ndarray:
    slope = np.nan_to_num(nc_d3h, nan=0.0) / 3.0
    return nc_lvl + slope * min(h, 6)


def boot_ci(values_by_year: dict[int, tuple[float, float]], stat, n: int = BOOT) -> list[float]:  # noqa: ANN001
    """Bootstrap by water year: resample years with replacement; stat(sum_a, sum_b) from per-year sums."""
    years = sorted(values_by_year)
    if len(years) < 2:
        return [math.nan, math.nan]
    rng = np.random.default_rng(SEED)
    arr = np.array([values_by_year[y] for y in years])
    out = []
    for _ in range(n):
        idx = rng.integers(0, len(years), len(years))
        a, b = arr[idx].sum(axis=0)
        out.append(stat(a, b))
    lo, hi = np.nanpercentile(out, [2.5, 97.5])
    return [round(float(lo), 4), round(float(hi), 4)]


def level_skill(q19: np.ndarray, y_change: np.ndarray, nc_lvl: np.ndarray, nc_d3h: np.ndarray, wy: np.ndarray,
                h: int, rising_only: bool = False) -> dict[str, Any]:
    """T6 at one horizon: fair CRPSS and median-MAE skill against pure persistence (and the 3 h trend), on rows
    with a target. Persistence predicts a change of 0; the trend predicts (nc_d3h / 3) x min(h, 6)."""
    ok = np.isfinite(y_change) & np.isfinite(q19).all(axis=1)
    if rising_only:
        ok &= np.nan_to_num(nc_d3h, nan=-1) >= RISING_FT
    q, y, d3, w = q19[ok], y_change[ok], nc_d3h[ok], wy[ok]
    if len(y) == 0:
        return {"h": h, "n": 0, "rising_only": rising_only}
    c_model = fair_crps_rows(q, y)
    med = q[:, LEVELS.index(0.5)]
    ae_model = np.abs(y - med)
    ae_pers = np.abs(y)
    trend_change = trend_point(np.zeros_like(y), d3, h)
    ae_trend = np.abs(y - trend_change)
    per_year: dict[int, tuple[float, float]] = {}
    per_year_mae: dict[int, tuple[float, float]] = {}
    for yr in np.unique(w):
        m = w == yr
        per_year[int(yr)] = (float(c_model[m].sum()), float(ae_pers[m].sum()))
        per_year_mae[int(yr)] = (float(ae_model[m].sum()), float(ae_pers[m].sum()))

    def skill(a: float, b: float) -> float:
        return 1 - a / b if b > 0 else math.nan

    return {"h": h, "n": int(len(y)), "years": int(len(per_year)), "rising_only": rising_only,
            "fair_crps_model": round(float(c_model.mean()), 4), "crps_persistence": round(float(ae_pers.mean()), 4),
            "crps_trend": round(float(ae_trend.mean()), 4),
            "fair_crpss_vs_persistence": round(skill(c_model.sum(), ae_pers.sum()), 4),
            "fair_crpss_vs_persistence_ci95": boot_ci(per_year, skill),
            "fair_crpss_vs_trend": round(skill(c_model.sum(), ae_trend.sum()), 4),
            "mae_model": round(float(ae_model.mean()), 4), "mae_persistence": round(float(ae_pers.mean()), 4),
            "mae_skill_vs_persistence": round(skill(ae_model.sum(), ae_pers.sum()), 4),
            "mae_skill_vs_persistence_ci95": boot_ci(per_year_mae, skill)}


def brier_block(p: np.ndarray, o: np.ndarray, ref: dict[str, np.ndarray], wy: np.ndarray) -> dict[str, Any]:
    """Brier score, BSS against each reference (bootstrap by water year), reliability (10 bins), ECE, and the
    low-bias check (amendment 1, A8): the 95 % interval of mean(p) - mean(o) must not lie entirely below 0."""
    ok = np.isfinite(p) & np.isfinite(o)
    for r in ref.values():
        ok &= np.isfinite(r)
    p, o, w = p[ok], o[ok], wy[ok]
    if len(p) == 0:
        return {"n": 0}
    out: dict[str, Any] = {"n": int(len(p)), "positives": int(o.sum()), "brier": round(float(((p - o) ** 2).mean()), 5)}
    for name, r in ref.items():
        r = r[ok]
        per = {int(y): (float(((p[w == y] - o[w == y]) ** 2).sum()), float(((r[w == y] - o[w == y]) ** 2).sum()))
               for y in np.unique(w)}
        bm, br = sum(a for a, _ in per.values()), sum(b for _, b in per.values())
        out[f"bss_vs_{name}"] = round(1 - bm / br, 4) if br > 0 else None
        out[f"bss_vs_{name}_ci95"] = boot_ci(per, lambda a, b: 1 - a / b if b > 0 else math.nan)
    bins = np.clip((p * 10).astype(int), 0, 9)
    rel, ece = [], 0.0
    for b in range(10):
        m = bins == b
        if m.any():
            rel.append({"bin": b, "n": int(m.sum()), "mean_p": round(float(p[m].mean()), 4),
                        "observed": round(float(o[m].mean()), 4)})
            ece += m.sum() / len(p) * abs(p[m].mean() - o[m].mean())
    out["reliability"] = rel
    out["ece"] = round(float(ece), 4)
    per_bias = {int(y): (float(p[w == y].sum() - o[w == y].sum()), float((w == y).sum())) for y in np.unique(w)}
    out["mean_p_minus_obs"] = round(float(p.mean() - o.mean()), 5)
    out["mean_p_minus_obs_ci95"] = boot_ci(per_bias, lambda a, b: a / b if b > 0 else math.nan)
    lo = out["mean_p_minus_obs_ci95"][0]
    hi = out["mean_p_minus_obs_ci95"][1]
    out["no_systematic_low_bias"] = None if any(map(math.isnan, (lo, hi))) else not (hi < 0)
    return out


def alert_events(prob: np.ndarray, times: np.ndarray, p_star: float, k: int) -> list[int]:
    """Indices where an alert fires: prob >= p_star for k consecutive hourly issuances (first index of each run that
    reaches k; a new alert needs the probability to drop below p_star first)."""
    fired, run, armed = [], 0, True
    for i, p in enumerate(prob):
        if np.isfinite(p) and p >= p_star:
            run += 1
            if run >= k and armed:
                fired.append(i)
                armed = False
        else:
            run = 0
            armed = True
    return fired


def score_alerts(fire_times: list, event_times: list, max_lead_h: float = 48.0) -> dict[str, Any]:
    """Event-based POD and FAR: an alert is a hit if an event follows within max_lead_h; an event is detected if an
    alert came in the max_lead_h before it. Leads are listed per event; exact intervals on both rates."""
    import datetime as dt

    lead = dt.timedelta(hours=max_lead_h)
    hits = [a for a in fire_times if any(a <= e <= a + lead for e in event_times)]
    det = []
    for e in event_times:
        prior = [a for a in fire_times if e - lead <= a <= e]
        det.append({"event": e.isoformat(), "detected": bool(prior),
                    "lead_h": round((e - min(prior)).total_seconds() / 3600, 2) if prior else None})
    n_al, n_ev = len(fire_times), len(event_times)
    pod_k = sum(d["detected"] for d in det)
    far_k = n_al - len(hits)
    return {"alerts": n_al, "events": n_ev, "pod": round(pod_k / n_ev, 3) if n_ev else None,
            "pod_ci95": [round(x, 3) for x in clopper_pearson(pod_k, n_ev)] if n_ev else None,
            "far": round(far_k / n_al, 3) if n_al else None,
            "far_ci95": [round(x, 3) for x in clopper_pearson(far_k, n_al)] if n_al else None,
            "per_event": det}
