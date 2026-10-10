"""Relay v2 and the trust table (protocol amendment 2; supervisor addendum 3; D-03.23).

Counting rules are fixed in docs/evaluation-protocol.md, amendment 2, before these numbers were computed:
- record period from the first SR 544 record; alerts before it and overflow episodes whose warning event began before
  it are not counted;
- overflow episode: SR 544 records before 2026-10-01 (then readings >= 3.6 ft), split at gaps > 48 h; onset = first
  record, peak = max, large = peak >= 5.0 ft;
- an alert's window: its event's first product - 12 h to the event's end (latest VTEC end, else its last product)
  + 24 h; "followed by an overflow" = an onset in that window; lead = onset - alert time;
- missed = an overflow episode with no alert of that tier whose window contains its onset;
- precision with an exact Clopper-Pearson 95 % interval; day/night at Abbotsford.
Relay v2 is descriptive and in-sample: Prepare and the 5.0 ft level were chosen after seeing every year.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg

from floodlead import sun

OVERFLOW = "usgs:12211195"
CONTINUOUS_FROM = datetime(2026, 10, 1, tzinfo=UTC)
GAP = timedelta(hours=48)
LARGE_FT = 5.0
MOVE_LEVELS = (5.0, 4.0)
PRE, POST = timedelta(hours=12), timedelta(hours=24)
ABBOTSFORD = {  # first alert and first order touching Sumas Prairie (status-quo review; ranges, UTC)
    2021: {"first_alert": ("2021-11-15T08:30:00Z", "2021-11-15T08:30:00Z"),
           "first_order": ("2021-11-16T01:00:00Z", "2021-11-16T04:00:00Z")},
    2025: {"first_alert": ("2025-12-11T00:00:00Z", "2025-12-11T01:20:00Z"),
           "first_order": ("2025-12-11T07:00:00Z", "2025-12-11T07:00:00Z")},
}


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact (Clopper-Pearson) binomial interval, by bisection on the binomial tails (no scipy)."""
    if n == 0:
        return (math.nan, math.nan)

    def cdf(x: int, p: float) -> float:  # P(X <= x)
        return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(0, x + 1))

    def bisect(f, target: float, increasing: bool) -> float:  # noqa: ANN001
        lo, hi = 0.0, 1.0
        for _ in range(100):
            mid = (lo + hi) / 2
            if (f(mid) < target) == increasing:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    lower = 0.0 if k == 0 else bisect(lambda p: 1 - cdf(k - 1, p), alpha / 2, increasing=True)
    upper = 1.0 if k == n else bisect(lambda p: cdf(k, p), alpha / 2, increasing=False)
    return (lower, upper)


@dataclass
class Episode:
    onset: datetime
    end: datetime
    peak_ft: float
    first_ge: dict[float, datetime | None]

    @property
    def large(self) -> bool:
        return self.peak_ft >= LARGE_FT


def episodes(rows: list[tuple[datetime, float]]) -> list[Episode]:
    out: list[Episode] = []
    cur: list[tuple[datetime, float]] = []
    for t, v in rows:
        if t >= CONTINUOUS_FROM and v < 3.6:
            continue
        if cur and t - cur[-1][0] > GAP:
            out.append(_ep(cur))
            cur = []
        cur.append((t, v))
    if cur:
        out.append(_ep(cur))
    return out


def _ep(cur: list[tuple[datetime, float]]) -> Episode:
    return Episode(cur[0][0], cur[-1][0], max(v for _, v in cur),
                   {lv: next((t for t, v in cur if v >= lv), None) for lv in MOVE_LEVELS})


