"""Unit conversion to SI and the sentinel rule."""

from __future__ import annotations

FT_TO_M = 0.3048
CFS_TO_CMS = 0.028316846592

# raw unit -> (param, factor to SI)
_FACTORS: dict[str, float] = {
    "m": 1.0,
    "m3/s": 1.0,
    "ft": FT_TO_M,
    "ft3/s": CFS_TO_CMS,
}

# Documented "no data" codes: ECCC real-time CSV uses +/-99999, USGS legacy NWIS -999999,
# NWS/USGS -9999.
SENTINEL_CODES = frozenset({99999.0, -99999.0, -999999.0, 999999.0, -9999.0})

# Levels (m or ft) never legitimately reach 9999. Flows can: the Fraser at Hope has exceeded
# 10,000 m3/s in freshet, and the Nooksack at Everson reached 52,300 ft3/s in 2021. So the
# magnitude rule is applied to levels only; flows are flagged on the documented codes and on
# |value| >= 99999 (an order of magnitude above any river in scope).
LEVEL_SENTINEL_ABS = 9999.0
FLOW_SENTINEL_ABS = 99999.0


def is_sentinel(param: str, raw_value: float | None) -> bool:
    if raw_value is None:
        return False
    if raw_value in SENTINEL_CODES:
        return True
    limit = LEVEL_SENTINEL_ABS if param == "level" else FLOW_SENTINEL_ABS
    return abs(raw_value) >= limit


def to_si(raw_value: float | None, raw_unit: str) -> float | None:
    if raw_value is None:
        return None
    try:
        return raw_value * _FACTORS[raw_unit]
    except KeyError as e:
        raise ValueError(f"unknown unit {raw_unit!r}") from e


def si_value(param: str, raw_value: float | None, raw_unit: str) -> tuple[float | None, bool]:
    """Return (SI value or None for sentinels, is_sentinel)."""
    sentinel = is_sentinel(param, raw_value)
    return (None if sentinel else to_si(raw_value, raw_unit)), sentinel
