"""Scoring: every settled forecast horizon against what the river did, next to persistence, trend and NOAA.

Scores are derived data (table forecast_scores), reproducible from the ledger plus observations, and rewritten when
a truth observation is revised. Rules (docs/stages/STAGE-02-ledger-app.md, D-02.13):

- A horizon settles once valid_at is at least 3 h old.
- Level truth: the observation at valid_at, else the nearest within +/-10 min, else `no_truth` (never imputed).
- Event truth: the maximum observation over (data_as_of, valid_at], the same window as qmax and p_exceed (it
  includes the feed-latency gap the forecaster could not see); `insufficient_truth` if observations cover < 80 % of
  the window's grid.
- CRPS is approximated by the quantile score: 2 x mean pinball loss over the 7 quantile levels (equals the absolute
  error for a point forecast). Also: absolute error of the median, 25-75/10-90/5-95 % coverage, PIT bin, and Brier
  per threshold.
- NOAA matched comparison: base times at 00/06/12/18Z, horizons that are multiples of 6 h, stations with an NWPS
  forecast; NOAA's latest issuance with fetched_at <= our created_at, its point at the same valid_at (fetched by
  then); absolute error, and Brier with p in {0, 1} for the official categories (NOAA's points in the window).
"""

from __future__ import annotations

import json
import statistics
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from floodlead import baselines as bl
from floodlead import log
from floodlead.units import FT_TO_M

L = log.get(__name__)

SETTLE = timedelta(hours=3)
TRUTH_TOL = timedelta(minutes=10)
MIN_COVERAGE = 0.8
STEP = {"eccc": timedelta(minutes=5), "usgs": timedelta(minutes=15)}
LOOKBACK = timedelta(hours=60)  # base times older than this are fully settled once scored (48 h + 3 h + slack)
MIN_EVENTS = 30
TAUS = bl.QUANTILES
KEYS = bl.QKEYS


def pinball(tau: float, u: float) -> float:
    return u * tau if u >= 0 else u * (tau - 1.0)


def crps_qs(q: dict[str, float], y: float) -> float:
    """CRPS approximated by the quantile score: 2 x mean pinball loss over the quantile levels."""
    return 2.0 * statistics.fmean(pinball(t, y - q[k]) for t, k in zip(TAUS, KEYS, strict=True))


def pit_bin(q: dict[str, float], y: float) -> int:
    """0 = below the 0.05 quantile, ..., 7 = above the 0.95 quantile."""
    return sum(1 for k in KEYS if q[k] <= y)


def truth_at(obs: list[tuple[datetime, float, datetime, int]], t: datetime
             ) -> tuple[datetime, float, datetime, int] | None:
    best = None
    for row in obs:
        d = abs(row[0] - t)
        if d <= TRUTH_TOL and (best is None or d < abs(best[0] - t)):
            best = row
            if d == timedelta(0):
                break
    return best


def window(obs: list[tuple[datetime, float, datetime, int]], t0: datetime, t1: datetime, step: timedelta
           ) -> tuple[float | None, float]:
    vals = [v for ts, v, _, _ in obs if t0 < ts <= t1]
    expected = max(1, int((t1 - t0) / step))
    return (max(vals) if vals else None), len(vals) / expected


