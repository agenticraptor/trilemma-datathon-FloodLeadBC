"""Relay v2 / trust table rules (protocol amendment 2)."""

from datetime import UTC, datetime, timedelta

import pytest

from floodlead import trust


@pytest.mark.parametrize(("k", "n", "lo", "hi"), [(7, 18, 0.17, 0.64), (6, 8, 0.35, 0.97), (4, 8, 0.16, 0.84),
                                                  (4, 4, 0.40, 1.00), (5, 5, 0.48, 1.00), (3, 3, 0.29, 1.00)])
def test_clopper_pearson_matches_published_intervals(k: int, n: int, lo: float, hi: float) -> None:
    a, b = trust.clopper_pearson(k, n)
    assert round(a, 2) == lo and round(b, 2) == hi


T = datetime(2021, 11, 14, tzinfo=UTC)


def test_episodes_split_on_gaps_and_continuous_period_threshold() -> None:
    rows = [(T, 3.8), (T + timedelta(hours=1), 5.2), (T + timedelta(days=5), 4.1),
            (datetime(2026, 10, 2, tzinfo=UTC), 3.53), (datetime(2026, 10, 3, tzinfo=UTC), 3.7)]
    eps = trust.episodes(rows)
    assert [(e.onset, e.peak_ft, e.large) for e in eps] == [
        (T, 5.2, True), (T + timedelta(days=5), 4.1, False), (datetime(2026, 10, 3, tzinfo=UTC), 3.7, False)]
    assert eps[0].first_ge[5.0] == T + timedelta(hours=1) and eps[1].first_ge[5.0] is None


def test_score_counts_alerts_misses_and_leads() -> None:
    eps = trust.episodes([(T + timedelta(hours=10), 6.0), (T + timedelta(days=30), 4.2)])
    alerts = [{"at": T, "window": (T - timedelta(hours=12), T + timedelta(hours=40)), "label": "a"},
              {"at": T + timedelta(days=10), "window": (T + timedelta(days=10), T + timedelta(days=11)),
               "label": "false alarm"}]
    s = trust.score(alerts, eps)
    assert (s["alerts"], s["followed_by_overflow"], s["followed_by_large"]) == (2, 1, 1)
    assert s["list"][0]["lead_h"] == 10.0 and s["list"][1]["followed_by_overflow"] is False
    assert [m["peak_ft"] for m in s["missed"]] == [4.2]
