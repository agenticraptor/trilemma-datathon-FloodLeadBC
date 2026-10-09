"""How accurate were the official forecasts? A scorecard of archived NWS river flood products (Stage 3 addendum 1,
item 3.1; D-03.15).

Inputs: every archived NWS Seattle FLW/FLS product (IEM) with an H-VTEC forecast point among NRKW1, NKSW1, NREW1 and
NOEW1, and our USGS 15-min record of the same gauge (feet, as published).

An official event is one VTEC flood-warning series (phenomena FL, significance W, ETN) at one point. For each
product in it with a forecast crest in its text:
- lead (h) = observed crest time - product issuance (negative: issued after the crest);
- crest error (ft) = forecast crest - observed crest (the event's maximum 15-min stage);
- crest timing error (h) = H-VTEC forecast crest time - observed crest time;
- category right? = NWS category of the forecast crest == category of the observed crest;
- flood-begin error (h) = H-VTEC forecast flood begin - observed first crossing of minor (flood) stage.
For each event: the first warning's lead before the observed minor crossing, and when the first "major" product came
(H-VTEC severity 3) relative to the overflow onset at SR 544 (North Cedarville events only; the onset definition of the
replay, D-02.4).
The observed crest window is [first product - 12 h, last product + 48 h]. Categories use today's NWS stages for each
point (stations.official_thresholds); NWS stages can change over the years, which this does not model.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

POINTS = {"NRKW1": "usgs:12210700", "NKSW1": "usgs:12213100", "NREW1": "usgs:12211200", "NOEW1": "usgs:12211195"}
LEAD_BINS = ((-1e9, 0, "after the crest"), (0, 6, "0-6 h"), (6, 12, "6-12 h"), (12, 24, "12-24 h"),
             (24, 48, "24-48 h"), (48, 1e9, "48 h +"))
CATS = ("action", "minor", "moderate", "major")
OVERFLOW = "usgs:12211195"
OVERFLOW_ACTION_FT = 3.6
OVERFLOW_CONTINUOUS_FROM = datetime(2026, 10, 1, tzinfo=UTC)


def category(stage_ft: float | None, stages: dict[str, float]) -> str:
    if stage_ft is None:
        return "unknown"
    cat = "below action"
    for c in CATS:
        if c in stages and stage_ft >= stages[c]:
            cat = c
    return cat


def lead_bin(h: float) -> str:
    return next(lab for lo, hi, lab in LEAD_BINS if lo <= h < hi)


@dataclass
class Obs:
    crest_ft: float
    crest_at: datetime
    minor_cross: datetime | None
    moderate_cross: datetime | None
    major_cross: datetime | None


def observe(series: list[tuple[datetime, float]], stages: dict[str, float]) -> Obs | None:
    if not series:
        return None
    t_c, v_c = max(series, key=lambda x: x[1])

    def first_at(level: float | None) -> datetime | None:
        if level is None:
            return None
        return next((t for t, v in series if v >= level), None)

    return Obs(v_c, t_c, first_at(stages.get("minor")), first_at(stages.get("moderate")), first_at(stages.get("major")))


def score_event(products: list[dict[str, Any]], obs: Obs, stages: dict[str, float],
                overflow_onset: datetime | None) -> dict[str, Any]:
    rows = []
    for p in products:
        lead = (obs.crest_at - p["issued_at"]).total_seconds() / 3600
        r = {"issued_at": p["issued_at"], "action": p["action"], "severity": p["severity"], "lead_h": round(lead, 2),
             "lead_bin": lead_bin(lead), "forecast_crest_ft": p["forecast_crest_ft"],
             "forecast_crest_at": p["flood_crest"], "forecast_flood_begin": p["flood_begin"]}
        if p["forecast_crest_ft"] is not None:
            r["crest_error_ft"] = round(p["forecast_crest_ft"] - obs.crest_ft, 2)
            r["category_forecast"] = category(p["forecast_crest_ft"], stages)
            r["category_right"] = r["category_forecast"] == category(obs.crest_ft, stages)
        if p["flood_crest"] is not None:
            r["crest_time_error_h"] = round((p["flood_crest"] - obs.crest_at).total_seconds() / 3600, 2)
        if p["flood_begin"] is not None and obs.minor_cross is not None:
            r["flood_begin_error_h"] = round((p["flood_begin"] - obs.minor_cross).total_seconds() / 3600, 2)
        rows.append(r)
    first = products[0]
    major = next((p for p in products if p["severity"] == "3"), None)
    ev = {"first_issued_at": first["issued_at"], "first_forecast_crest_ft": first["forecast_crest_ft"],
          "observed_crest_ft": obs.crest_ft, "observed_crest_at": obs.crest_at,
          "observed_category": category(obs.crest_ft, stages),
          "observed_minor_cross": obs.minor_cross, "observed_moderate_cross": obs.moderate_cross,
          "observed_major_cross": obs.major_cross,
          "first_warning_lead_before_minor_h": None if obs.minor_cross is None else
          round((obs.minor_cross - first["issued_at"]).total_seconds() / 3600, 2),
          "first_major_product_at": major["issued_at"] if major else None,
          "overflow_onset": overflow_onset,
          "major_product_after_overflow_onset_h": None if not (major and overflow_onset) else
          round((major["issued_at"] - overflow_onset).total_seconds() / 3600, 2),
          "products": rows}
    return ev


def summarise(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_bin: dict[str, list[dict[str, Any]]] = {}
    ev_in_bin: dict[str, set[int]] = {}
    for i, e in enumerate(events):
        for r in e["products"]:
            if "crest_error_ft" in r:
                by_bin.setdefault(r["lead_bin"], []).append(r)
                ev_in_bin.setdefault(r["lead_bin"], set()).add(i)
    bins = []
    for _, _, lab in LEAD_BINS:
        rs = by_bin.get(lab, [])
        if not rs:
            continue
        errs = [r["crest_error_ft"] for r in rs]
        cat = [r["category_right"] for r in rs if "category_right" in r]
        te = [r["crest_time_error_h"] for r in rs if "crest_time_error_h" in r]
        bins.append({"lead": lab, "n_products": len(rs), "n_events": len(ev_in_bin[lab]),
                     "crest_bias_ft": round(statistics.fmean(errs), 2),
                     "crest_mae_ft": round(statistics.fmean(abs(x) for x in errs), 2),
                     "category_right_share": round(sum(cat) / len(cat), 3) if cat else None,
                     "crest_time_mae_h": round(statistics.fmean(abs(x) for x in te), 1) if te else None})
    leads = [e["first_warning_lead_before_minor_h"] for e in events if e["first_warning_lead_before_minor_h"]
             is not None]
    return {"n_events": len(events), "lead_bins": bins,
            "first_warning_lead_before_minor_h": {
                "n": len(leads), "median": statistics.median(leads) if leads else None,
                "min": min(leads) if leads else None, "max": max(leads) if leads else None}}


def _series(conn: psycopg.Connection, sid: str, t0: datetime, t1: datetime) -> list[tuple[datetime, float]]:
    return [(t, float(v)) for t, v in conn.execute(
        "SELECT ts, raw_value FROM observations WHERE station_id = %s AND param = 'level' AND NOT is_sentinel"
        " AND raw_value IS NOT NULL AND ts BETWEEN %s AND %s ORDER BY ts", (sid, t0, t1))]


def overflow_onset(conn: psycopg.Connection, t0: datetime, t1: datetime) -> datetime | None:
    """First SR 544 overflow record in the window (reported only while water flowed until 2026-10-01; from then on,
    the first reading at or above its 3.6 ft action stage), as in the replay (D-02.4)."""
    for t, v in _series(conn, OVERFLOW, t0, t1):
        if t < OVERFLOW_CONTINUOUS_FROM or v >= OVERFLOW_ACTION_FT:
            return t
    return None


def build(conn: psycopg.Connection, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    conn.execute("SET statement_timeout = '10min'")
    stages = {}
    for sid, thr in conn.execute("SELECT station_id, official_thresholds FROM stations WHERE station_id = ANY(%s)",
                                 (list(POINTS.values()),)).fetchall():
        cats = (thr or {}).get("categories") or {}
        stages[sid] = {c: float(cats[c]["stage_ft"]) for c in CATS if (cats.get(c) or {}).get("stage_ft") is not None}
    rows = conn.execute(
        "SELECT v.nwsli, v.etn, v.issued_at, v.action, v.severity, v.forecast_crest_ft, v.flood_crest, v.flood_begin,"
        " v.flood_end, p.pil, p.wmo FROM nws_vtec v JOIN nws_products p USING (product_id)"
        " WHERE v.nwsli = ANY(%s) AND v.phenomena = 'FL' AND v.significance = 'W' ORDER BY v.nwsli, v.issued_at",
        (list(POINTS),)).fetchall()
    groups: dict[tuple[str, int, int], list[dict[str, Any]]] = {}
    for nwsli, etn, iss, act, sev, fc, fcrest, fbeg, fend, pil, wmo in rows:
        wy = iss.year + 1 if iss.month >= 10 else iss.year  # water year (Oct-Sep), so ETNs that restart each Jan
        groups.setdefault((nwsli, etn, wy), []).append(  # never merge across years within one season
            {"issued_at": iss, "action": act, "severity": sev, "forecast_crest_ft": fc, "flood_crest": fcrest,
             "flood_begin": fbeg, "flood_end": fend, "product": f"{pil} {wmo}"})
    events = []
    for (nwsli, etn, wy), prods in sorted(groups.items(), key=lambda kv: kv[1][0]["issued_at"]):
        sid = POINTS[nwsli]
        t0 = prods[0]["issued_at"] - timedelta(hours=12)
        t1 = max([p["issued_at"] for p in prods] + [p["flood_end"] for p in prods if p["flood_end"]]) \
            + timedelta(hours=48)
        obs = observe(_series(conn, sid, t0, t1), stages.get(sid, {}))
        if obs is None:
            events.append({"point": nwsli, "station_id": sid, "etn": etn, "water_year": wy, "status": "no_observations",
                           "first_issued_at": prods[0]["issued_at"]})
            continue
        onset = overflow_onset(conn, t0, t1) if nwsli == "NRKW1" else None
        ev = score_event(prods, obs, stages.get(sid, {}), onset)
        events.append({"point": nwsli, "station_id": sid, "etn": etn, "water_year": wy, "status": "scored",
                       "stages_ft": stages.get(sid, {}), **ev})
    scored = [e for e in events if e["status"] == "scored"]
    body = {"generated_at": now, "method": (__doc__ or "").strip(), "points": POINTS,
            "period": [min((e["first_issued_at"] for e in events), default=None),
                       max((e["first_issued_at"] for e in events), default=None)],
            "summary": {nw: summarise([e for e in scored if e["point"] == nw]) for nw in POINTS},
            "events": events}
    conn.execute("INSERT INTO official_scorecards (generated_at, body) VALUES (%s, %s)", (now, Jsonb(body)))
    return body