def score_one(d: dict[str, Any], hz: dict[str, Any], created_at: datetime,
              obs: list[tuple[datetime, float, datetime, int]], noaa: dict[str, Any] | None) -> dict[str, Any]:
    src = d["station_id"].split(":", 1)[0]
    valid = datetime.fromisoformat(hz["valid_at"].replace("Z", "+00:00"))
    asof = datetime.fromisoformat(d["data_as_of"].replace("Z", "+00:00"))
    out: dict[str, Any] = {"valid_at": valid, "events": {}, "noaa": None}
    tr = truth_at(obs, valid)
    if tr is None:
        out["status"] = "no_truth"
    else:
        y = tr[1]
        q = hz["q"]
        out.update(status="scored", truth_ts=tr[0], truth_m=y, truth_first_seen_at=tr[2], truth_revision_count=tr[3],
                   q50_m=q["0.5"], crps=crps_qs(q, y), ae_median=abs(y - q["0.5"]),
                   in_50=q["0.25"] <= y <= q["0.75"], in_80=q["0.1"] <= y <= q["0.9"],
                   in_90=q["0.05"] <= y <= q["0.95"], pit_bin=pit_bin(q, y))
    wmax, cov = window(obs, asof, valid, STEP[src])
    out["window_coverage"] = round(cov, 4)
    out["window_max_m"] = wmax
    if wmax is None or cov < MIN_COVERAGE:
        out["event_status"] = "insufficient_truth"
    else:
        out["event_status"] = "ok"
        levels = {t["key"]: t["level_m"] for t in d["thresholds"]}
        for k, p in hz["p_exceed"].items():
            o = 1 if wmax >= levels[k] else 0
            out["events"][k] = {"p": p, "outcome": o, "brier": (p - o) ** 2}
    if noaa is not None and out.get("status") == "scored":
        nm = noaa["stage_ft"] * FT_TO_M
        ev = {}
        if out["event_status"] == "ok":
            for t in d["thresholds"]:
                if t["kind"] != "official":
                    continue
                p = 1.0 if noaa["window_max_ft"] is not None and noaa["window_max_ft"] >= t["level_ft"] else 0.0
                o = out["events"][t["key"]]["outcome"]
                ev[t["key"]] = {"p": p, "outcome": o, "brier": (p - o) ** 2}
        out["noaa"] = {"lid": noaa["lid"], "issued_at": noaa["issued_at"], "stage_ft": noaa["stage_ft"],
                       "stage_m": round(nm, 4), "ae": abs(out["truth_m"] - nm), "lead_h": noaa["lead_h"], "events": ev}
    return out


def _noaa_point(conn: psycopg.Connection, lid: str, created_at: datetime, asof: datetime, valid: datetime
                ) -> dict[str, Any] | None:
    iss = conn.execute("SELECT max(issued_at) FROM official_forecasts WHERE lid = %s AND fetched_at <= %s",
                       (lid, created_at)).fetchone()[0]
    if iss is None:
        return None
    pt = conn.execute("SELECT stage_ft FROM official_forecasts WHERE lid = %s AND issued_at = %s AND valid_at = %s"
                      " AND fetched_at <= %s", (lid, iss, valid, created_at)).fetchone()
    if pt is None or pt[0] is None:
        return None
    wmax = conn.execute("SELECT max(stage_ft) FROM official_forecasts WHERE lid = %s AND issued_at = %s"
                        " AND valid_at > %s AND valid_at <= %s AND fetched_at <= %s",
                        (lid, iss, asof, valid, created_at)).fetchone()[0]
    return {"lid": lid, "issued_at": iss.strftime("%Y-%m-%dT%H:%M:%SZ"), "stage_ft": pt[0], "window_max_ft": wmax,
            "lead_h": round((valid - iss).total_seconds() / 3600, 2)}


