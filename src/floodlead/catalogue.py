"""Event catalogue: the labels and comparators Stage 4 is judged on (Stage 3 part 2 item 6; D-03.18).

Nooksack (North Cedarville, NRKW1): every minor-stage event (the replay's definition, D-02.4: runs >= 146.5 ft, runs
under 48 h apart merged), with its first crossing of action/minor/moderate/major, crest, the SR 544 overflow onset
where that gauge existed, and the first NWS North Cedarville flood warning issued from 72 h before the minor crossing
to the end of the event, with its forecast flood begin, crest time and crest value.

BC (typical yearly peak, typical-peak-v1): from ECCC history, (a) every year whose annual instantaneous maximum level
reached the station's typical yearly peak, with its date and time; (b) every day whose daily mean reached it. Daily
means smooth instantaneous peaks, so (b) undercounts; (a) has at most one per year. Live 5-min data (Sep 2026 on) are
in `observations`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg

from floodlead import replay, typical_peaks


def _t(s: str | None) -> datetime | None:
    return None if s is None else datetime.fromisoformat(s.replace("Z", "+00:00"))


def nooksack(conn: psycopg.Connection) -> list[dict[str, Any]]:
    conn.execute("SET statement_timeout = '15min'")
    out = []
    for e in replay.compute(conn)["events"]:
        mf, ml = _t(e["minor_first"]), _t(e["minor_last"])
        assert mf is not None and ml is not None
        w = conn.execute(
            "SELECT v.issued_at, v.action, v.severity, v.flood_begin, v.flood_crest, v.forecast_crest_ft, p.pil,"
            " p.wmo FROM nws_vtec v JOIN nws_products p USING (product_id) WHERE v.nwsli = 'NRKW1'"
            " AND v.phenomena = 'FL' AND v.significance = 'W' AND v.action = 'NEW' AND v.issued_at BETWEEN %s AND %s"
            " ORDER BY v.issued_at LIMIT 1", (mf - timedelta(hours=72), ml)).fetchone()
        first = None
        if w:
            first = {"issued_at": w[0], "action": w[1], "severity": w[2], "forecast_flood_begin": w[3],
                     "forecast_crest_at": w[4], "forecast_crest_ft": w[5], "product": f"{w[6]} {w[7]}",
                     "lead_before_minor_h": round((mf - w[0]).total_seconds() / 3600, 2)}
        ov = e.get("overflow") or {}
        out.append({"event_id": e["event_id"], "gauge": "usgs:12210700", "nwsli": "NRKW1",
                    "action_first": e["action_first"], "minor_first": e["minor_first"], "minor_last": e["minor_last"],
                    "moderate_first": e["moderate_first"], "major_first": e["major_first"],
                    "crest_ft": e["peak_ft"], "crest_at": e["peak_at"],
                    "overflow_gauge_operating": e["overflow_gauge_operating"],
                    "overflow_onset": ov.get("first_record_at"), "overflow_max_ft": ov.get("max_ft"),
                    "first_nws_warning": first, "wy": (mf.year + 1 if mf.month >= 10 else mf.year)})
    return out


def bc(conn: psycopg.Connection) -> dict[str, Any]:
    conn.execute("SET statement_timeout = '15min'")
    tp = {sid.split(":", 1)[1]: v for sid, v in conn.execute(
        "SELECT station_id, value_m FROM typical_peaks WHERE method = %s AND status IN ('ok', 'flagged')",
        (typical_peaks.METHOD,)).fetchall()}
    annual = [{"station": f"eccc:{s}", "year": y, "peak_at": at, "peak_m": v, "typical_peak_m": tp[s]}
              for s, y, at, v in conn.execute(
                  "SELECT station_number, year, peak_at, value FROM eccc_annual_peaks WHERE data_type = 'level'"
                  " AND peak_code = 'max' AND station_number = ANY(%s) ORDER BY 1, 2", (list(tp),)).fetchall()
              if v >= tp[s]]
    days = conn.execute(
        "SELECT d.station_number, count(*), min(d.date), max(d.date) FROM eccc_daily d JOIN (SELECT"
        " split_part(station_id, ':', 2) AS s, value_m FROM typical_peaks WHERE method = %s AND status IN ('ok',"
        " 'flagged')) t ON t.s = d.station_number WHERE d.level >= t.value_m GROUP BY 1 ORDER BY 1",
        (typical_peaks.METHOD,)).fetchall()
    return {"method": typical_peaks.METHOD, "stations": len(tp),
            "annual_peak_crossings": annual,
            "daily_mean_days_at_or_above": [{"station": f"eccc:{s}", "days": n, "first": a, "last": b}
                                            for s, n, a, b in days],
            "generated_at": datetime.now(UTC)}
