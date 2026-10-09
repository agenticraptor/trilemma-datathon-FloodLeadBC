"""Parse archived rainfall payloads into rain_hourly and openmeteo_hourly (Stage 3 part 2; D-03.13).

Time convention: every row's ts is the END of the hour it covers, in UTC.
- ECCC climate-hourly: UTC_DATE is the observation hour; PRECIP_AMOUNT is the amount in the hour ending then.
- NCEI Global Hourly (KBLI): routine METARs (REPORT_TYPE FM-15, about :53) with AA1 period 01 h: depth/10 mm in the
  hour ending at the report; assigned to the next whole hour. TMP is tenths of a degree C; +9999 is missing.
- SNOTEL (AWDB hourly): timestamps in local standard time (PST, UTC-8, all year); PREC is the water-year accumulation
  in inches, so the hourly amount is its increase (negative steps, e.g. the Oct 1 reset or sensor noise, become 0 and
  are flagged); TOBS degF; WTEQ and SNWD inches.
- Open-Meteo: `hourly.time` in GMT (requested) with values for the preceding hour (precipitation sums).
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

PST = timedelta(hours=-8)
IN_MM = 25.4


def eccc_climate(doc: dict[str, Any], raw_id: int) -> Iterator[tuple]:
    for f in doc.get("features", []):
        p = f["properties"]
        if not p.get("UTC_DATE"):
            continue
        ts = datetime.fromisoformat(p["UTC_DATE"]).replace(tzinfo=UTC)
        flags = ",".join(x for x in (p.get("PRECIP_AMOUNT_FLAG"), p.get("TEMP_FLAG")) if x) or None
        yield ("eccc-climate", str(p["CLIMATE_IDENTIFIER"]), ts, p.get("PRECIP_AMOUNT"), p.get("TEMP"), None, None,
               flags, raw_id)


def _ceil_hour(t: datetime) -> datetime:
    base = t.replace(minute=0, second=0, microsecond=0)
    return base if base == t else base + timedelta(hours=1)


def ncei(text: str, raw_id: int) -> Iterator[tuple]:
    seen: set[datetime] = set()
    for r in csv.DictReader(io.StringIO(text)):
        if r.get("REPORT_TYPE", "").strip() != "FM-15":
            continue
        t = _ceil_hour(datetime.fromisoformat(r["DATE"]).replace(tzinfo=UTC))
        if t in seen:
            continue
        precip = None
        aa = (r.get("AA1") or "").split(",")
        if len(aa) >= 4 and aa[0] == "01" and aa[1] != "9999":
            precip = int(aa[1]) / 10.0
        temp = None
        tmp = (r.get("TMP") or "").split(",")
        if tmp and tmp[0] not in ("", "+9999"):
            temp = int(tmp[0]) / 10.0
        seen.add(t)
        yield ("ncei", r["STATION"], t, precip, temp, None, None, f"AA1q={aa[3]}" if len(aa) >= 4 else None, raw_id)


def snotel(doc: list[dict[str, Any]], raw_id: int) -> Iterator[tuple]:
    for st in doc:
        site = st["stationTriplet"]
        series: dict[str, dict[datetime, float]] = {}
        for d in st.get("data", []):
            code = d["stationElement"]["elementCode"]
            vals = {}
            for v in d.get("values", []):
                if v.get("value") is None:
                    continue
                # local standard time -> UTC; the value at hh:00 covers the hour ending then
                vals[(datetime.fromisoformat(v["date"]) - PST).replace(tzinfo=UTC)] = float(v["value"])
            series[code] = vals
        prec = series.get("PREC", {})
        times = sorted(set().union(*[set(v) for v in series.values()])) if series else []
        prev_t = prev_v = None
        for t in times:
            amount, flag = None, None
            if t in prec and prev_t is not None and prev_v is not None and t - prev_t == timedelta(hours=1):
                inc = prec[t] - prev_v
                amount, flag = (max(inc, 0.0) * IN_MM, "neg_step" if inc < 0 else None)
            if t in prec:
                prev_t, prev_v = t, prec[t]
            tobs = series.get("TOBS", {}).get(t)
            swe = series.get("WTEQ", {}).get(t)
            snwd = series.get("SNWD", {}).get(t)
            yield ("snotel", site, t, amount, None if tobs is None else (tobs - 32) * 5 / 9,
                   None if swe is None else swe * IN_MM, None if snwd is None else snwd * 2.54, flag, raw_id)


OM_COLS = {"precipitation": "precip_mm", "rain": "rain_mm", "snowfall": "snowfall_cm", "temperature_2m": "temp_c",
           "snow_depth": "snow_depth_m", "soil_moisture_0_to_7cm": "soil_moisture",
           "freezing_level_height": "freezing_level_m", "precipitation_previous_day1": "precip_prev_day1_mm",
           "precipitation_previous_day2": "precip_prev_day2_mm", "temperature_2m_previous_day1": "temp_prev_day1_c",
           "temperature_2m_previous_day2": "temp_prev_day2_c"}
OM_ORDER = list(dict.fromkeys(OM_COLS.values()))


def openmeteo(doc: dict[str, Any], kind: str, point: str, raw_id: int) -> Iterator[tuple]:
    h = doc.get("hourly", {})
    cols = {OM_COLS[k]: v for k, v in h.items() if k in OM_COLS}
    for i, t in enumerate(h.get("time", [])):
        vals = [cols[c][i] if c in cols else None for c in OM_ORDER]
        if all(v is None for v in vals):
            continue
        yield (kind, point, datetime.fromisoformat(t).replace(tzinfo=UTC), *vals, raw_id)


def load(pool) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """(Re)load every downloaded rainfall payload (derived tables: rows for each payload are replaced)."""
    from floodlead import archive
    from floodlead.config import get_settings

    s = get_settings()
    counts: dict[str, int] = {}
    with pool.connection() as conn:
        conn.autocommit = True  # each payload commits on its own, so its ON COMMIT DROP temp table goes with it
        conn.execute("SET statement_timeout = '30min'")
        pages = conn.execute(
            "SELECT h.source, h.key, r.raw_object_id, r.archive_path FROM history_downloads h JOIN raw_objects r"
            " USING (raw_object_id) WHERE h.status = 'ok' AND h.source IN ('eccc-climate', 'ncei', 'snotel',"
            " 'openmeteo-archive', 'openmeteo-histfc', 'openmeteo-prevruns') ORDER BY 1, 2").fetchall()
        for src, key, rid, path in pages:
            data = archive.read(s.archive_dir, path)
            if src != "ncei":
                try:
                    json.loads(data)
                except ValueError:  # an invalid body recorded as ok by an older downloader: skip and report
                    counts[f"invalid:{src}"] = counts.get(f"invalid:{src}", 0) + 1
                    continue
            if src == "eccc-climate":
                rows, table = list(eccc_climate(json.loads(data), rid)), "rain_hourly"
            elif src == "ncei":
                rows, table = list(ncei(data.decode(), rid)), "rain_hourly"
            elif src == "snotel":
                rows, table = list(snotel(json.loads(data), rid)), "rain_hourly"
            else:
                kind = src.split("-", 1)[1]
                rows, table = list(openmeteo(json.loads(data), kind, key.split("/")[0], rid)), "openmeteo_hourly"
            cols = ("source, site, ts, precip_mm, temp_c, swe_mm, snow_depth_cm, flags, raw_object_id"
                    if table == "rain_hourly" else f"kind, point, ts, {', '.join(OM_ORDER)}, raw_object_id")
            with conn.transaction():
                conn.execute(f"DELETE FROM {table} WHERE raw_object_id = %s", (rid,))
                # Adjacent yearly payloads can overlap by one boundary hour: stage, then keep the first row per key.
                conn.execute(f"CREATE TEMP TABLE _stage (LIKE {table}) ON COMMIT DROP")
                with conn.cursor().copy(f"COPY _stage ({cols}) FROM STDIN") as cp:
                    for r in rows:
                        cp.write_row(r)
                n = conn.execute(f"INSERT INTO {table} ({cols}) SELECT DISTINCT ON (1, 2, 3) {cols} FROM _stage"
                                 " ORDER BY 1, 2, 3 ON CONFLICT DO NOTHING").rowcount
            counts[src] = counts.get(src, 0) + n
    return counts
