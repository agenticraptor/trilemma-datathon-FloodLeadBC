"""Typical yearly peak (Stage 3): computation on a fixture and the datum-check rule."""

from floodlead import typical_peaks as tp

# 12 years of annual maxima in the period, one ice-affected year, and two years outside the period
PEAKS = [(y, 3.0 + 0.1 * (y - 2010), None) for y in range(2010, 2022)] + [(2022, 9.9, "Ice Conditions"),
                                                                         (1999, 8.0, None), (2025, 8.0, None)]
SEASON = {"first_year": 2020, "last_year": 2024, "n_days": 150, "min": 1.0, "median": 1.3, "max": 1.6}


def test_median_over_the_period_without_ice_years() -> None:
    value, years = tp.typical(PEAKS)
    assert years == list(range(2010, 2022))  # 1999, 2025 outside 2005-2024; 2022 ice-affected
    assert value == (3.5 + 3.6) / 2  # even count: mean of the middle two


def test_ok_when_current_levels_sit_in_the_seasonal_range() -> None:
    r = tp.judge("eccc:X", PEAKS, {"n": 8000, "median": 1.2, "max": 1.9}, SEASON)
    assert (r.status, r.value_m, r.n_years, r.first_year, r.last_year) == ("ok", 3.55, 12, 2010, 2021)


def test_insufficient_below_ten_years() -> None:
    r = tp.judge("eccc:X", PEAKS[:9], {"n": 1, "median": 1.2, "max": 1.3}, SEASON)
    assert r.status == "insufficient" and r.value_m is None and "9 years" in r.reason


def test_datum_shift_is_rejected() -> None:
    # today's levels 10 m above anything seen in the same season: the gauge datum moved
    r = tp.judge("eccc:X", PEAKS, {"n": 8000, "median": 11.2, "max": 11.5}, SEASON)
    assert r.status == "rejected" and r.value_m is None and "datum change likely" in r.reason
    # inside the tolerance (max(0.5, half the 0.6 m range) = 0.5 m) is not a datum change
    assert tp.judge("eccc:X", PEAKS, {"n": 1, "median": 2.05, "max": 2.1}, SEASON).status == "ok"
    assert tp.judge("eccc:X", PEAKS, {"n": 1, "median": 2.15, "max": 2.2}, SEASON).status == "rejected"


def test_flags() -> None:
    assert tp.judge("eccc:X", PEAKS, None, SEASON).status == "flagged"  # no live data to check against
    assert tp.judge("eccc:X", PEAKS, {"n": 1, "median": 1.2, "max": 1.3}, None).status == "flagged"  # no history
    r = tp.judge("eccc:X", PEAKS, {"n": 1, "median": 1.5, "max": 3.6}, SEASON)  # reached it in the last 30 days
    assert r.status == "flagged" and r.value_m == 3.55 and "reached" in r.reason