def run(pool: ConnectionPool, now: datetime | None = None) -> dict[str, Any]:
    t0 = time.monotonic()
    now = now or datetime.now(UTC)
    with pool.connection() as conn:
        conn.autocommit = True
        run_id = conn.execute("INSERT INTO scorer_runs DEFAULT VALUES RETURNING scorer_run_id").fetchone()[0]
        lids = {sid: lid for sid, lid in conn.execute(
            "SELECT station_id, links->>'nwps_lid' FROM stations WHERE links ? 'nwps_lid'")}
        cand = conn.execute(
            "SELECT seq, station_id, base_time, created_at FROM ledger_entries WHERE entry_type = 'forecast'"
            " AND base_time > %s AND base_time <= %s ORDER BY station_id, seq",
            (now - LOOKBACK, now - SETTLE - timedelta(hours=1))).fetchall()
        done: dict[int, dict[int, tuple[datetime, datetime]]] = defaultdict(dict)
        for seq, h, valid, scored_at in conn.execute(
                "SELECT seq, h, valid_at, scored_at FROM forecast_scores WHERE base_time > %s", (now - LOOKBACK,)):
            done[seq][h] = (valid, scored_at)
        # Stations with a revised level observation in the scoring window: only their scored entries are re-checked.
        revised = {r[0] for r in conn.execute(
            "SELECT DISTINCT station_id FROM observations WHERE param = 'level' AND ts > %s AND revised_at > %s",
            (now - LOOKBACK - timedelta(hours=52), now - LOOKBACK - timedelta(hours=52)))}
        by_station: dict[str, list[tuple[int, datetime, datetime]]] = defaultdict(list)
        for seq, sid, base, created in cand:
            settled = [h for h in bl.HORIZONS_H if base + timedelta(hours=h) - created >= timedelta(minutes=30)
                       and base + timedelta(hours=h) + SETTLE <= now]
            if any(h not in done[seq] for h in settled) or (done[seq] and sid in revised):
                by_station[sid].append((seq, base, created))
        scored = rescored = 0
        for sid, entries in by_station.items():
            seqs = [e[0] for e in entries]
            rows = conn.execute("SELECT seq, created_at, canonical FROM ledger_entries WHERE seq = ANY(%s)",
                                (seqs,)).fetchall()
            parsed = [(s, c, json.loads(can)["data"]) for s, c, can in rows]
            t_lo = min(datetime.fromisoformat(d["data_as_of"].replace("Z", "+00:00")) for _, _, d in parsed)
            t_hi = max(datetime.fromisoformat(hz["valid_at"].replace("Z", "+00:00"))
                       for _, _, d in parsed for hz in d["horizons"]) + TRUTH_TOL
            obs_rows = conn.execute(
                "SELECT ts, value, first_seen_at, revision_count, coalesce(revised_at, first_seen_at) FROM observations"
                " WHERE station_id = %s AND param = 'level' AND NOT is_sentinel AND value IS NOT NULL"
                " AND ts BETWEEN %s AND %s ORDER BY ts", (sid, t_lo, t_hi)).fetchall()
            obs = [(r[0], r[1], r[2], r[3]) for r in obs_rows]
            changed = [(r[0], r[4]) for r in obs_rows]
            batch = []
            for seq, created, d in parsed:
                asof = datetime.fromisoformat(d["data_as_of"].replace("Z", "+00:00"))
                for hz in d["horizons"]:
                    valid = datetime.fromisoformat(hz["valid_at"].replace("Z", "+00:00"))
                    if valid + SETTLE > now:
                        continue
                    prev = done[seq].get(hz["h"])
                    if prev is not None:
                        # Rescore only if an observation in the truth window was revised after scoring.
                        if not any(asof - TRUTH_TOL <= ts <= valid + TRUTH_TOL and ch > prev[1] for ts, ch in changed):
                            continue
                        rescored += 1
                    else:
                        scored += 1
                    noaa = None
                    lid = lids.get(sid)
                    base = datetime.fromisoformat(d["base_time"].replace("Z", "+00:00"))
                    if lid and base.hour % 6 == 0 and hz["h"] % 6 == 0:
                        noaa = _noaa_point(conn, lid, created, asof, valid)
                    s = score_one(d, hz, created, obs, noaa)
                    batch.append((seq, hz["h"], sid, sid.split(":", 1)[0], d["model"], base, valid,
                                  d["stale_inputs"], s["status"], s.get("truth_ts"), s.get("truth_m"),
                                  s.get("truth_first_seen_at"), s.get("truth_revision_count"), s.get("q50_m"),
                                  s.get("crps"), s.get("ae_median"), s.get("in_50"), s.get("in_80"), s.get("in_90"),
                                  s.get("pit_bin"), s["event_status"], s["window_coverage"], s["window_max_m"],
                                  Jsonb(s["events"]), Jsonb(s["noaa"]) if s["noaa"] else None, now, run_id))
            if batch:
                with conn.transaction(), conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO forecast_scores (seq, h, station_id, source, model, base_time, valid_at,"
                        " stale_inputs, status, truth_ts, truth_m, truth_first_seen_at, truth_revision_count, q50_m,"
                        " crps, ae_median, in_50, in_80, in_90, pit_bin, event_status, window_coverage, window_max_m,"
                        " events, noaa, scored_at, scorer_run_id) VALUES (" + ", ".join(["%s"] * 27) + ")"
                        " ON CONFLICT (seq, h) DO UPDATE SET status = EXCLUDED.status, truth_ts = EXCLUDED.truth_ts,"
                        " truth_m = EXCLUDED.truth_m, truth_first_seen_at = EXCLUDED.truth_first_seen_at,"
                        " truth_revision_count = EXCLUDED.truth_revision_count, crps = EXCLUDED.crps,"
                        " ae_median = EXCLUDED.ae_median, in_50 = EXCLUDED.in_50, in_80 = EXCLUDED.in_80,"
                        " in_90 = EXCLUDED.in_90, pit_bin = EXCLUDED.pit_bin, event_status = EXCLUDED.event_status,"
                        " window_coverage = EXCLUDED.window_coverage, window_max_m = EXCLUDED.window_max_m,"
                        " events = EXCLUDED.events, noaa = EXCLUDED.noaa, scored_at = EXCLUDED.scored_at,"
                        " scorer_run_id = EXCLUDED.scorer_run_id", batch)
        summary = summarise(conn, run_id, now)
        runtime = round(time.monotonic() - t0, 1)
        conn.execute("UPDATE scorer_runs SET finished_at = now(), status = 'ok', scored = %s, rescored = %s,"
                     " details = %s WHERE scorer_run_id = %s",
                     (scored, rescored, Jsonb({"runtime_s": runtime, "candidates": len(cand)}), run_id))
        L.info("scorer run", **log.kv(run_id=run_id, scored=scored, rescored=rescored, runtime_s=runtime))
        return {"scorer_run_id": run_id, "scored": scored, "rescored": rescored, "runtime_s": runtime,
                "n_scored_total": summary["totals"]["scored"]}


