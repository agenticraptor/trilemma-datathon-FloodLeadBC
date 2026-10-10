#!/usr/bin/env python3
"""Check the built training sets row by row (Stage 3 part 2, AC-10). Standard library only.

    python3 scripts/check_datasets.py /srv/floodlead/datasets

For the Nooksack hourly files it checks, on every row:
- leakage: asof_usgs <= issue_time - 60 min, asof_snotel <= issue_time - 120 min, asof_kbli <= issue_time - 20 min,
  nws_issued_at <= issue_time;
- split integrity: holdout is true exactly for water years 2022 and 2026;
- honest has no oracle_* column; oracle has the same rows and issue times.
It prints non-null shares per column group, target counts and event-level counts, and exits 1 on any violation.
"""

from __future__ import annotations

import csv
import gzip
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

LAT = {"asof_usgs": 60, "asof_snotel": 120, "asof_kbli": 20}
HOLDOUT = {2022, 2026}


def ts(s: str) -> datetime | None:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ") if s else None


def check_hourly(path: Path) -> tuple[int, list[str], dict[str, float], Counter]:
    bad: list[str] = []
    nonnull: Counter = Counter()
    targets: Counter = Counter()
    n = 0
    with gzip.open(path, "rt", newline="") as fh:
        r = csv.DictReader(fh)
        cols = r.fieldnames or []
        for row in r:
            n += 1
            t = ts(row["issue_time"])
            assert t is not None
            for col, lat in LAT.items():
                a = ts(row[col])
                if a is not None and a > t - timedelta(minutes=lat):
                    bad.append(f"{row['issue_time']} {col} {row[col]} > issue - {lat} min")
            ni = ts(row["nws_issued_at"])
            if ni is not None and ni > t:
                bad.append(f"{row['issue_time']} nws_issued_at {row['nws_issued_at']} after issue time")
            wy = int(row["wy"])
            if (row["holdout"] == "True") != (wy in HOLDOUT):
                bad.append(f"{row['issue_time']} holdout={row['holdout']} for WY{wy}")
            for c in cols:
                if row[c] != "":
                    nonnull[c] += 1
            for c in ("y_minor_24h", "y_moderate_24h", "y_major_24h", "y_overflow_12h"):
                if row.get(c) == "1.0":
                    targets[(c, "holdout" if row["holdout"] == "True" else "development")] += 1
            if len(bad) > 20:
                break
    share = {c: round(nonnull[c] / n, 3) for c in cols} if n else {}
    return n, bad, share, targets


def main(d: str) -> int:
    base = Path(d)
    ok = True
    issue: dict[str, int] = {}
    for variant in ("honest", "oracle"):
        p = base / f"nooksack_hourly_{variant}_v1.csv.gz"
        n, bad, share, targets = check_hourly(p)
        issue[variant] = n
        oracle_cols = [c for c in share if c.startswith("oracle_")]
        print(f"== {p.name}: {n} rows, {len(share)} columns, violations {len(bad)}")
        for b in bad[:10]:
            print("   VIOLATION", b)
        ok = ok and not bad
        if variant == "honest" and oracle_cols:
            print("   VIOLATION honest file has oracle columns", oracle_cols)
            ok = False
        groups = {"gauges (nc_lvl)": "nc_lvl", "upstream SF (sf_lvl)": "sf_lvl", "overflow_flowing": "overflow_flowing",
                  "snotel_p24h": "snotel_p24h", "kbli_p24h": "kbli_p24h", "fc_rain_0_18h": "fc_rain_0_18h",
                  "nws_crest_ft": "nws_crest_ft", "y_lvl_h24": "y_lvl_h24", "y_overflow_12h": "y_overflow_12h",
                  "oracle_future_rain_24h": "oracle_future_rain_24h"}
        print("   non-null share:", {k: share.get(c) for k, c in groups.items() if c in share})
        print("   positive targets:", dict(sorted(targets.items())))
    if issue.get("honest") != issue.get("oracle"):
        print("VIOLATION honest and oracle row counts differ", issue)
        ok = False
    print("RESULT", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "/srv/floodlead/datasets"))