def _iso(t: datetime | None) -> str | None:
    return None if t is None else t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def score(alerts: list[dict[str, Any]], eps: list[Episode]) -> dict[str, Any]:
    """alerts: [{at, window: (a, b), label}], scored against the overflow episodes."""
    rows = []
    for a in sorted(alerts, key=lambda x: x["at"]):
        w0, w1 = a["window"]
        hit = next((e for e in eps if w0 <= e.onset <= w1), None)
        rows.append({"at": _iso(a["at"]), "label": a["label"], "daylight": sun.is_daylight(a["at"]),
                     "followed_by_overflow": hit is not None, "followed_by_large": bool(hit and hit.large),
                     "overflow_onset": _iso(hit.onset) if hit else None,
                     "overflow_peak_ft": hit.peak_ft if hit else None,
                     "lead_h": round((hit.onset - a["at"]).total_seconds() / 3600, 2) if hit else None})
    n = len(rows)
    k = sum(r["followed_by_overflow"] for r in rows)
    kl = sum(r["followed_by_large"] for r in rows)
    missed = [e for e in eps if not any(a["window"][0] <= e.onset <= a["window"][1] for a in alerts)]
    ci = clopper_pearson(k, n)
    cil = clopper_pearson(kl, n)
    return {"alerts": n, "followed_by_overflow": k, "followed_by_large": kl,
            "precision": round(k / n, 3) if n else None, "precision_ci95": [round(x, 3) for x in ci],
            "precision_large": round(kl / n, 3) if n else None, "precision_large_ci95": [round(x, 3) for x in cil],
            "missed": [{"onset": _iso(e.onset), "peak_ft": e.peak_ft} for e in missed],
            "list": rows}


