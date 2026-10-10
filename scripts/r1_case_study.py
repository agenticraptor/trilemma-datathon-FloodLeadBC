#!/usr/bin/env python3
"""R1 (protocol amendment 3): the AI-rainfall case study, one event, descriptive.

Reads only what R0 already cached (Open-Meteo Previous Runs, Dec 7-12 2025, day-1 and day-2 leads, five models, the
three Nooksack SNOTEL sites) and the SNOTEL hourly gauge totals exported from `rain_hourly` (no new API calls).
Windows end at North Cedarville's minor crossing, 2025-12-10 20:15Z: hours ending 21:00Z Dec 9 ... 20:00Z Dec 10
(24 h) and 21:00Z Dec 8 ... 20:00Z Dec 10 (48 h). Both sources label an hour by its end (Open-Meteo: "values for the
preceding hour"; rain_hourly: ts = end of the hour). Standard library only.

    python3 scripts/r1_case_study.py /srv/floodlead/datasets/r0 /srv/floodlead/datasets/r1/snotel_truth.csv OUT.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

SITES = {"909": "909:WA:SNTL Wells Creek", "910": "910:WA:SNTL Elbow Lake", "1011": "1011:WA:SNTL MF Nooksack"}
MODELS = ("ecmwf_aifs025_single", "ecmwf_ifs025", "gem_hrdps_continental", "ncep_hrrr_conus", "ncep_nbm_conus")
LEADS = {"day1": "precipitation_previous_day1", "day2": "precipitation_previous_day2"}
END = datetime(2025, 12, 10, 20, tzinfo=UTC)
WINDOWS = {"24h": 24, "48h": 48}
LABEL = "one event, descriptive"


def hours(n: int) -> list[str]:
    return [(END - timedelta(hours=n - 1 - i)).strftime("%Y-%m-%dT%H:%M") for i in range(n)]


def heaviest_6h_end(series: list[float], hs: list[str]) -> str | None:
    best, at = -1.0, None
    for i in range(5, len(series)):
        s = sum(series[i - 5 : i + 1])
        if s > best:
            best, at = s, hs[i]
    return at


def main(r0: Path, truth_csv: Path, out: Path) -> int:
    truth: dict[str, dict[str, float | None]] = {}
    for site, t, v in csv.reader(truth_csv.open()):
        truth.setdefault(site.split(":")[0], {})[t] = float(v) if v else None
    rows, sources = [], {}
    for sid, name in SITES.items():
        raw = (r0 / f"{sid}.json").read_bytes()
        sources[f"r0/{sid}.json"] = hashlib.sha256(raw).hexdigest()
        doc = json.loads(raw)
        times = doc["hourly"]["time"]
        for wname, n in WINDOWS.items():
            hs = hours(n)
            obs = [truth.get(sid, {}).get(h) for h in hs]
            obs_ok = all(v is not None for v in obs)
            obs_total = round(sum(obs), 1) if obs_ok else None
            obs_peak = heaviest_6h_end(obs, hs) if obs_ok else None
            for m in MODELS:
                for lead, var in LEADS.items():
                    vals = doc["hourly"].get(f"{var}_{m}") or []
                    by_t = dict(zip(times, vals, strict=False))
                    fc = [by_t.get(h) for h in hs]
                    row = {"site": name, "window": wname, "model": m, "lead": lead, "observed_mm": obs_total,
                           "observed_heaviest_6h_end": obs_peak}
                    if any(v is None for v in fc):
                        row.update({"forecast_mm": None, "note": f"{sum(v is None for v in fc)} of {n} hours empty"})
                    else:
                        tot = round(sum(fc), 1)
                        pk = heaviest_6h_end(fc, hs)
                        row.update({"forecast_mm": tot,
                                    "ratio_forecast_to_observed": round(tot / obs_total, 2) if obs_total else None,
                                    "forecast_heaviest_6h_end": pk,
                                    "timing_error_h": None if not (pk and obs_peak) else round(
                                        (datetime.fromisoformat(pk) - datetime.fromisoformat(obs_peak))
                                        .total_seconds() / 3600)})
                    rows.append(row)
    aifs = json.loads((r0 / "909.json").read_text())["hourly"].get("precipitation_previous_day1_ecmwf_aifs025_single")
    body = {"label": LABEL,
            "what": "R1, protocol amendment 3: forecast rain at day-1 and day-2 lead against SNOTEL gauge totals, "
                    "24 h and 48 h before North Cedarville's minor crossing (2025-12-10 20:15Z)",
            "changes_nothing": "Whatever it shows, this changes nothing in the product before Demo Day (amendment 3).",
            "windows": {k: [hours(n)[0], hours(n)[-1]] for k, n in WINDOWS.items()},
            "truth": "SNOTEL hourly gauge totals (rain_hourly, source snotel), never IMERG; storage gauges can "
                     "under-catch in wind and snow, and report in 0.1 in (2.54 mm) steps",
            "caveats": ["AIFS is treated as 6-hourly information: Open-Meteo interpolates it to hours, so its "
                        "heaviest-6-h timing has 6-h resolution",
                        "Open-Meteo returns one coordinate per request; each model is read at its own nearest grid "
                        "cell. Sites 910 and 1011 share an ECMWF 0.25 degree cell",
                        "HRDPS and HRRR have no day-2 lead (their runs are shorter than 48 h); R0 recorded this",
                        "The 48 h window holds two bursts (Dec 8 21Z-Dec 9 08Z and Dec 10); a heaviest-6-h timing "
                        "error near 36 h means the forecast's heaviest 6 h fell in the other burst",
                        "One storm at three gauges: no skill or ranking is claimed"],
            "aifs_hourly_sample_day1_909_first_12": aifs[:12] if aifs else None,
            "sources_sha256": sources, "truth_file_sha256": hashlib.sha256(truth_csv.read_bytes()).hexdigest(),
            "api_calls": 0, "rows": rows}
    out.write_text(json.dumps(body, indent=1))
    for r in rows:
        if r["window"] == "48h":
            print(r["site"][:4], r["model"][:22].ljust(22), r["lead"], r["observed_mm"], r.get("forecast_mm"),
                  r.get("ratio_forecast_to_observed"), r.get("timing_error_h"))
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])))
