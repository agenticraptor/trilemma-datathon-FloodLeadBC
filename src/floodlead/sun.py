"""Sunrise and sunset (NOAA solar position approximation, accurate to about a minute at mid-latitudes)."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

ABBOTSFORD = (49.05, -122.30)


def sunrise_sunset(d: date, lat: float = ABBOTSFORD[0], lon: float = ABBOTSFORD[1]) -> tuple[datetime, datetime]:
    """UTC sunrise and sunset on calendar day d at (lat, lon); zenith 90.833 deg (refraction and solar disc)."""
    n = d.timetuple().tm_yday
    g = 2 * math.pi / 365 * (n - 1)  # fractional year at noon is close enough for times to ~1 min
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g)
                    - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    phi = math.radians(lat)
    ha = math.degrees(math.acos(math.cos(math.radians(90.833)) / (math.cos(phi) * math.cos(decl))
                                - math.tan(phi) * math.tan(decl)))
    base = datetime(d.year, d.month, d.day, tzinfo=UTC)
    rise = base + timedelta(minutes=720 - 4 * (lon + ha) - eqt)
    sset = base + timedelta(minutes=720 - 4 * (lon - ha) - eqt)
    return rise, sset


def is_daylight(t: datetime, lat: float = ABBOTSFORD[0], lon: float = ABBOTSFORD[1]) -> bool:
    local_day = (t + timedelta(hours=-8)).date()  # Pacific standard time day; both neighbours checked below
    for d in (local_day - timedelta(days=1), local_day, local_day + timedelta(days=1)):
        r, s = sunrise_sunset(d, lat, lon)
        if r <= t <= s:
            return True
    return False
