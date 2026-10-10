"""Stage 4 model core: 19 sorted quantiles, CRPS of stored quantiles = crps.fair, crossing probabilities from the
window-maximum CDF (monotone; exact at the knots; brute-force check on a synthetic case)."""

import math
from statistics import NormalDist

import numpy as np
import pytest

from floodlead import crps, model


def normal_q19(mu: float = 0.0, sd: float = 1.0) -> np.ndarray:
    return np.array([[NormalDist(mu, sd).inv_cdf(p) for p in model.LEVELS]])


def test_interp19_is_sorted_and_has_19_levels() -> None:
    q7 = np.array([[0.9, 0.1, 0.3, 0.5, 0.6, 0.8, 0.2]])  # deliberately unsorted (crossing)
    q19 = model.interp19(q7)
    assert q19.shape == (1, 19) and np.all(np.diff(q19[0]) >= 0)
    assert len(model.LEVELS) == 19 and model.LEVELS[0] == 0.05 and model.LEVELS[-1] == 0.95


def test_crps_of_stored_quantiles_equals_crps_fair() -> None:
    q = normal_q19()[0]
    d = {str(lv): float(v) for lv, v in zip(model.LEVELS, q, strict=True)}
    for y in (-2.0, 0.0, 0.7):
        assert crps.crps_pl(list(model.LEVELS), list(q), y) == pytest.approx(crps.fair(d, y))


def test_exceedance_exact_at_knots_and_monotone() -> None:
    q = normal_q19()
    for k, lv in enumerate(model.LEVELS):
        assert model.exceed_prob(q, np.array([q[0, k]]))[0] == pytest.approx(1 - lv)
    grid = np.linspace(-4, 4, 161)
    p = [model.exceed_prob(q, np.array([c]))[0] for c in grid]
    assert all(a >= b for a, b in zip(p, p[1:], strict=False)) and 0 < p[-1] < p[0] < 1


def sample(q: np.ndarray, u: np.ndarray) -> np.ndarray:
    """Inverse-CDF sampling of the rebuilt distribution (linear between knots, exponential tails)."""
    t = np.asarray(model.LEVELS)
    x = np.interp(u, t, q)
    lam = (t[1] - t[0]) / (q[1] - q[0]) / t[0]
    mu = (t[-1] - t[-2]) / (q[-1] - q[-2]) / (1 - t[-1])
    lo, hi = u < t[0], u > t[-1]
    x[lo] = q[0] + np.log(u[lo] / t[0]) / lam
    x[hi] = q[-1] - np.log((1 - u[hi]) / (1 - t[-1])) / mu
    return x


def test_crossing_probability_matches_brute_force() -> None:
    q = normal_q19(0.3, 0.8)
    xs = sample(q[0], np.random.default_rng(1).random(400_000))
    for c in (-2.0, -0.5, 0.3, 1.0, 2.5):
        assert model.exceed_prob(q, np.array([c]))[0] == pytest.approx(float((xs > c).mean()), abs=0.004)
    # through the level-crossing helper: base 140 ft, the window max change q -> P(>= 140.3 + 1.0)
    p = model.crossing_prob(q, np.array([140.0]), 141.3)[0]
    assert p == pytest.approx(float((xs > 1.3).mean()), abs=0.004)


def test_point_forecast_edges_are_point_masses() -> None:
    q = np.full((1, 19), 1.0)
    assert model.exceed_prob(q, np.array([0.5]))[0] == pytest.approx(1.0)
    assert model.exceed_prob(q, np.array([1.5]))[0] == pytest.approx(0.0)
    assert not math.isnan(model.exceed_prob(q, np.array([1.0]))[0])
