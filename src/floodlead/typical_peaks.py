"""Typical yearly peak for BC gauges (Stage 3, part 1 item 4; D-03.7).

value = median of the annual instantaneous maximum water level over 2005-2024 (ECCC annual peaks, HYDAT), with at
least 10 years; levels marked "Ice Conditions" are left out. It is reached in about half of years. It is
FloodLead-derived from ECCC records, not an official flood level, and is stored apart from NOAA's thresholds.

Datum check (a gauge datum change makes old peaks meaningless against today's levels): today's 30-day median live level
is compared with the daily mean levels for the same calendar days in the last 5 years of ECCC daily history.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

METHOD = "typical-peak-v1"
FIRST_YEAR, LAST_YEAR = 2005, 2024  # 20 years; approved HYDAT ends in 2024 (probed Oct 9)
MIN_YEARS = 10
EXCLUDE_SYMBOLS = frozenset({"Ice Conditions"})
SEASON_YEARS = 5
SEASON_DAYS = 30
TOL_MIN_M = 0.5
LABEL = ("Typical yearly peak (reached in about half of years): FloodLead-derived from ECCC records, not an official "
         "flood level")


@dataclass
class Result:
    station_id: str
    status: str
    value_m: float | None
    n_years: int
    first_year: int | None
    last_year: int | None
    reason: str | None
    checks: dict[str, Any] = field(default_factory=dict)


def typical(peaks: list[tuple[int, float, str | None]]) -> tuple[float | None, list[int]]:
    """Median of the annual maximum levels in the period, ice-affected years left out."""
    use = sorted((y, v) for y, v, sym in peaks if FIRST_YEAR <= y <= LAST_YEAR and sym not in EXCLUDE_SYMBOLS)
    if not use:
        return None, []
    return statistics.median(v for _, v in use), [y for y, _ in use]


def judge(station_id: str, peaks: list[tuple[int, float, str | None]], current: dict[str, float] | None,
          season: dict[str, float] | None) -> Result:
    value, years = typical(peaks)
    n = len(years)
    base = dict(station_id=station_id, n_years=n, first_year=years[0] if years else None,
                last_year=years[-1] if years else None)
    checks: dict[str, Any] = {"current_30d": current, "same_season_history": season}
    if n < MIN_YEARS or value is None:
        return Result(status="insufficient", value_m=None, reason=f"{n} years of annual peaks in "
                      f"{FIRST_YEAR}-{LAST_YEAR}; at least {MIN_YEARS} needed", checks=checks, **base)
    v = round(value, 3)
    if current is None:
        return Result(status="flagged", value_m=v, reason="no live level in the last 30 days to check the datum",
                      checks=checks, **base)
    if season is None:
        return Result(status="flagged", value_m=v, reason="no daily level history for this season to check the "
                      "datum against", checks=checks, **base)
    tol = max(TOL_MIN_M, 0.5 * (season["max"] - season["min"]))
    checks["tolerance_m"] = round(tol, 3)
    if not season["min"] - tol <= current["median"] <= season["max"] + tol:
        return Result(status="rejected", value_m=None, checks=checks, **base,
                      reason=(f"datum change likely: the 30-day median level {current['median']:.3f} m is outside "
                              f"the same-season range {season['min']:.3f}-{season['max']:.3f} m of daily means in "
                              f"{season['first_year']}-{season['last_year']} by more than {tol:.2f} m"))
    if current["max"] >= v:
        return Result(status="flagged", value_m=v, checks=checks, **base,
                      reason="the level reached this typical yearly peak in the last 30 days; check before use")
    return Result(status="ok", value_m=v, reason=None, checks=checks, **base)


def _season_window(today: date, year: int) -> tuple[date, date]:
    end = today.replace(year=year) if not (today.month == 2 and today.day == 29) else date(year, 2, 28)
    return end - timedelta(days=SEASON_DAYS - 1), end


def compute(conn: psycopg.Connection, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    conn.execute("SET statement_timeout = '10min'")
    stations = [r[0] for r in conn.execute(
        "SELECT station_id FROM stations WHERE source = 'eccc' AND 'level' = ANY(params) ORDER BY 1").fetchall()]
    peaks: dict[str, list[tuple[int, float, str | None]]] = {}
    for stn, y, v, sym in conn.execute(
            "SELECT station_number, year, value, symbol FROM eccc_annual_peaks WHERE data_type = 'level'"
            " AND peak_code = 'max'").fetchall():
        peaks.setdefault(f"eccc:{stn}", []).append((y, v, sym))
    t0 = now - timedelta(days=30)  # a constant bound: chunk exclusion on the hypertable (F3)
    current = {sid: {"n": n, "median": round(md, 3), "max": round(mx, 3)} for sid, n, md, mx in conn.execute(
        "SELECT station_id, count(*), percentile_cont(0.5) WITHIN GROUP (ORDER BY value), max(value) FROM observations"
        " WHERE param = 'level' AND NOT is_sentinel AND value IS NOT NULL AND ts > %s AND ts <= %s"
        " AND station_id LIKE 'eccc:%%' GROUP BY station_id", (t0, now)).fetchall()}
    # same calendar window in each of the last SEASON_YEARS years that have daily levels in it
    season: dict[str, dict[str, Any]] = {}
    windows = [_season_window(now.date(), y) for y in range(LAST_YEAR - 14, LAST_YEAR + 1)]
    vals: dict[str, dict[int, list[float]]] = {}
    for stn, d, lv in conn.execute(
            "SELECT station_number, date, level FROM eccc_daily WHERE level IS NOT NULL AND date >= %s"
            " AND (" + " OR ".join(["date BETWEEN %s AND %s"] * len(windows)) + ")",
            (windows[0][0], *[x for w in windows for x in w])).fetchall():
        vals.setdefault(f"eccc:{stn}", {}).setdefault(d.year, []).append(lv)
    for sid, by_year in vals.items():
        yrs = sorted(y for y, v in by_year.items() if len(v) >= 10)[-SEASON_YEARS:]
        if yrs:
            allv = [x for y in yrs for x in by_year[y]]
            season[sid] = {"first_year": yrs[0], "last_year": yrs[-1], "n_days": len(allv),
                           "min": round(min(allv), 3), "median": round(statistics.median(allv), 3),
                           "max": round(max(allv), 3)}
    results = [judge(sid, peaks.get(sid, []), current.get(sid), season.get(sid)) for sid in stations]
    with conn.transaction():
        conn.execute("DELETE FROM typical_peaks WHERE method = %s", (METHOD,))
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO typical_peaks (method, station_id, status, value_m, n_years, first_year, last_year,"
                " reason, checks, computed_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [(METHOD, r.station_id, r.status, r.value_m, r.n_years, r.first_year, r.last_year, r.reason,
                  Jsonb(r.checks), now) for r in results])
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    return {"method": METHOD, "stations": len(results), "counts": counts}


def card_block(conn: psycopg.Connection) -> dict[str, Any] | None:
    """The thresholds and their provenance as they go into the model cards' params (D-03.8): ok values only."""
    rows = conn.execute(
        "SELECT station_id, value_m, n_years, first_year, last_year FROM typical_peaks WHERE method = %s"
        " AND status = 'ok' ORDER BY station_id", (METHOD,)).fetchall()
    if not rows:
        return None
    return {"method": METHOD, "label": LABEL,
            "statistic": "median of the annual instantaneous maximum water level",
            "source": "ECCC hydrometric-annual-peaks (HYDAT, OGL-Canada), api.weather.gc.ca",
            "period": [FIRST_YEAR, LAST_YEAR], "min_years": MIN_YEARS, "excluded_symbols": sorted(EXCLUDE_SYMBOLS),
            "datum_check": f"30-day median live level within the same-season range of daily means of the last "
                           f"{SEASON_YEARS} years, +/- max({TOL_MIN_M} m, half that range)",
            "values": {sid: {"level_m": round(v, 3), "n_years": n, "years": [a, b]} for sid, v, n, a, b in rows}}
