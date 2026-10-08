"""Baseline maths on synthetic series, and the issuer's leakage rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from floodlead import baselines as bl

STEP = timedelta(minutes=5)
T0 = datetime(2026, 9, 1, tzinfo=UTC)


def grid(y: np.ndarray) -> bl.Grid:
    return bl.Grid(T0, STEP, y.astype(float))


def _samples(model: str, y: np.ndarray, max_lead: int = 60) -> tuple[np.ndarray, float, float]:
    g = grid(y)
    d = len(y) - 1
    window, cap = 36, 72
    origins = np.arange(window, d - max_lead + 1, 12)
    E, _ = bl.error_paths(model, g, origins, max_lead, window, cap, 6)
    slope = float(bl.slopes(g.y, np.array([d]), window, bl.TREND_MIN_COVERAGE)[0])
    pp = bl.point_path(model, float(y[d]), 0.0 if np.isnan(slope) else slope, np.arange(1, max_lead + 1), cap)
    return pp[None, :] + E, float(y[d]), slope


def test_constant_series_gives_zero_width_intervals() -> None:
    for model in bl.MODELS:
        s, y_d, _ = _samples(model, np.full(3000, 2.5))
        (q, qm, pe), = bl.summarise(s, [24], {"rise:+0.25": y_d + 0.25, "at": y_d})
        assert set(q.values()) == {2.5} and set(qm.values()) == {2.5}
        assert pe == {"rise:+0.25": 0.0, "at": 1.0}


def test_random_walk_quantiles_and_exceedance_match_analytic() -> None:
    rng = np.random.default_rng(7)
    sigma = 0.01
    y = np.cumsum(rng.normal(0, sigma, 40000))
    s, y_d, _ = _samples("persistence-v1", y, max_lead=48)
    lead = 48
    (q, qm, pe), = bl.summarise(s, [lead], {"rise": y_d + 2 * sigma * np.sqrt(lead)})
    sd = sigma * np.sqrt(lead)
    # Level at the lead: Normal(y_d, sd). 0.05/0.95 quantiles are y_d -/+ 1.645 sd (tolerance 15 %).
    assert q["0.5"] == pytest.approx(y_d, abs=0.15 * sd)
    assert q["0.95"] - y_d == pytest.approx(1.645 * sd, rel=0.15)
    assert y_d - q["0.05"] == pytest.approx(1.645 * sd, rel=0.15)
    # Running maximum reaching +2 sd: reflection principle P = 2 * (1 - Phi(2)) = 0.0455 (discrete walk a bit
    # lower); accept 0.02-0.06.
    assert 0.02 <= pe["rise"] <= 0.06
    assert qm["0.5"] >= q["0.5"]


def test_trend_point_path_is_capped_at_6h_and_needs_coverage() -> None:
    y = np.arange(400) * 0.001  # +1 mm per 5 min
    g = grid(y)
    sl = bl.slopes(g.y, np.array([399]), 36, 0.5)[0]
    assert sl == pytest.approx(0.001)
    pp = bl.point_path("trend3h-v1", 1.0, sl, np.array([1, 72, 100, 600]), 72)
    assert pp.tolist() == pytest.approx([1.001, 1.072, 1.072, 1.072])
    sparse = y.copy()
    sparse[380:399] = np.nan  # 19 of the last 37 points missing → < 50 % coverage
    assert np.isnan(bl.slopes(sparse, np.array([399]), 36, 0.5)[0])
    gappy = y.copy()
    gappy[385:390] = np.nan  # a small gap still gives the exact slope of a straight line
    assert bl.slopes(gappy, np.array([399]), 36, 0.5)[0] == pytest.approx(0.001)


def test_ffill_is_limited() -> None:
    y = np.array([1.0, np.nan, np.nan, np.nan, 2.0])
    assert bl.ffill(y, 2).tolist()[:3] == [1.0, 1.0, 1.0] and np.isnan(bl.ffill(y, 2)[3])
