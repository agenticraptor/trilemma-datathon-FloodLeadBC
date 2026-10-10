"""Stage 4 scoring of saved predictions: the development report (walk-forward validation predictions) and, after the
supervisor's go, the same blocks on held-out rows. Protocol §4-§6 with amendments 1-4.

Probabilities:
- crossing P(>= X within H) from the window-maximum quantiles m_H (H = 12, 24, 48 h);
- overflow onset within H = mean over the development onsets L_j of P(M_H >= L_j); for H = 6 h, which has no window
  target in amendment 4, the 6-h level quantiles d_6 stand in (on a rising river the 6-h level is the 6-h maximum);
  rows where overflow water was already flowing are excluded (their target is undefined);
- outcomes are the frozen dataset's y_minor/y_moderate/y_major/y_overflow columns.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from floodlead import model, model_eval, train_data

THRESH = {"minor": 146.5, "moderate": 148.0, "major": 150.0}
NWS_COL = {"moderate": "nws_p_ge_148", "major": "nws_p_ge_150"}
WINDOW_TARGET = {6: "d_6", 12: "m_12", 24: "m_24", 48: "m_48"}
P_GRID = tuple(round(0.1 * i, 1) for i in range(1, 10))
K_GRID = (1, 2, 3)
FAR_LIMIT = {"prepare": 0.5, "move": 0.2}
SELECTION_H = (6, 12, 24)
TIMING_NOTE = ("not assessable: no agency recorded when water reached the border or the farm's zone; protocol §6 "
               "claims no accuracy without >= 3 verifiable arrival times. Hours before the overflow onset are shown")


def ts(x: str) -> datetime:
    return datetime.fromisoformat(str(x).replace("Z", "+00:00").replace(" ", "T")).astimezone(UTC)


def joined(frame: pd.DataFrame, idx: pd.DataFrame, preds: dict[str, np.ndarray]
           ) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    """Dataset rows for the predictions' issue times, sorted by time (predictions reordered to match)."""
    val = frame.set_index("issue_time").loc[idx["issue_time"].to_numpy()].reset_index()
    order = np.argsort(val["issue_time"].to_numpy(), kind="stable")
    val = val.iloc[order].reset_index(drop=True)
    val["t"] = pd.to_datetime(val["issue_time"], utc=True)
    return val, {k: v[order] for k, v in preds.items()}


def overflow_probability(val: pd.DataFrame, preds: dict[str, np.ndarray], h: int, levels: list[float]) -> np.ndarray:
    q = preds[WINDOW_TARGET[h]]
    p = model.overflow_prob(q, val["nc_lvl"].to_numpy(dtype=float), levels)
    return np.where(val["overflow_flowing"].to_numpy(dtype=float) == 1.0, np.nan, p)


def crossing_blocks(val: pd.DataFrame, preds: dict[str, np.ndarray], calib: dict[str, Any] | None = None
                    ) -> dict[str, Any]:
    nc = val["nc_lvl"].to_numpy(dtype=float)
    wy = val["wy"].to_numpy(dtype=int)
    inforce = val["nws_in_force"].to_numpy(dtype=float) == 1.0
    out = {}
    for w in (12, 24, 48):
        tgt = WINDOW_TARGET[w]
        if tgt not in preds:
            continue
        for name, x in THRESH.items():
            p = model.crossing_prob(preds[tgt], nc, x)
            key = f"{name}_{x:g}ft_within_{w}h"
            if calib and key in calib:
                p = apply_calibration(calib[key], p)
            o = val[f"y_{name}_{w}h"].to_numpy(dtype=float)
            refs = {"persistence": np.where(np.isfinite(nc), (nc >= x).astype(float), np.nan)}
            if name in NWS_COL:
                refs["nws_derived"] = val[NWS_COL[name]].to_numpy(dtype=float)
            blk = model_eval.brier_block(p, o, refs, wy)
            if name in NWS_COL:
                blk["rows_with_nws_warning_in_force"] = model_eval.brier_block(
                    np.where(inforce, p, np.nan), o, {"nws_derived": refs["nws_derived"]}, wy)
            out[key] = blk
    return out


