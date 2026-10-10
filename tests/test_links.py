"""Travel-time estimators on a synthetic pair with a known 5 h delay (synthetic, labelled)."""

import numpy as np

from floodlead.history import links


def test_known_delay_is_recovered() -> None:
    rng = np.random.default_rng(1)
    n = 5000
    up = np.cumsum(rng.normal(0, 0.05, n))
    for c in (800, 2100, 3600, 4500):  # four flood pulses
        up += 3 * np.exp(-0.5 * ((np.arange(n) - c) / 6) ** 2)
    down = np.roll(up, 5) * 0.8 + rng.normal(0, 0.01, n)
    down[:5] = np.nan
    months = np.full(n, 11)
    rc = links.rise_correlation(up, down, months, 12)
    assert rc["lag_h"] == 5 and rc["r"] > 0.9
    pk = links.peak_lags(up, down, window=48, sep=72)
    assert pk["n"] >= 4 and pk["median_h"] == 5