def summarise(conn: psycopg.Connection, run_id: int, now: datetime) -> dict[str, Any]:
    """Materialise the summary: by model x horizon x source (non-stale, scored), paired skill vs persistence,
    Brier per threshold family with event counts, and the NOAA matched comparison."""
    q = conn.execute
    tot = q("SELECT count(*) FILTER (WHERE status = 'scored'), count(*) FILTER (WHERE status = 'no_truth'),"
            " count(*) FILTER (WHERE stale_inputs), min(base_time), max(valid_at) FROM forecast_scores").fetchone()
    rows = q("SELECT model, h, source, count(*), count(DISTINCT station_id), count(DISTINCT base_time::date),"
             " avg(crps), avg(ae_median), avg(in_50::int)::float, avg(in_80::int)::float, avg(in_90::int)::float"
             " FROM forecast_scores WHERE status = 'scored' AND NOT stale_inputs GROUP BY 1, 2, 3 ORDER BY 1, 3, 2"
             ).fetchall()
    pairs = {(r[0], r[1]): r[2:] for r in q(
        "SELECT t.h, t.source, count(*), avg(t.crps), avg(p.crps) FROM forecast_scores t JOIN forecast_scores p"
        " ON p.station_id = t.station_id AND p.base_time = t.base_time AND p.h = t.h AND p.model = 'persistence-v1'"
        " WHERE t.model = 'trend3h-v1' AND t.status = 'scored' AND p.status = 'scored'"
        " AND NOT t.stale_inputs AND NOT p.stale_inputs GROUP BY 1, 2").fetchall()}
    fam = "CASE WHEN e.k LIKE 'official:%%' THEN 'official' ELSE e.k END"
    brier = defaultdict(dict)
    for model, h, src, family, n, events, mb in q(
            f"SELECT model, h, source, {fam}, count(*), sum((e.v->>'outcome')::int), avg((e.v->>'brier')::float)"
            " FROM forecast_scores, jsonb_each(events) AS e(k, v) WHERE status = 'scored' AND NOT stale_inputs"
            " AND event_status = 'ok' GROUP BY 1, 2, 3, 4").fetchall():
        brier[(model, h, src)][family] = {"n": n, "events": int(events or 0), "brier": mb}
    bss = {}
    for h, src, family, n, events, bt, bp in q(
            f"SELECT t.h, t.source, {fam}, count(*), sum((e.v->>'outcome')::int), avg((e.v->>'brier')::float),"
            " avg((p.events->e.k->>'brier')::float) FROM forecast_scores t CROSS JOIN LATERAL jsonb_each(t.events)"
            " AS e(k, v) JOIN forecast_scores p ON p.station_id = t.station_id AND p.base_time = t.base_time"
            " AND p.h = t.h AND p.model = 'persistence-v1' AND p.events ? e.k WHERE t.model = 'trend3h-v1'"
            " AND t.status = 'scored' AND p.status = 'scored' AND NOT t.stale_inputs AND NOT p.stale_inputs"
            " AND t.event_status = 'ok' GROUP BY 1, 2, 3").fetchall():
        bss[(h, src, family)] = {"n_pairs": n, "events": int(events or 0),
                                 "bss_vs_persistence": (None if events is None or events < MIN_EVENTS or not bp
                                                        else round(1 - bt / bp, 4)),
                                 "note": None if events is not None and events >= MIN_EVENTS
                                 else "too few events to judge"}
    groups = []
    for model, h, src, n, st, days, crps, mae, c50, c80, c90 in rows:
        g: dict[str, Any] = {"model": model, "h": h, "source": src, "n": n, "stations": st, "days": days,
                             "mean_crps_m": crps, "mae_median_m": mae,
                             "coverage": {"25-75": c50, "10-90": c80, "5-95": c90}, "brier": {}}
        if model == "trend3h-v1" and (h, src) in pairs:
            n_p, mt, mp = pairs[(h, src)]
            g["crpss_vs_persistence"] = {"n_pairs": n_p, "value": None if not mp else round(1 - mt / mp, 4),
                                         "paired_crps": {"trend3h-v1": mt, "persistence-v1": mp}}
        for family, b in brier.get((model, h, src), {}).items():
            entry = {**b, "note": None if b["events"] >= MIN_EVENTS else "too few events to judge"}
            if model == "trend3h-v1" and (h, src, family) in bss:
                entry["bss_vs_persistence"] = bss[(h, src, family)]
            g["brier"][family] = entry
        groups.append(g)
    official = []
    for lid, model, h, n, mae, noaa_mae, lead in q(
            "SELECT noaa->>'lid', model, h, count(*), avg(ae_median), avg((noaa->>'ae')::float),"
            " percentile_cont(0.5) WITHIN GROUP (ORDER BY (noaa->>'lead_h')::float) FROM forecast_scores"
            " WHERE noaa IS NOT NULL AND status = 'scored' GROUP BY 1, 2, 3 ORDER BY 1, 2, 3").fetchall():
        official.append({"lid": lid, "model": model, "h": h, "n": n, "mae_median_m": mae, "noaa_mae_m": noaa_mae,
                         "noaa_median_lead_h": lead})
    body = {"scorer_run_id": run_id, "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window": {"first_base_time": tot[3].strftime("%Y-%m-%dT%H:%M:%SZ") if tot[3] else None,
                       "last_valid_at": tot[4].strftime("%Y-%m-%dT%H:%M:%SZ") if tot[4] else None},
            "totals": {"scored": tot[0], "no_truth": tot[1], "stale_excluded": tot[2]},
            "rules": {"settle_h": 3, "truth_tolerance_min": 10, "event_window": "(data_as_of, valid_at]",
                      "min_window_coverage": MIN_COVERAGE, "crps": "quantile score: 2 x mean pinball loss (7 levels)",
                      "skill": "paired samples only (same station, base time, horizon)",
                      "min_events_for_skill": MIN_EVENTS, "stale": "stale-input forecasts excluded"},
            "groups": groups, "official": official}
    q("INSERT INTO score_summaries (scorer_run_id, generated_at, body) VALUES (%s, %s, %s)",
      (run_id, now, Jsonb(body)))
    return body