def overflow_blocks(val: pd.DataFrame, preds: dict[str, np.ndarray], levels: list[float]) -> dict[str, Any]:
    nc = val["nc_lvl"].to_numpy(dtype=float)
    d3 = val["nc_d3h"].to_numpy(dtype=float)
    wy = val["wy"].to_numpy(dtype=int)
    l_med = float(np.median(levels))
    out = {}
    for h in (6, 12, 24):
        if WINDOW_TARGET[h] not in preds:
            continue
        p = overflow_probability(val, preds, h, levels)
        o = val[f"y_overflow_{h}h"].to_numpy(dtype=float)
        trend = np.where(np.isfinite(nc), (np.maximum(nc, model_eval.trend_point(nc, d3, h)) >= l_med).astype(float),
                         np.nan)
        out[f"onset_within_{h}h"] = model_eval.brier_block(
            p, o, {"persistence_no_onset": np.where(np.isfinite(p), 0.0, np.nan), "trend_reaches_median_L": trend}, wy)
        if h == 6:
            out[f"onset_within_{h}h"]["note"] = "uses the 6-h level quantiles (no 6-h window target in amendment 4)"
    return out


def choose_alert(prob: np.ndarray, times: list[datetime], events: list[datetime], tier: str) -> dict[str, Any]:
    """§5: (p*, k) maximising the median hours of warning subject to the tier's FAR limit; else the lowest FAR."""
    rows = []
    for ps in P_GRID:
        for k in K_GRID:
            fired = [times[i] for i in model_eval.alert_events(prob, times, ps, k)]
            sc = model_eval.score_alerts(fired, events)
            leads = [e["lead_h"] for e in sc["per_event"] if e["lead_h"] is not None]
            rows.append({"p_star": ps, "k": k, "alerts": sc["alerts"], "pod": sc["pod"], "far": sc["far"],
                         "median_lead_h": float(np.median(leads)) if leads else None, "score": sc})
    ok = [r for r in rows if r["far"] is not None and r["far"] <= FAR_LIMIT[tier] and r["median_lead_h"] is not None]
    if ok:
        best, met = max(ok, key=lambda r: (r["median_lead_h"], -r["far"], -r["p_star"])), True
    else:
        cand = [r for r in rows if r["far"] is not None]
        best = min(cand, key=lambda r: (r["far"], -(r["median_lead_h"] or 0))) if cand else rows[-1]
        met = False
    return {"tier": tier, "far_limit": FAR_LIMIT[tier], "far_limit_met": met,
            "chosen": {k: best[k] for k in ("p_star", "k", "alerts", "pod", "far", "median_lead_h")},
            "chosen_detail": best["score"],
            "grid": [{k: r[k] for k in ("p_star", "k", "alerts", "pod", "far", "median_lead_h")} for r in rows]}


def alert_blocks(val: pd.DataFrame, preds: dict[str, np.ndarray], inputs: dict[str, Any], ev: dict[str, list[str]],
                 rules: dict[str, dict[str, Any]] | None = None, calib: dict[str, Any] | None = None
                 ) -> dict[str, Any]:
    """Prepare (148 ft within 24 h) and move (overflow within 12 h). With `rules`, score those (p*, k) instead of
    choosing (held-out use)."""
    times = list(val["t"].dt.to_pydatetime())
    nc = val["nc_lvl"].to_numpy(dtype=float)
    out: dict[str, Any] = {}
    if "m_24" in preds:
        p = model.crossing_prob(preds["m_24"], nc, THRESH["moderate"])
        if calib and "moderate_148ft_within_24h" in calib:
            p = apply_calibration(calib["moderate_148ft_within_24h"], p)
        out["prepare"] = score_rule(p, times, [ts(x) for x in ev["ge_148ft"]], "prepare", rules)
    if "m_12" in preds:
        p = np.nan_to_num(overflow_probability(val, preds, 12, inputs["onset_levels_ft"]), nan=0.0)
        out["move"] = score_rule(p, times, [ts(x) for x in ev["overflow_onset"]], "move", rules)
    return out


