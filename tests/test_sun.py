"""Sunrise/sunset at Abbotsford (49.05, -122.30) against api.sunrise-sunset.org, fetched Oct 9, 2026 (UTC)."""

from datetime import UTC, date, datetime

from floodlead import sun


def test_known_days_within_4_minutes() -> None:
    # reference: Dec 10, 2025 sunrise 15:50:58Z, sunset 00:13:30Z; Jun 21, 2025 sunrise 12:02:46Z, sunset 04:19:31Z
    for d, rise, sset in ((date(2025, 12, 10), datetime(2025, 12, 10, 15, 50, 58, tzinfo=UTC),
                           datetime(2025, 12, 11, 0, 13, 30, tzinfo=UTC)),
                          (date(2025, 6, 21), datetime(2025, 6, 21, 12, 2, 46, tzinfo=UTC),
                           datetime(2025, 6, 22, 4, 19, 31, tzinfo=UTC))):
        r, s = sun.sunrise_sunset(d)
        assert abs((r - rise).total_seconds()) <= 240 and abs((s - sset).total_seconds()) <= 240


def test_daylight_flag() -> None:
    assert sun.is_daylight(datetime(2025, 12, 10, 20, 0, tzinfo=UTC))  # noon PST
    assert not sun.is_daylight(datetime(2025, 12, 11, 7, 0, tzinfo=UTC))  # 11 PM PST
