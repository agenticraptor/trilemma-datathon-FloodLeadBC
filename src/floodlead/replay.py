"""Sumas Prairie overflow replay: every North Cedarville minor-stage event and when the overflow began.

Computed from the stored USGS observations (approved historical data), never hardcoded. Definitions:

- **Event**: a run of North Cedarville (usgs:12210700) levels >= minor stage (146.5 ft); runs less than 48 h
  apart are one event. `minor_first` is the first observation >= minor.
- **Stage crossings**: `action_first` is the first observation >= action stage (144.8 ft) in the 72 h before
  `minor_first` (the river can dip back below action before reaching minor, as on 2025-12-09/10);
  `moderate_first` / `major_first` are the first observations >= 148 / 150 ft within the event
  window [minor_first - 24 h, minor_last + 24 h]; the peak is the maximum in that window.
- **Overflow onset**: the Overflow at SR 544 gauge (usgs:12211195) reported only while water was flowing over
  the overflow path until 2026-10-01; since then it reports continuously at ~3.53 ft. Onset = the first record
  in [minor_first - 12 h, minor_last + 24 h] (before 2026-10-01), or the first record >= its NWS action stage
  (3.6 ft) after that date.
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg

CEDARVILLE = "usgs:12210700"
OVERFLOW = "usgs:12211195"
EVERSON = "usgs:12211200"
CEDARVILLE_STAGES_FT = {"action": 144.8, "minor": 146.5, "moderate": 148.0, "major": 150.0}
OVERFLOW_STAGES_FT = {"action": 3.6, "minor": 4.0}
EVERSON_ACTION_FT = 83.0
CONTINUOUS_FROM = datetime(2026, 10, 1, tzinfo=UTC)  # overflow gauge reports continuously from here on
EVENT_GAP = timedelta(hours=48)
ACTION_LOOKBACK = timedelta(hours=72)  # action_first = first record >= action stage in the 72 h before minor

CAVEATS = [
    "Approved historical USGS data, not what was visible in real time (the live feed lags by about 15-60 min and "
    "provisional values can change).",
    "A small number of events: the overflow gauge record begins in November 2015.",
    "Until 2026-10-01 the overflow gauge reported only while water was flowing, so its first record marks the onset; "
    "it now reports continuously, so onset is taken as its first record at or above its NWS action stage (3.6 ft).",
    "The overflow path can change after big floods (the 2021-11-28 overflow began almost exactly at minor stage, "
    "two weeks after the record November 2021 flood).",
    "The suggested personal level is the official NWS minor flood stage; the overflow statistics are empirical "
    "observations, not official thresholds. Follow EmergencyInfoBC, NWS Seattle and local orders.",
]


def _q(conn: psycopg.Connection, sql: str, params: tuple | dict) -> list[tuple]:
    return conn.execute(sql, params).fetchall()


def _iso(t: datetime | None) -> str | None:
    return None if t is None else t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _first_at_or_above(conn: psycopg.Connection, sid: str, ft: float, t0: datetime, t1: datetime
                       ) -> tuple[datetime, float] | None:
    r = _q(conn, "SELECT ts, raw_value FROM observations WHERE station_id = %s AND param = 'level' AND NOT is_sentinel"
                 " AND ts BETWEEN %s AND %s AND raw_value >= %s ORDER BY ts LIMIT 1", (sid, t0, t1, ft))
    return (r[0][0], r[0][1]) if r else None


def _level_at(conn: psycopg.Connection, sid: str, t: datetime) -> float | None:
    r = _q(conn, "SELECT raw_value FROM observations WHERE station_id = %s AND param = 'level' AND NOT is_sentinel"
                 " AND ts BETWEEN %s AND %s ORDER BY ts DESC LIMIT 1", (sid, t - timedelta(minutes=30), t))
    return r[0][0] if r else None


def minor_events(conn: psycopg.Connection) -> list[tuple[datetime, datetime]]:
    rows = _q(conn, "SELECT ts FROM observations WHERE station_id = %s AND param = 'level' AND NOT is_sentinel"
                    " AND raw_value >= %s ORDER BY ts", (CEDARVILLE, CEDARVILLE_STAGES_FT["minor"]))
    events: list[list[datetime]] = []
    for (ts,) in rows:
        if events and ts - events[-1][1] <= EVENT_GAP:
            events[-1][1] = ts
        else:
            events.append([ts, ts])
    return [(a, b) for a, b in events]


def overflow_record_begins(conn: psycopg.Connection) -> datetime | None:
    r = _q(conn, "SELECT min(ts) FROM observations WHERE station_id = %s AND param = 'level'", (OVERFLOW,))
    return r[0][0] if r else None


def compute(conn: psycopg.Connection) -> dict[str, Any]:
    begins = overflow_record_begins(conn)
    events_out: list[dict[str, Any]] = []
    for minor_first, minor_last in minor_events(conn):
        w0, w1 = minor_first - timedelta(hours=24), minor_last + timedelta(hours=24)
        action = _first_at_or_above(conn, CEDARVILLE, CEDARVILLE_STAGES_FT["action"],
                                    minor_first - ACTION_LOOKBACK, minor_first)
        moderate = _first_at_or_above(conn, CEDARVILLE, CEDARVILLE_STAGES_FT["moderate"], w0, w1)
        major = _first_at_or_above(conn, CEDARVILLE, CEDARVILLE_STAGES_FT["major"], w0, w1)
        # Peak: the highest level; peak_at is the first time it was reached, peak_until the last (plateaus).
        peak = _q(conn, "SELECT min(ts), max(ts), raw_value FROM observations WHERE station_id = %s AND param = 'level'"
                        " AND NOT is_sentinel AND ts BETWEEN %s AND %s AND raw_value = (SELECT max(raw_value)"
                        " FROM observations WHERE station_id = %s AND param = 'level' AND NOT is_sentinel"
                        " AND ts BETWEEN %s AND %s) GROUP BY raw_value", (CEDARVILLE, w0, w1, CEDARVILLE, w0, w1))
        everson = _first_at_or_above(conn, EVERSON, EVERSON_ACTION_FT, w0, w1)
        operating = begins is not None and begins <= minor_first - timedelta(hours=12)
        o0, o1 = minor_first - timedelta(hours=12), w1
        if o0 >= CONTINUOUS_FROM:
            onset = _first_at_or_above(conn, OVERFLOW, OVERFLOW_STAGES_FT["action"], o0, o1)
        else:
            r = _q(conn, "SELECT ts, raw_value FROM observations WHERE station_id = %s AND param = 'level'"
                         " AND NOT is_sentinel AND ts BETWEEN %s AND %s ORDER BY ts LIMIT 1", (OVERFLOW, o0, o1))
            onset = (r[0][0], r[0][1]) if r else None
        overflow = None
        if onset is not None:
            omax = _q(conn, "SELECT max(raw_value) FROM observations WHERE station_id = %s AND param = 'level'"
                            " AND NOT is_sentinel AND ts BETWEEN %s AND %s", (OVERFLOW, o0, o1))[0][0]
            overflow = {
                "first_record_at": _iso(onset[0]), "first_record_ft": onset[1],
                "cedarville_ft_at_onset": _level_at(conn, CEDARVILLE, onset[0]),
                "hours_after_minor": round((onset[0] - minor_first).total_seconds() / 3600, 2),
                "max_ft": omax,
            }
        note = None
        if not operating and begins is not None and begins <= w1:
            note = (f"The overflow gauge record begins during this event ({_iso(begins)}); it may not have been "
                    "operating at the onset, so this event is left out of the summary.")
        elif not operating:
            note = "Before the overflow gauge record (begins 2015-11-14)."
        events_out.append({
            "event_id": f"{minor_first:%Y-%m-%d}",
            "minor_first": _iso(minor_first), "minor_last": _iso(minor_last),
            "action_first": _iso(action[0]) if action else None,
            "moderate_first": _iso(moderate[0]) if moderate else None,
            "major_first": _iso(major[0]) if major else None,
            "peak_ft": peak[0][2] if peak else None, "peak_at": _iso(peak[0][0]) if peak else None,
            "peak_until": _iso(peak[0][1]) if peak else None,
            "everson_action_first": _iso(everson[0]) if everson else None,
            "overflow_gauge_operating": operating,
            "overflow": overflow,
            "note": note,
        })
    return {"generated_at": _iso(datetime.now(UTC)), "overflow_record_begins": _iso(begins),
            "events": events_out, "summary": summarise(events_out)}


def summarise(events: list[dict[str, Any]]) -> dict[str, Any]:
    op = [e for e in events if e["overflow_gauge_operating"]]
    ov = [e for e in op if e["overflow"]]
    no_ov = [e for e in op if not e["overflow"]]
    onset = sorted(e["overflow"]["cedarville_ft_at_onset"] for e in ov if e["overflow"]["cedarville_ft_at_onset"])
    hours = sorted(e["overflow"]["hours_after_minor"] for e in ov)

    def stats(xs: list[float]) -> dict[str, float] | None:
        return {"min": xs[0], "median": round(statistics.median(xs), 2), "max": xs[-1]} if xs else None

    peaks_with = sorted(e["peak_ft"] for e in ov if e["peak_ft"] is not None)
    peaks_without = sorted(e["peak_ft"] for e in no_ov if e["peak_ft"] is not None)

    def rng(xs: list[float]) -> dict[str, float] | None:
        return {"min": xs[0], "max": xs[-1]} if xs else None

    # Supervisor QA (addendum 2, item 1): the level at onset is not a trigger level (e.g. March 2026: the overflow
    # began on the falling limb, ~3 h after the peak). Suggest the official minor stage plus the rule the data supports.
    rule = sep = None
    if ov and hours:
        rule = (f"{len(ov)} of {len(op)} minor-stage events since Nov 2015 were followed by water on the overflow "
                f"path, a median {statistics.median(hours):.1f} h later ({hours[0]:.1f}–{hours[-1]:.1f} h).")
    if peaks_with and peaks_without:
        overlap = peaks_without[-1] >= peaks_with[0]
        sep = (f"Peaks {'overlap' if overlap else 'do not overlap'} (overflow {peaks_with[0]:.1f}–"
               f"{peaks_with[-1]:.1f} ft, no overflow {peaks_without[0]:.1f}–{peaks_without[-1]:.1f} ft): "
               + ("no single level separates them." if overlap else "but with so few events this is not a rule."))
    return {
        "events_total": len(events), "events_with_gauge": len(op), "events_with_overflow": len(ov),
        "events_without_overflow": len(no_ov),
        "max_peak_without_overflow_ft": peaks_without[-1] if peaks_without else None,
        "onset_cedarville_ft": stats(onset), "hours_after_minor": stats(hours),
        "peaks_with_overflow_ft": peaks_with, "peaks_without_overflow_ft": peaks_without,
        "peak_range_with_overflow_ft": rng(peaks_with), "peak_range_without_overflow_ft": rng(peaks_without),
        "separation_text": sep,
        "suggested_personal_level_ft": CEDARVILLE_STAGES_FT["minor"],
        "suggested_label": "NWS minor flood stage (official)",
        "suggested_text": rule,
        "onset_note": "The North Cedarville level when the overflow first appeared is not a trigger level: in March "
                      "2026 it first appeared on the falling limb, about 3 h after the peak.",
    }


def series(conn: psycopg.Connection, event: dict[str, Any]) -> dict[str, Any]:
    t0 = datetime.fromisoformat(event["minor_first"].replace("Z", "+00:00")) - timedelta(hours=36)
    t1 = datetime.fromisoformat(event["minor_last"].replace("Z", "+00:00")) + timedelta(hours=24)
    out: dict[str, list[list[Any]]] = {}
    for sid in (CEDARVILLE, OVERFLOW, EVERSON):
        rows = _q(conn, "SELECT ts, raw_value FROM observations WHERE station_id = %s AND param = 'level'"
                        " AND NOT is_sentinel AND ts BETWEEN %s AND %s ORDER BY ts", (sid, t0, t1))
        out[sid] = [[_iso(ts), v] for ts, v in rows]
    return {"event_id": event["event_id"], "window": {"start": _iso(t0), "end": _iso(t1)}, "units": "ft",
            "series": out}