def score_rule(p: np.ndarray, times: list[datetime], events: list[datetime], tier: str,
               rules: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    if rules is None:
        res = choose_alert(p, times, events, tier)
    else:
        r = rules[tier]
        fired = [times[i] for i in model_eval.alert_events(p, times, r["p_star"], r["k"])]
        res = {"tier": tier, "rule": r, "detail": model_eval.score_alerts(fired, events)}
    fired_all = []
    r = res["chosen"] if rules is None else rules[tier]
    for i in model_eval.alert_events(p, times, r["p_star"], r["k"]):
        fired_all.append(times[i])
    res["alerts_per_year"] = alerts_per_year(fired_all, times)
    res["alert_times"] = [a.strftime("%Y-%m-%dT%H:%MZ") for a in fired_all]
    return res


def alerts_per_year(fired: list[datetime], times: list[datetime]) -> dict[str, int]:
    years = sorted({wy_of(t) for t in times})
    out = {str(y): 0 for y in years}
    for a in fired:
        out[str(wy_of(a))] = out.get(str(wy_of(a)), 0) + 1
    return out


def wy_of(t: datetime) -> int:
    return t.year + 1 if t.month >= 10 else t.year


def median_path_crossing(nc: float, meds: dict[int, float], level: float) -> float | None:
    """Hours until the median path (0 at h = 0, then the median change at 1, 3, 6, 12 h, linear between) first
    reaches `level`; None if not within 12 h."""
    hs = [0, *sorted(meds)]
    vs = [nc, *(nc + meds[h] for h in sorted(meds))]
    if vs[0] >= level:
        return 0.0
    for (h0, v0), (h1, v1) in zip(zip(hs, vs, strict=True), zip(hs[1:], vs[1:], strict=True), strict=False):
        if v1 >= level > v0:
            return h0 + (h1 - h0) * (level - v0) / (v1 - v0)
    return None


def onset_timing(val: pd.DataFrame, preds: dict[str, np.ndarray], inputs: dict[str, Any], ev: dict[str, list[str]]
                 ) -> dict[str, Any]:
    """T4 timing at 1-12 h: for each onset and each issuance 1-12 h before it, the predicted onset time (median
    path reaching the median L), the 3 h trend's, and persistence's (never, unless already at L)."""
    need = ("d_1", "d_3", "d_6", "d_12")
    if not all(t in preds for t in need):
        return {"note": "needs d_1, d_3, d_6 and d_12"}
    l_med = float(np.median(inputs["onset_levels_ft"]))
    med = {int(t[2:]): preds[t][:, model.LEVELS.index(0.5)] for t in need}
    tt = val["t"]
    rows = []
    for onset_s in ev["overflow_onset"]:
        onset = ts(onset_s)
        for i in np.where((tt < onset) & (tt >= onset - timedelta(hours=12)))[0]:
            t = tt.iloc[i].to_pydatetime()
            lead = (onset - t).total_seconds() / 3600
            nc = float(val["nc_lvl"].iloc[i])
            if not math.isfinite(nc):
                continue
            mh = median_path_crossing(nc, {h: float(med[h][i]) for h in med}, l_med)
            slope = float(np.nan_to_num(val["nc_d3h"].iloc[i])) / 3
            gap = l_med - nc
            trend_h = 0.0 if gap <= 0 else (gap / slope if slope > 0 and gap / slope <= 6 else None)
            rows.append({"onset": onset_s, "issue_time": t.strftime("%Y-%m-%dT%H:%MZ"), "lead_h": round(lead, 2),
                         "model_predicted_in_h": None if mh is None else round(mh, 2),
                         "model_error_h": None if mh is None else round(mh - lead, 2),
                         "trend_error_h": None if trend_h is None else round(trend_h - lead, 2),
                         "persistence_error_h": round(-lead, 2) if nc >= l_med else None})
    def med_abs(key: str) -> dict[str, Any]:
        v = [abs(r[key]) for r in rows if r[key] is not None]
        return {"n_with_prediction": len(v), "n_none": len(rows) - len(v),
                "median_abs_error_h": round(float(np.median(v)), 2) if v else None}
    return {"median_L_ft": l_med, "issuances": len(rows), "model": med_abs("model_error_h"),
            "trend": med_abs("trend_error_h"), "persistence": med_abs("persistence_error_h"), "rows": rows,
            "nws_note": "NWS issues no overflow-onset forecast; its first warning's forecast flood-begin time (minor "
                        "stage) is listed per event in the event table"}


def isotonic_loyo(p: np.ndarray, o: np.ndarray, wy: np.ndarray) -> dict[str, Any]:
    """Amendment 4, item 4: leave-one-validation-year-out isotonic check on pooled validation predictions."""
    check_validation_years(wy)
    from sklearn.isotonic import IsotonicRegression

    ok = np.isfinite(p) & np.isfinite(o)
    p, o, wy = p[ok], o[ok], wy[ok]
    cal = np.empty_like(p)
    for y in np.unique(wy):
        m = wy == y
        iso = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(p[~m], o[~m])
        cal[m] = iso.predict(p[m])
    raw_b, cal_b = float(((p - o) ** 2).mean()), float(((cal - o) ** 2).mean())
    return {"n": int(len(p)), "brier_raw": round(raw_b, 6), "brier_loyo_isotonic": round(cal_b, 6),
            "isotonic_wins": cal_b < raw_b}


def check_validation_years(wy: np.ndarray) -> None:
    bad = sorted({int(y) for y in np.unique(wy)} - set(train_data.VALIDATION_WY))
    if bad:
        raise train_data.HeldOutRowError(f"calibration may use validation years only; got {bad}")


def fit_calibration(p: np.ndarray, o: np.ndarray, wy: np.ndarray) -> dict[str, Any]:
    """Isotonic map fitted on pooled walk-forward validation predictions only (raises on any other year)."""
    check_validation_years(wy)
    from sklearn.isotonic import IsotonicRegression

    ok = np.isfinite(p) & np.isfinite(o)
    iso = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(p[ok], o[ok])
    return {"x": [float(v) for v in iso.X_thresholds_], "y": [float(v) for v in iso.y_thresholds_],
            "fitted_on_wy": sorted(int(y) for y in np.unique(wy[ok]))}


def apply_calibration(m: dict[str, Any], p: np.ndarray) -> np.ndarray:
    return np.where(np.isfinite(p), np.interp(p, m["x"], m["y"]), np.nan)


def level_blocks(val: pd.DataFrame, preds: dict[str, np.ndarray]) -> list[dict[str, Any]]:
    nc = val["nc_lvl"].to_numpy(dtype=float)
    d3 = val["nc_d3h"].to_numpy(dtype=float)
    wy = val["wy"].to_numpy(dtype=int)
    out = []
    for h in model.HORIZONS:
        if f"d_{h}" not in preds:
            continue
        y = val[f"d_{h}"].to_numpy(dtype=float)
        out.append(model_eval.level_skill(preds[f"d_{h}"], y, nc, d3, wy, h))
        if h in SELECTION_H:
            out.append(model_eval.level_skill(preds[f"d_{h}"], y, nc, d3, wy, h, rising_only=True))
    return out


def headline(levels: list[dict[str, Any]]) -> float | None:
    v = [r["fair_crps_model"] for r in levels if r.get("h") in SELECTION_H and not r["rising_only"]]
    return round(float(np.mean(v)), 5) if len(v) == len(SELECTION_H) else None


def score(frame: pd.DataFrame, idx: pd.DataFrame, preds: dict[str, np.ndarray], inputs: dict[str, Any],
          events: dict[str, list[str]], rules: dict[str, Any] | None = None, calib: dict[str, Any] | None = None
          ) -> dict[str, Any]:
    val, preds = joined(frame, idx, preds)
    levels = level_blocks(val, preds)
    out: dict[str, Any] = {"rows": int(len(val)), "water_years": sorted(int(y) for y in val["wy"].unique()),
                           "targets": sorted(preds), "headline_fair_crps_6_12_24": headline(levels),
                           "T6_level": levels, "crossing": crossing_blocks(val, preds, calib),
                           "overflow": overflow_blocks(val, preds, inputs["onset_levels_ft"]),
                           "alerts": alert_blocks(val, preds, inputs, events, rules, calib)}
    out["onset_timing"] = onset_timing(val, preds, inputs, events)
    return out


def _ci_met(v: float | None, ci: list[float], bar: float) -> bool | None:
    return None if v is None else bool(v > bar)


def t_table(sc: dict[str, Any]) -> list[dict[str, Any]]:
    """T1-T6 rows (amendment 1 numbering) from one scored block, each with its value, interval and met/not met."""
    rows: list[dict[str, Any]] = []
    al = sc.get("alerts", {})
    if "prepare" in al:
        d = al["prepare"].get("chosen_detail") or al["prepare"].get("detail")
        leads = [e["lead_h"] for e in d["per_event"] if e["lead_h"] is not None]
        rows.append({"target": "T1", "what": "prepare (P(>=148 ft within 24 h)) alert: hours before the >=148 ft "
                     "crossing per event; FAR <= 0.5", "events": d["events"], "pod": d["pod"],
                     "pod_ci95": d["pod_ci95"],
                     "far": d["far"], "far_ci95": d["far_ci95"], "leads_h": leads,
                     "far_part_met": bool(d["far"] is not None and d["far"] <= 0.5),
                     "fired_before_most_events": bool(len(leads) * 2 > d["events"]),
                     "met": None, "timing_part": TIMING_NOTE,
                     "note": "City-alert comparisons exist for held-out 2021/2025 only (amendment 1, A8)"})
    if "move" in al:
        d = al["move"].get("chosen_detail") or al["move"].get("detail")
        rows.append({"target": "T2", "what": "move (overflow within 12 h) alert: POD >= 0.8 and FAR <= 0.2",
                     "events": d["events"], "pod": d["pod"], "pod_ci95": d["pod_ci95"], "far": d["far"],
                     "far_ci95": d["far_ci95"], "leads_h": [e["lead_h"] for e in d["per_event"]],
                     "pod_far_part_met": bool(d["pod"] is not None and d["pod"] >= 0.8
                                              and d["far"] is not None and d["far"] <= 0.2),
                     "met": None, "timing_part": TIMING_NOTE})
    for key, blk in sc.get("crossing", {}).items():
        if not key.startswith(("moderate", "major")) or not blk.get("n"):
            continue
        nws = blk.get("rows_with_nws_warning_in_force", {})
        rows.append({"target": "T3", "what": key, "n": blk["n"], "positives": blk["positives"],
                     "mean_p_minus_obs": blk["mean_p_minus_obs"], "ci95": blk["mean_p_minus_obs_ci95"],
                     "ece": blk["ece"], "bss_vs_nws_rows_in_force": nws.get("bss_vs_nws_derived"),
                     "bss_vs_nws_ci95": nws.get("bss_vs_nws_derived_ci95"), "nws_rows": nws.get("n"),
                     "met": bool(blk["no_systematic_low_bias"] and blk["ece"] <= 0.05
                                 and (nws.get("bss_vs_nws_derived") or -1) > 0) if blk["positives"] else None})
    for key, blk in sc.get("overflow", {}).items():
        if not blk.get("n"):
            continue
        rows.append({"target": "T4", "what": key, "n": blk["n"], "positives": blk["positives"],
                     "bss_vs_persistence": blk.get("bss_vs_persistence_no_onset"),
                     "bss_vs_trend": blk.get("bss_vs_trend_reaches_median_L"),
                     "ci95_vs_trend": blk.get("bss_vs_trend_reaches_median_L_ci95"),
                     "met": bool((blk.get("bss_vs_persistence_no_onset") or -1) > 0
                                 and (blk.get("bss_vs_trend_reaches_median_L") or -1) > 0)})
    ot = sc.get("onset_timing", {})
    if ot.get("model"):
        rows.append({"target": "T4", "what": "onset timing at 1-12 h, median |error| (h)",
                     "issuances": ot["issuances"],
                     "model": ot["model"], "trend": ot["trend"], "persistence": ot["persistence"]})
    for key in ("moderate_148ft_within_12h",):
        blk = sc.get("crossing", {}).get(key)
        if blk and blk.get("n"):
            eces = {k: v["ece"] for k, v in sc["crossing"].items() if v.get("n")}
            rows.append({"target": "T5", "what": f"{key}: BSS vs persistence >= 0.10; ECE <= 0.05 per horizon",
                         "bss_vs_persistence": blk["bss_vs_persistence"], "ci95": blk["bss_vs_persistence_ci95"],
                         "ece_by_target": eces,
                         "met": bool((blk["bss_vs_persistence"] or -1) >= 0.10
                                     and all(v <= 0.05 for v in eces.values()))})
    for r in sc.get("T6_level", []):
        if r.get("h") in SELECTION_H and r.get("n"):
            rows.append({"target": "T6", "what": f"level at {r['h']} h{' (rising limbs)' if r['rising_only'] else ''}",
                         "n": r["n"], "fair_crpss": r["fair_crpss_vs_persistence"],
                         "fair_crpss_ci95": r["fair_crpss_vs_persistence_ci95"],
                         "mae_skill": r["mae_skill_vs_persistence"],
                         "mae_skill_ci95": r["mae_skill_vs_persistence_ci95"],
                         "met": bool(r["fair_crpss_vs_persistence"] > 0 and r["mae_skill_vs_persistence"] > 0)})
    return rows


def event_table(val: pd.DataFrame, preds: dict[str, np.ndarray], sc: dict[str, Any], inputs: dict[str, Any],
                catalogue: list[dict[str, Any]], relay: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every development event at >= 148 ft and every development overflow: the model's first alerts (chosen rules)
    against relay v1 and NWS's first warning. Events in training-only years have no out-of-sample prediction."""
    ids = {e["event_id"] for e in inputs["development_events_ge_148ft"]} | {
        e["event_id"] for e in inputs["development_overflow_onsets"]}
    prep = [ts(x) for x in sc["alerts"].get("prepare", {}).get("alert_times", [])]
    move = [ts(x) for x in sc["alerts"].get("move", {}).get("alert_times", [])]
    p24 = model.crossing_prob(preds["m_24"], val["nc_lvl"].to_numpy(dtype=float), THRESH["moderate"]) \
        if "m_24" in preds else None
    out = []
    for e in sorted((c for c in catalogue if c["event_id"] in ids), key=lambda c: c["event_id"]):
        rel = next((r for r in relay if r["event_id"] == e["event_id"]), {})
        nws = e.get("first_nws_warning") or {}
        row: dict[str, Any] = {"event_id": e["event_id"], "wy": e["wy"], "crest_ft": e["crest_ft"],
                               "minor_first": e["minor_first"], "moderate_first": e["moderate_first"],
                               "overflow_onset": e["overflow_onset"] if e.get("overflow_gauge_operating") else None,
                               "nws_first_warning": nws.get("issued_at"),
                               "nws_forecast_flood_begin": nws.get("forecast_flood_begin"),
                               "relay_v1_prepare": (rel.get("prepare") or {}).get("at"),
                               "relay_v1_move": (rel.get("move") or {}).get("at")}
        if e["wy"] not in set(val["wy"].unique()):
            row["model"] = "training-only year: no out-of-sample (walk-forward) prediction"
            out.append(row)
            continue
        ref = ts(e["moderate_first"] or e["minor_first"])
        onset = ts(e["overflow_onset"]) if row["overflow_onset"] else None
        anchor = min(x for x in (ref, onset) if x is not None)
        fp = [a for a in prep if anchor - timedelta(hours=72) <= a <= anchor + timedelta(hours=24)]
        fm = [a for a in move if anchor - timedelta(hours=72) <= a <= anchor + timedelta(hours=24)]
        row["model_first_prepare"] = fp[0].strftime("%Y-%m-%dT%H:%MZ") if fp else None
        row["model_first_move"] = fm[0].strftime("%Y-%m-%dT%H:%MZ") if fm else None
        if e["moderate_first"] and fp:
            row["prepare_h_before_148ft"] = round((ts(e["moderate_first"]) - fp[0]).total_seconds() / 3600, 2)
        if onset is not None:
            if fp:
                row["prepare_h_before_onset"] = round((onset - fp[0]).total_seconds() / 3600, 2)
            if fm:
                row["move_h_before_onset"] = round((onset - fm[0]).total_seconds() / 3600, 2)
            if row["relay_v1_move"]:
                lead = (onset - ts(row["relay_v1_move"])).total_seconds() / 3600
                row["relay_v1_move_h_before_onset"] = round(lead, 2)
        if p24 is not None:
            m = ((val["t"] >= ref - timedelta(hours=48)) & (val["t"] < ref)).to_numpy()
            row["max_p148_24h_in_48h_before"] = round(float(np.nanmax(p24[m])), 3) if m.any() else None
        out.append(row)
    return out


def development_report(datasets: Path, pred_dirs: list[Path], inputs_path: Path, catalogue_path: Path,
                       relay_path: Path, chosen: str | None) -> dict[str, Any]:
    """Score every saved candidate on the pooled validation predictions; the full blocks (event table, isotonic
    check, T-table) for each candidate that has every metric target."""
    import json

    from floodlead import model_dev

    inputs = json.loads(inputs_path.read_text())
    catalogue = json.loads(catalogue_path.read_text())["nooksack"]
    relay = json.loads(relay_path.read_text())["events"]
    events = inputs["validation_events"]
    frames: dict[str, pd.DataFrame] = {}
    cands = []
    for d in pred_dirs:
        for f in sorted(d.glob("preds-*.npz")):
            cid = f.stem.removeprefix("preds-")
            name = "nooksack_hourly_oracle_v1.csv.gz" if "_oracle_" in cid else "nooksack_hourly_honest_v1.csv.gz"
            if name not in frames:
                frames[name] = model_dev.load_dev(datasets / name)
            idx, preds = model_dev.load_preds(f)
            sc = score(frames[name], idx, preds, inputs, events)
            sc["candidate"] = cid
            sc["source"] = str(f)
            val, jp = joined(frames[name], idx, preds)
            if "m_24" in jp:
                p = model.crossing_prob(jp["m_24"], val["nc_lvl"].to_numpy(dtype=float), THRESH["moderate"])
                sc["isotonic_check_148ft_24h"] = isotonic_loyo(p, val["y_moderate_24h"].to_numpy(dtype=float),
                                                               val["wy"].to_numpy(dtype=int))
                b = sc["crossing"].get("moderate_148ft_within_24h", {})
                sc["tiebreak_brier_148ft_24h"] = b.get("brier")
            sc["T_table"] = t_table(sc)
            sc["events"] = event_table(val, jp, sc, inputs, catalogue, relay)
            cands.append(sc)
    ranked = sorted((c for c in cands if c["headline_fair_crps_6_12_24"] is not None and "_GR_" in c["candidate"]),
                    key=lambda c: c["headline_fair_crps_6_12_24"])
    return {"label": "development (walk-forward), used to choose the model; not the result",
            "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "selection_rule": "amendment 4, item 6: lowest pooled validation fair CRPS averaged over 6/12/24 h among "
                              "the G+R candidates; within 1 %, the lower Brier for >= 148 ft within 24 h",
            "ranking_G+R": [{"candidate": c["candidate"], "headline_fair_crps_6_12_24": c["headline_fair_crps_6_12_24"],
                             "tiebreak_brier_148ft_24h": c.get("tiebreak_brier_148ft_24h")} for c in ranked],
            "chosen": chosen, "inputs": inputs, "candidates": cands}
