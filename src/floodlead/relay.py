"""Relay and trigger replay: what model-free rules built only from archived official products and gauge readings
would have done in every North Cedarville minor-stage event since the SR 544 overflow gauge began (Stage 3
addendum 1, item 3.2; D-03.16). This is "relay value"; a model must not take credit for it.

Tiers (pre-registered in docs/evaluation-protocol.md; the first fire of each tier in the event window):
- heads-up: an NWS flood watch (VTEC significance A, phenomena FA or FL) whose segment names Whatcom County, issued
  from 7 days before the minor crossing to its end. (BC River Forecast Centre watches are not archived: their licence
  record is still yellow, so this half of the rule cannot be replayed.)
- prepare: an NWS North Cedarville (NRKW1) flood warning product forecasting at least minor stage (H-VTEC severity
  1-3 or a forecast crest >= 146.5 ft), or an NWS warning segment naming the Everson overflow.
- move: the SR 544 overflow gauge's onset (first record before 2026-10-01, then >= 3.6 ft), or North Cedarville
  reaching minor stage (146.5 ft) while rising (the event's minor crossing).
Each fire is flagged daylight or night at Abbotsford (floodlead.sun). Events with no overflow count as false alarms for
any tier that fired. Lead = overflow onset - fire time.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg

from floodlead import replay, sun

MINOR_FT = 146.5
OVERFLOW_GAUGE_BEGINS = datetime(2015, 11, 14, tzinfo=UTC)

# Comparators from docs/research/fraser-valley-flood-warning-status-quo.md (times PST -> UTC; ranges where the
# sources give one). Reconstructed estimates, not published by any agency.
ABBOTSFORD = {
    "2021-11-14": {"first_alert": ("2021-11-15T08:30Z", "2021-11-15T08:30Z"),
                   "first_order": ("2021-11-16T01:00Z", "2021-11-16T04:00Z"),
                   "note": "first alert touching Sumas Prairie ~12:30 AM Nov 15; first orders evening Nov 15"},
    "2025-12-10": {"first_alert": ("2025-12-11T00:00Z", "2025-12-11T01:20Z"),
                   "first_order": ("2025-12-11T07:00Z", "2025-12-11T07:00Z"),
                   "note": "alerts ~4:00-5:20 PM Dec 10; order ~11 PM Dec 10 (371 properties)"},
}
SEVEN_HOUR_RULE = timedelta(hours=7)


def _t(s: str | None) -> datetime | None:
    return None if s is None else datetime.fromisoformat(s.replace("Z", "+00:00"))


def _fire(t: datetime | None, what: str | None, onset: datetime | None) -> dict[str, Any] | None:
    if t is None:
        return None
    return {"at": t, "what": what, "daylight": sun.is_daylight(t),
            "lead_before_overflow_h": None if onset is None else round((onset - t).total_seconds() / 3600, 2)}


def tiers(conn: psycopg.Connection, ev: dict[str, Any]) -> dict[str, Any]:
    minor_first, minor_last = _t(ev["minor_first"]), _t(ev["minor_last"])
    assert minor_first is not None and minor_last is not None
    onset = _t((ev.get("overflow") or {}).get("first_record_at"))
    lo, hi = minor_first - timedelta(days=7), minor_last
    watch = conn.execute(
        "SELECT issued_at, phenomena || '.' || significance || ' ' || action FROM nws_vtec WHERE significance = 'A'"
        " AND phenomena IN ('FA', 'FL') AND segment_head ILIKE '%%Whatcom%%' AND issued_at BETWEEN %s AND %s"
        " ORDER BY issued_at LIMIT 1", (lo, hi)).fetchone()
    prep = conn.execute(
        "SELECT issued_at, CASE WHEN nwsli = 'NRKW1' THEN 'NRKW1 ' ELSE 'Everson overflow ' END || phenomena || '.'"
        " || significance || ' ' || action FROM nws_vtec WHERE significance = 'W' AND action NOT IN ('CAN', 'EXP')"
        " AND issued_at BETWEEN %s AND %s AND ((nwsli = 'NRKW1' AND (severity IN ('1', '2', '3')"
        " OR forecast_crest_ft >= %s)) OR (segment_head ILIKE '%%Everson%%' AND segment_head ILIKE '%%overflow%%'))"
        " ORDER BY issued_at LIMIT 1", (lo, hi, MINOR_FT)).fetchone()
    move_t, move_what = minor_first, "North Cedarville reached minor stage (146.5 ft), rising"
    if onset is not None and onset < move_t:
        move_t, move_what = onset, "SR 544 overflow onset"
    out = {"event_id": ev["event_id"], "minor_first": minor_first, "peak_ft": ev.get("peak_ft"),
           "overflow": onset is not None, "overflow_onset": onset,
           "heads_up": _fire(watch[0] if watch else None, watch[1] if watch else None, onset),
           "prepare": _fire(prep[0] if prep else None, prep[1] if prep else None, onset),
           "move": _fire(move_t, move_what, onset)}
    ab = ABBOTSFORD.get(ev["event_id"])
    if ab:
        out["abbotsford"] = {k: [_t(v[0]), _t(v[1])] if isinstance(v, tuple) else v for k, v in ab.items()}
    if onset is not None:
        out["seven_hour_rule_arrival"] = onset + SEVEN_HOUR_RULE
    return out


def replay_all(conn: psycopg.Connection) -> dict[str, Any]:
    conn.execute("SET statement_timeout = '10min'")
    evs = [e for e in replay.compute(conn)["events"] if e["overflow_gauge_operating"]]
    rows = [tiers(conn, e) for e in evs]
    summ: dict[str, Any] = {}
    for tier in ("heads_up", "prepare", "move"):
        fired = [r for r in rows if r[tier] is not None]
        hits = [r for r in fired if r["overflow"]]
        missed = [r for r in rows if r["overflow"] and r[tier] is None]
        leads = sorted(r[tier]["lead_before_overflow_h"] for r in hits)
        summ[tier] = {"events": len(rows), "overflow_events": sum(r["overflow"] for r in rows), "fired": len(fired),
                      "hits": len(hits), "false_alarms": len(fired) - len(hits), "missed": len(missed),
                      "far": round((len(fired) - len(hits)) / len(fired), 3) if fired else None,
                      "pod": round(len(hits) / (len(hits) + len(missed)), 3) if hits or missed else None,
                      "lead_before_overflow_h": leads,
                      "daylight_share": round(sum(r[tier]["daylight"] for r in fired) / len(fired), 3) if fired
                      else None}
    return {"events": rows, "summary": summ, "method": (__doc__ or "").strip()}