def build(conn: psycopg.Connection, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    conn.execute("SET statement_timeout = '10min'")
    gauge = [(t, float(v)) for t, v in conn.execute(
        "SELECT ts, raw_value FROM observations WHERE station_id = %s AND param = 'level' AND NOT is_sentinel"
        " AND raw_value IS NOT NULL AND ts >= '2015-01-01' AND ts <= %s ORDER BY ts", (OVERFLOW, now)).fetchall()]
    record_start = gauge[0][0]
    eps_all = episodes(gauge)
    # NRKW1 warning events (FL.W; one per ETN and water year)
    ev: dict[tuple[int, int], list[tuple]] = {}
    for iss, act, sev, end, etn in conn.execute(
            "SELECT issued_at, action, severity, vtec_end, etn FROM nws_vtec WHERE nwsli = 'NRKW1' AND phenomena ="
            " 'FL' AND significance = 'W' ORDER BY issued_at").fetchall():
        wy = iss.year + 1 if iss.month >= 10 else iss.year
        ev.setdefault((etn, wy), []).append((iss, act, sev, end))
    events = []
    for (etn, wy), prods in ev.items():
        first = prods[0][0]
        ends = [p[3] for p in prods if p[3] is not None]
        end = max(ends) if ends else prods[-1][0]
        events.append({"etn": etn, "wy": wy, "first": first, "end": end, "prods": prods,
                       "window": (first - PRE, end + POST)})
    # overflow episodes whose warning event began before the record start are excluded (amendment 2)
    pre_events = [e for e in events if e["first"] < record_start]
    eps = [x for x in eps_all if not any(e["window"][0] <= x.onset <= e["window"][1] for e in pre_events)]
    excluded_eps = [x for x in eps_all if x not in eps]
    in_rec = [e for e in events if e["first"] >= record_start]
    heads = [{"at": e["first"], "window": e["window"], "label": f"NRKW1 ETN {e['etn']} (WY{e['wy']}) NEW"}
             for e in in_rec]
    prep = []
    for e in in_rec:
        p = next((p for p in e["prods"] if p[2] in ("2", "3")), None)
        if p:
            prep.append({"at": p[0], "window": e["window"],
                         "label": f"NRKW1 ETN {e['etn']} (WY{e['wy']}) first severity {p[2]} ({p[1]})"})
    # watches naming Whatcom: one per (phenomena, ETN, year)
    wv: dict[tuple, list[tuple]] = {}
    for iss, end, ph, etn in conn.execute(
            "SELECT issued_at, vtec_end, phenomena, etn FROM nws_vtec WHERE significance = 'A' AND phenomena IN"
            " ('FA', 'FL') AND segment_head ILIKE '%%Whatcom%%' AND issued_at >= %s ORDER BY issued_at",
            (record_start,)).fetchall():
        wv.setdefault((ph, etn, iss.year), []).append((iss, end))
    watch = []
    for (ph, etn, yr), prods in wv.items():
        ends = [p[1] for p in prods if p[1] is not None]
        end = max(ends) if ends else prods[-1][0]
        watch.append({"at": prods[0][0], "window": (prods[0][0] - PRE, end + POST),
                      "label": f"{ph}.A ETN {etn} ({yr})"})
    fav: dict[tuple, list[tuple]] = {}
    for iss, end, etn in conn.execute(
            "SELECT issued_at, vtec_end, etn FROM nws_vtec WHERE phenomena = 'FA' AND significance = 'W'"
            " AND segment_head ILIKE '%%Everson%%' AND segment_head ILIKE '%%overflow%%' AND issued_at >= %s"
            " ORDER BY issued_at", (record_start,)).fetchall():
        fav.setdefault((etn, iss.year), []).append((iss, end))
    fa = []
    for (etn, yr), prods in fav.items():
        ends = [p[1] for p in prods if p[1] is not None]
        end = max(ends) if ends else prods[-1][0]
        fa.append({"at": prods[0][0], "window": (prods[0][0] - PRE, end + POST), "label": f"FA.W ETN {etn} ({yr})"})
    tiers = {"watch": score(watch, eps), "heads_up": score(heads, eps), "prepare": score(prep, eps),
             "everson_overflow_fa_w": score(fa, eps)}
    for lv in MOVE_LEVELS:
        mv = [{"at": x.first_ge[lv], "window": (x.onset, x.end), "label": f"SR 544 >= {lv} ft"}
              for x in eps if x.first_ge[lv] is not None]
        tiers[f"move_now_{lv:.1f}ft"] = score(mv, eps)
    years = (now - record_start).total_seconds() / (365.25 * 86400)
    for t in tiers.values():
        t["alerts_per_year"] = round(t["alerts"] / years, 2)
    # 2021 and 2025 against Abbotsford
    comp = {}
    for yr, ab in ABBOTSFORD.items():
        row = {}
        for name, t in tiers.items():
            first = next((r for r in t["list"] if r["at"].startswith(str(yr)) and r["followed_by_large"]
                          and (yr != 2021 or r["overflow_onset"] < "2021-11-20")), None)
            if first:
                at = datetime.fromisoformat(first["at"].replace("Z", "+00:00"))
                fa0, fa1 = (datetime.fromisoformat(x.replace("Z", "+00:00")) for x in ab["first_alert"])
                fo0, fo1 = (datetime.fromisoformat(x.replace("Z", "+00:00")) for x in ab["first_order"])
                row[name] = {"at": first["at"], "daylight": first["daylight"],
                             "before_first_alert_h": [round((fa0 - at).total_seconds() / 3600, 1),
                                                      round((fa1 - at).total_seconds() / 3600, 1)],
                             "before_first_order_h": [round((fo0 - at).total_seconds() / 3600, 1),
                                                      round((fo1 - at).total_seconds() / 3600, 1)]}
        comp[str(yr)] = row
    return {"generated_at": _iso(now), "record_start": _iso(record_start), "record_years": round(years, 2),
            "nrkw1_warning_events": len(in_rec),
            "overflow_episodes": [{"onset": _iso(x.onset), "end": _iso(x.end), "peak_ft": x.peak_ft,
                                   "large": x.large} for x in eps],
            "excluded_episodes": [{"onset": _iso(x.onset), "peak_ft": x.peak_ft,
                                   "reason": "its warning event began before the SR 544 record"} for x in excluded_eps],
            "tiers": tiers, "abbotsford_2021_2025": comp,
            "labels": {"relay_v2": "descriptive and in-sample: the Prepare tier and the 5.0 ft Move-now level were "
                                   "chosen after seeing every year, including the held-out ones",
                       "move_now_5.0ft": "chosen after seeing the data",
                       "move_now_4.0ft": "the NWS minor stage at SR 544; not chosen from the data"},
            "method": (__doc__ or "").strip()}
