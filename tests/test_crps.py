"""Fair CRPS (Stage 3, F1): exactness for point forecasts and the bias table on synthetic distributions."""

import math
import random
from statistics import NormalDist

import pytest

from floodlead import crps

L7 = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]
L19 = [round(0.05 * i, 2) for i in range(1, 20)]
SQRT_PI = math.sqrt(math.pi)


def exact_normal(mu: float, sd: float, y: float) -> float:
    z = (y - mu) / sd
    n = NormalDist()
    return sd * (z * (2 * n.cdf(z) - 1) + 2 * n.pdf(z) - 1 / SQRT_PI)


def exact_lognormal(m: float, s: float, y: float) -> float:
    """Closed form for LN(m, s) (Baran and Lerch 2015)."""
    n = NormalDist()
    assert y > 0
    w = (math.log(y) - m) / s
    return y * (2 * n.cdf(w) - 1) - 2 * math.exp(m + s * s / 2) * (n.cdf(w - s) + n.cdf(s / math.sqrt(2)) - 1)


def test_point_forecast_is_absolute_error() -> None:
    for y in (-3.0, 0.0, 1.234, 7.5):
        assert crps.crps_pl(L7, [1.234] * 7, y) == pytest.approx(abs(y - 1.234), abs=1e-12)
        assert crps.crps_qs(L7, [1.234] * 7, y) == pytest.approx(abs(y - 1.234), abs=1e-12)


def test_tied_edge_quantiles_are_point_masses() -> None:
    # 0.05 == 0.1 and 0.9 == 0.95: the tails collapse to point masses; still finite and >= 0
    q = [1.0, 1.0, 1.2, 1.5, 1.8, 2.0, 2.0]
    for y in (0.0, 1.0, 1.5, 2.0, 3.0):
        v = crps.crps_pl(L7, q, y)
        assert v >= 0 and math.isfinite(v)
    # far below: every unit of distance adds exactly 1 (F = 0 there, indicator = 1)
    assert crps.crps_pl(L7, q, -10.0) - crps.crps_pl(L7, q, -9.0) == pytest.approx(1.0)


def test_matches_numerical_integral_of_the_same_cdf() -> None:
    q = [0.1, 0.3, 0.6, 1.0, 1.3, 1.9, 2.4]
    lam = (L7[1] - L7[0]) / (q[1] - q[0]) / L7[0]
    mu = (L7[-1] - L7[-2]) / (q[-1] - q[-2]) / (1 - L7[-1])

    def cdf(x: float) -> float:
        if x < q[0]:
            return L7[0] * math.exp(lam * (x - q[0]))
        if x > q[-1]:
            return 1 - (1 - L7[-1]) * math.exp(-mu * (x - q[-1]))
        for i in range(6):
            if q[i] <= x <= q[i + 1]:
                return L7[i] + (L7[i + 1] - L7[i]) * (x - q[i]) / (q[i + 1] - q[i])
        raise AssertionError

    for y in (-1.0, 0.2, 1.0, 2.2, 4.0):
        n, lo, hi = 200_000, -8.0, 12.0
        dx = (hi - lo) / n
        num = sum((cdf(lo + (i + 0.5) * dx) - (1.0 if lo + (i + 0.5) * dx >= y else 0.0)) ** 2 for i in range(n)) * dx
        assert crps.crps_pl(L7, q, y) == pytest.approx(num, rel=1e-4)


CASES = {
    # name: (forecast quantile function, exact CRPS of the forecast distribution at y, truth sampler)
    "calibrated normal": (NormalDist(0, 1).inv_cdf, lambda y: exact_normal(0, 1, y), lambda r: r.gauss(0, 1)),
    "log-normal (s=0.5)": (lambda p: math.exp(0.5 * NormalDist().inv_cdf(p)), lambda y: exact_lognormal(0, 0.5, y),
                           lambda r: math.exp(r.gauss(0, 0.5))),
    "under-dispersed (sd 0.5 vs 1)": (NormalDist(0, 0.5).inv_cdf, lambda y: exact_normal(0, 0.5, y),
                                      lambda r: r.gauss(0, 1)),
    "over-dispersed (sd 2 vs 1)": (NormalDist(0, 2).inv_cdf, lambda y: exact_normal(0, 2, y),
                                   lambda r: r.gauss(0, 1)),
}


def bias_table(levels: list[float], n: int = 4000, seed: int = 7) -> dict[str, tuple[float, float]]:
    out = {}
    for name, (ppf, exact, draw) in CASES.items():
        r = random.Random(seed)
        ys = [draw(r) for _ in range(n)]
        q = [ppf(p) for p in levels]
        ex = sum(exact(y) for y in ys) / n
        pl = sum(crps.crps_pl(levels, q, y) for y in ys) / n
        qs = sum(crps.crps_qs(levels, q, y) for y in ys) / n
        out[name] = ((pl - ex) / ex, (qs - ex) / ex)
    return out


def test_bias_table_7_levels_under_5_percent() -> None:
    table = bias_table(L7)
    for name, (b_pl, b_qs) in table.items():
        print(f"7 levels  {name:32s} fair {100 * b_pl:+.1f} %   quantile score {100 * b_qs:+.1f} %")
        assert abs(b_pl) < 0.05, name
    assert table["calibrated normal"][1] < -0.15  # the old approximation is ~19 % low here


def test_bias_table_19_levels_under_1_percent() -> None:
    for name, (b_pl, _) in bias_table(L19).items():
        print(f"19 levels {name:32s} fair {100 * b_pl:+.1f} %")
        assert abs(b_pl) < 0.01, name


def test_from_ledger_keys_orders_levels() -> None:
    q = {"0.5": 1.0, "0.05": 0.5, "0.95": 1.5, "0.1": 0.6, "0.9": 1.4, "0.25": 0.8, "0.75": 1.2}
    assert crps.from_keys(q) == (L7, [0.5, 0.6, 0.8, 1.0, 1.2, 1.4, 1.5])
    assert crps.fair(q, 1.0) == pytest.approx(crps.crps_pl(L7, [0.5, 0.6, 0.8, 1.0, 1.2, 1.4, 1.5], 1.0))
