"""Summarize coverage, cadence, history and flood signal for the demo gauges.

Run after pull_gauges.py (same folder). Uses only the Python standard library.
Data: ECCC Water Survey of Canada via api.weather.gc.ca (Open Government Licence - Canada).
"""
import json, csv, statistics as st
from collections import defaultdict
from datetime import datetime, date, timedelta

ST = ["08MH001", "08MH029", "08MH024", "08MH155", "08MF062", "08MH103", "08MH056"]

def is_sentinel(v):
    return v is not None and abs(v) >= 9999

rows = []
summ = {}
for s in ST:
    d = json.load(open(f"{s}.json"))
    rt = sorted(d["rt"], key=lambda r: r["DATETIME"])
    dm = sorted(d["dm"], key=lambda r: r["DATE"])
    ts = [datetime.fromisoformat(r["DATETIME"].replace("Z", "+00:00")) for r in rt]
    gaps = [(b - a).total_seconds() / 60 for a, b in zip(ts, ts[1:])]
    sentinels = sum(1 for r in rt if is_sentinel(r["LEVEL"]) or is_sentinel(r["DISCHARGE"]))
    q_days = [r for r in dm if r["DISCHARGE"] is not None]
    ann = defaultdict(float)
    for r in q_days:
        ann[r["DATE"][:4]] = max(ann[r["DATE"][:4]], r["DISCHARGE"])
    q2 = st.median(ann.values())
    summ[s] = q2
    rows.append({
        "station": s, "name": rt[0]["STATION_NAME"],
        "realtime_rows_30d": len(rt), "realtime_from": rt[0]["DATETIME"], "realtime_to": rt[-1]["DATETIME"],
        "median_step_min": st.median(gaps), "max_gap_h": round(max(gaps) / 60, 1),
        "realtime_has_discharge": any(r["DISCHARGE"] is not None for r in rt),
        "sentinel_rows": sentinels,
        "daily_from": dm[0]["DATE"], "daily_to": dm[-1]["DATE"],
        "daily_discharge_days": len(q_days), "years_with_discharge": len(ann),
        "median_annual_max_m3s": round(q2, 1),
    })

with open("station_summary.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(rows)

# Signal checks at Vedder Crossing (08MH001) with the upstream gauge (08MH103)
def daily(s):
    return {r["DATE"]: r["DISCHARGE"] for r in json.load(open(f"{s}.json"))["dm"] if r["DISCHARGE"] is not None}

v, up = daily("08MH001"), daily("08MH103")
qv, qu = summ["08MH001"], summ["08MH103"]
prev = lambda d: (date.fromisoformat(d) - timedelta(1)).isoformat()
events = [d for d in sorted(v) if prev(d) in v and v[prev(d)] < qv <= v[d]]
sudden = sum(1 for d in events if v[prev(d)] < 0.5 * qv)
with_up = [d for d in events if d in up]
up_same = sum(1 for d in with_up if up[d] >= qu)
up_prev = sum(1 for d in with_up if up.get(prev(d), 0) >= qu)
print(json.dumps({
    "vedder_threshold_crossing_events": len(events),
    "events_since_2000": sum(1 for d in events if d >= "2000"),
    "events_with_previous_day_below_half_threshold": sudden,
    "events_with_upstream_data": len(with_up),
    "upstream_above_own_threshold_same_day": up_same,
    "upstream_above_own_threshold_previous_day": up_prev,
}, indent=2))
