#!/usr/bin/env python3
"""Reproduce FloodLead forecasts from the public API alone (Stage 2, AC-6).

For each chosen `forecast` ledger entry this fetches the station's level observations from the public
observations API, keeps only rows first seen before the forecast's created_at (as the issuer did), and recomputes
- input_hash (sha256 of the canonical [[ts, value]] list for the 3 h ending at data_as_of), and
- for persistence-v1, the median (q 0.5) at every horizon, from the same empirical error-path library.
ECCC stations only: their library is the trailing 30 days, which the public API serves (USGS libraries also use
prior years' seasons). A mismatch can come from a value revised after created_at (the API serves current values;
revisions are in observation_revisions), and the script says so instead of hiding it.

Usage: uv run python scripts/reproduce_forecast.py --api https://<host> [--n 3] [--seed 1] [--seq N ...]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import urllib.request
from datetime import datetime, timedelta

import numpy as np

from floodlead import baselines as bl
from floodlead import ledger
from floodlead.issuer import TRAILING, input_hash

STEP = timedelta(minutes=5)


def get(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "floodlead-reproduce/1"}),
                                timeout=120) as r:
        return json.load(r)


def iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def public_rows(api: str, sid: str, t0: datetime, t1: datetime, created: datetime) -> list[tuple[datetime, float]]:
    rows, cur = [], t0
    while cur <= t1:
        nxt = min(cur + timedelta(days=7), t1 + timedelta(seconds=1))
        page = get(f"{api}/v1/stations/{sid}/observations?param=level&since={iso(cur)}&until={iso(nxt)}")
        for o in page["observations"]:
            ts = parse(o["ts"])
            if o["value"] is not None and ts <= created and parse(o["first_seen_at"]) <= created:
                rows.append((ts, o["value"]))
        cur = nxt
    return sorted(set(rows))


def reproduce(api: str, entry: dict) -> dict:
    body = json.loads(entry["canonical"])
    d = body["data"]
    created = parse(body["created_at"])
    asof = parse(d["data_as_of"])
    base = parse(d["base_time"])
    rows = public_rows(api, d["station_id"], asof - TRAILING, asof, created)
    inputs = [(t, v) for t, v in rows if t >= asof - bl.TREND_WINDOW]
    ih = input_hash(inputs)
    out = {"seq": entry["seq"], "station_id": d["station_id"], "model": d["model"], "base_time": d["base_time"],
           "input_hash_ledger": d["input_hash"], "input_hash_recomputed": ih, "input_hash_match": ih == d["input_hash"]}
    if d["model"] != "persistence-v1":
        return out
    g = bl.to_grid(rows, STEP, start=asof - TRAILING, end=asof)
    d_idx = len(g.y) - 1
    window_pts, cap_pts = int(bl.TREND_WINDOW / STEP), int(bl.TREND_CAP / STEP)
    max_lead = math.ceil(bl.MAX_LEAD / STEP)
    origins = np.arange(window_pts, d_idx - max_lead + 1, int(timedelta(hours=1) / STEP))
    E, used = bl.error_paths("persistence-v1", g, origins, max_lead, window_pts, cap_pts, int(bl.FFILL_LIMIT / STEP))
    y_d = float(g.y[d_idx])
    samples = y_d + E
    med = {}
    for hz in d["horizons"]:
        lead = int(round((base + timedelta(hours=hz["h"]) - asof) / STEP))
        med[hz["h"]] = (ledger.r4(float(np.quantile(samples[:, lead - 1], 0.5))), hz["q"]["0.5"])
    out.update(library_paths_recomputed=int(len(E)), library_paths_ledger=d["error_library"]["paths"],
               median_by_h={h: {"recomputed": a, "ledger": b} for h, (a, b) in med.items()},
               median_match=all(a == b for a, b in med.values()))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--seq", type=int, nargs="*")
    a = ap.parse_args()
    api = a.api.rstrip("/")
    seqs = a.seq
    if not seqs:
        head = get(f"{api}/v1/ledger/head")["seq"]
        rnd = random.Random(a.seed)
        seqs = []
        tries = 0
        while len(seqs) < a.n and tries < 500:
            tries += 1
            e = get(f"{api}/v1/ledger/{rnd.randint(2, head)}")
            dd = json.loads(e["canonical"])
            if e["entry_type"] == "forecast" and dd["data"]["model"] == "persistence-v1" \
                    and dd["data"]["station_id"].startswith("eccc:"):
                seqs.append(e["seq"])
    ok = True
    for s in seqs:
        r = reproduce(api, get(f"{api}/v1/ledger/{s}"))
        ok &= r["input_hash_match"] and r.get("median_match", True)
        print(json.dumps(r))
    print("ALL MATCH" if ok else "MISMATCH (see above; a value revised after created_at can cause this)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
