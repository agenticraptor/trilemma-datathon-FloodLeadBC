#!/usr/bin/env python3
"""R0 (protocol amendment 3): which models in Open-Meteo's Previous Runs API return precipitation at fixed leads
(day 1, day 2) over Dec 7-12, 2025, at the three Nooksack SNOTEL sites. One request per site, all models; responses
cached on disk; requests counted. Standard library only.

    python3 scripts/r0_availability.py /srv/floodlead/datasets/r0
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "FloodLeadBC/0.3 (+https://github.com/agenticraptor/trilemma-datathon-FloodLeadBC)"}
SITES = {"909:WA:SNTL Wells Creek": (48.8661, -121.7898), "910:WA:SNTL Elbow Lake": (48.6909, -121.9089),
         "1011:WA:SNTL MF Nooksack": (48.8244, -121.9295)}
MODELS = ("ecmwf_aifs025_single", "ecmwf_ifs025", "gem_hrdps_continental", "ncep_hrrr_conus", "ncep_nbm_conus")
VARS = ("precipitation", "precipitation_previous_day1", "precipitation_previous_day2")


def main(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    log = {"requests": 0, "sites": {}}
    for name, (lat, lon) in SITES.items():
        cache = out / f"{name.split(':')[0]}.json"
        if cache.exists():
            doc = json.loads(cache.read_text())
        else:
            q = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "hourly": ",".join(VARS),
                                        "models": ",".join(MODELS), "start_date": "2025-12-07",
                                        "end_date": "2025-12-12", "timezone": "GMT"})
            url = f"https://previous-runs-api.open-meteo.com/v1/forecast?{q}"
            try:
                body = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()
            except urllib.error.HTTPError as e:
                body = e.read()
            log["requests"] += 1
            cache.write_bytes(body)
            doc = json.loads(body)
            time.sleep(3)
        if doc.get("error"):
            log["sites"][name] = {"error": doc.get("reason")}
            continue
        h = doc.get("hourly", {})
        res = {}
        for m in MODELS:
            res[m] = {}
            for v in VARS:
                vals = h.get(f"{v}_{m}") or []
                nn = [x for x in vals if x is not None]
                res[m][v] = {"hours": len(vals), "non_null": len(nn), "total_mm": round(sum(nn), 1) if nn else None}
        log["sites"][name] = {"grid": [doc.get("latitude"), doc.get("longitude"), doc.get("elevation")],
                              "models": res}
    (out / "r0_summary.json").write_text(json.dumps(log, indent=1))
    print(json.dumps(log, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "r0")))
