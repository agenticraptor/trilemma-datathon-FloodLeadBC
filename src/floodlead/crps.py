"""Fair CRPS for forecasts stored as quantiles (Stage 3, F1; D-03.4).

The forecast's CDF is rebuilt from its quantiles (levels tau_1 < ... < tau_K at values q_1 <= ... <= q_K):

- between quantiles, F is linear: F(q_i) = tau_i;
- below q_1 and above q_K, exponential tails that keep the density of the nearest segment:
  F(x) = tau_1 * exp(lam * (x - q_1)) with lam = f_1 / tau_1, and 1 - F(x) = (1 - tau_K) * exp(-mu * (x - q_K)) with
  mu = f_K / (1 - tau_K), where f_1 and f_K are the slopes of the first and last segments. A zero-width edge segment
  gives an infinitely steep tail, that is a point mass at the edge quantile.

CRPS(F, y) = integral of (F(x) - 1{x >= y})^2 dx, computed exactly piece by piece (closed form; no sampling).
For a point forecast (all quantiles equal) it is exactly |y - q|.

Bias against the exact CRPS of the underlying distribution (tests/test_crps.py; 7 levels 0.05 ... 0.95): calibrated
normal +0.0 %, log-normal +0.1 %, under-dispersed -0.2 %, over-dispersed +1.2 %. The quantile score
(2 x mean pinball loss), used until Stage 3, is -13 % to -19 % on the same cases; it is kept as `crps_qs`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


def _seg(a: float, b: float, fa: float, fb: float, h: float) -> float:
    """Integral over [a, b] of (F - h)^2 for linear F from fa to fb."""
    da, db = fa - h, fb - h
    return (b - a) * (da * da + da * db + db * db) / 3.0


def crps_pl(levels: Sequence[float], values: Sequence[float], y: float) -> float:
    """Exact CRPS of the piecewise-linear CDF with exponential tails (module docstring) at observation y."""
    t = [float(v) for v in levels]
    q = [float(v) for v in values]
    k = len(q)
    if k != len(t) or k < 2:
        raise ValueError("need at least 2 quantiles with matching levels")
    if any(q[i + 1] < q[i] for i in range(k - 1)) or any(t[i + 1] <= t[i] for i in range(k - 1)):
        raise ValueError("quantiles must be non-decreasing and levels increasing")
    if q[-1] - q[0] <= 0.0:
        return abs(y - q[0])
    total = 0.0
    for i in range(k - 1):
        a, b, fa, fb = q[i], q[i + 1], t[i], t[i + 1]
        if b <= a:
            continue  # a jump in F: zero width, no contribution
        if y <= a:
            total += _seg(a, b, fa, fb, 1.0)
        elif y >= b:
            total += _seg(a, b, fa, fb, 0.0)
        else:
            fy = fa + (fb - fa) * (y - a) / (b - a)
            total += _seg(a, y, fa, fy, 0.0) + _seg(y, b, fy, fb, 1.0)
    # lower tail: F(x) = t1 * exp(lam * (x - q1)) for x < q1
    t1, w1 = t[0], q[1] - q[0]
    lam = (t[1] - t[0]) / w1 / t1 if w1 > 0 else math.inf
    if y >= q[0]:
        total += 0.0 if math.isinf(lam) else t1 * t1 / (2 * lam)
    elif math.isinf(lam):
        total += q[0] - y
    else:
        d = y - q[0]  # < 0
        e1, e2 = math.exp(lam * d), math.exp(2 * lam * d)
        total += t1 * t1 * e2 / (2 * lam) + (q[0] - y) - 2 * t1 * (1 - e1) / lam + t1 * t1 * (1 - e2) / (2 * lam)
    # upper tail: 1 - F(x) = tk * exp(-mu * (x - qK)) for x > qK
    tk, wk = 1.0 - t[-1], q[-1] - q[-2]
    mu = (t[-1] - t[-2]) / wk / tk if wk > 0 else math.inf
    if y <= q[-1]:
        total += 0.0 if math.isinf(mu) else tk * tk / (2 * mu)
    elif math.isinf(mu):
        total += y - q[-1]
    else:
        d = y - q[-1]  # > 0
        e1, e2 = math.exp(-mu * d), math.exp(-2 * mu * d)
        total += d - 2 * tk * (1 - e1) / mu + tk * tk * (1 - e2) / (2 * mu) + tk * tk * e2 / (2 * mu)
    return total


def pinball(tau: float, u: float) -> float:
    return u * tau if u >= 0 else u * (tau - 1.0)


def crps_qs(levels: Sequence[float], values: Sequence[float], y: float) -> float:
    """The quantile score: 2 x mean pinball loss over the levels (equal to |y - q| for a point forecast). Kept as a
    secondary column; it under-states the CRPS of a spread forecast (module docstring)."""
    return 2.0 * sum(pinball(t, y - v) for t, v in zip(levels, values, strict=True)) / len(levels)


def from_keys(q: Mapping[str, float]) -> tuple[list[float], list[float]]:
    """Levels and values from a ledger horizon's quantile dict (keys "0.05", "0.1", ...), in level order."""
    items = sorted((float(k), float(v)) for k, v in q.items())
    return [k for k, _ in items], [v for _, v in items]


def fair(q: Mapping[str, float], y: float) -> float:
    lv, vals = from_keys(q)
    return crps_pl(lv, vals, y)


def quantile_score(q: Mapping[str, float], y: float) -> float:
    lv, vals = from_keys(q)
    return crps_qs(lv, vals, y)
