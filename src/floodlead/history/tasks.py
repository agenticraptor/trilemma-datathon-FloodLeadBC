"""Task lists for each history source (Stage 3 part 2). Usage-rights records: data-contract.md.

Every source is paced well below its published limits, and every payload is archived unchanged.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

from psycopg_pool import ConnectionPool

from floodlead.history.download import Task

OGC = "https://api.weather.gc.ca/collections"
PAGE = 10_000
FIRST_YEAR = 2004  # the Nooksack 15-min history starts in Oct 2004

# Basin points for Open-Meteo (D-03.3). Each point is one grid cell's series; a basin average is the mean of its points.
BASIN_POINTS: dict[str, tuple[float, float, str]] = {
    "nooksack-nf": (48.90, -121.80, "North Fork Nooksack, upper (Glacier / Wells Creek)"),
    "nooksack-mf": (48.80, -121.95, "Middle Fork Nooksack"),
    "nooksack-sf": (48.65, -122.05, "South Fork Nooksack"),
    "nooksack-lower": (48.85, -122.25, "Nooksack mainstem, Deming to Everson"),
    "sumas-abbotsford": (49.00, -122.25, "Sumas River / Abbotsford"),
    "chilliwack-upper": (49.05, -121.55, "Chilliwack River above Slesse Creek"),
    "coquihalla-hope": (49.40, -121.30, "Coquihalla River / Hope"),
    "nicomekl-langley": (49.08, -122.65, "Nicomekl River / Langley"),
}

# ECCC hourly climate stations in and near the Fraser Valley (climate IDs; several IDs are one site over time).
ECCC_CLIMATE: dict[str, tuple[str, int, int]] = {
    "1100030": ("ABBOTSFORD A", 2004, 2012),
    "1100031": ("ABBOTSFORD A", 2011, 2026),
    "1100032": ("ABBOTSFORD A", 2016, 2026),
    "1113541": ("HOPE (AUT)", 2004, 2012),
    "1113542": ("HOPE A", 2011, 2026),
    "1113543": ("HOPE AIRPORT", 2012, 2026),
    "1106178": ("PITT MEADOWS CS", 2004, 2026),
    "1108910": ("WHITE ROCK CAMPBELL SCIENTIFIC", 2004, 2026),
}
NCEI_STATIONS = {"72797624217": "BELLINGHAM INTL AIRPORT (KBLI)"}
SNOTEL = {"909:WA:SNTL": "Wells Creek", "910:WA:SNTL": "Elbow Lake", "1011:WA:SNTL": "MF Nooksack"}
NWS_PILS = ("FLWSEW", "FLSSEW", "FFASEW", "ESFSEW")  # warnings, statements, flood watches, hydrologic outlooks


def _years(first: int, last: int | None = None) -> range:
    return range(first, (last or datetime.now(UTC).year) + 1)


def ogc_next_page(t: Task, content: bytes) -> Iterator[Task]:
    """OGC API paging: if a page came back full, queue the next offset."""
    try:
        doc: dict[str, Any] = json.loads(content)
    except ValueError:
        return
    if doc.get("numberReturned", 0) >= PAGE:
        base, off = t.key.rsplit("/", 1)
        nxt = int(off) + PAGE
        yield Task(f"{base}/{nxt}", t.url, {**t.params, "offset": str(nxt)}, f"{t.name.rsplit('_', 1)[0]}_{nxt}")


def ogc_empty(content: bytes) -> bool:
    try:
        return json.loads(content).get("numberReturned", 0) == 0
    except ValueError:
        return False


def eccc_peaks() -> list[Task]:
    p = {"PROV_TERR_STATE_LOC": "BC", "limit": str(PAGE), "offset": "0", "f": "json", "sortby": "STATION_NUMBER,DATE",
         "skipGeometry": "true"}
    return [Task("BC/0", f"{OGC}/hydrometric-annual-peaks/items", p, "peaks_BC_0")]


def eccc_daily(pool: ConnectionPool) -> list[Task]:
    with pool.connection() as conn:
        stns = [r[0] for r in conn.execute(
            "SELECT native_id FROM stations WHERE source = 'eccc' ORDER BY native_id").fetchall()]
    props = "STATION_NUMBER,DATE,LEVEL,DISCHARGE,LEVEL_SYMBOL_EN,DISCHARGE_SYMBOL_EN"
    return [Task(f"{s}/0", f"{OGC}/hydrometric-daily-mean/items",
                 {"STATION_NUMBER": s, "limit": str(PAGE), "offset": "0", "f": "json", "sortby": "DATE",
                  "skipGeometry": "true", "properties": props}, f"daily_{s}_0") for s in stns]


def eccc_climate() -> list[Task]:
    props = "CLIMATE_IDENTIFIER,UTC_DATE,LOCAL_DATE,PRECIP_AMOUNT,PRECIP_AMOUNT_FLAG,TEMP,TEMP_FLAG"
    out = []
    for cid, (_, first, last) in ECCC_CLIMATE.items():
        for y in _years(max(first, FIRST_YEAR), last):
            out.append(Task(f"{cid}/{y}/0", f"{OGC}/climate-hourly/items",
                            {"CLIMATE_IDENTIFIER": cid, "datetime": f"{y}-01-01T00:00:00Z/{y + 1}-01-01T00:00:00Z",
                             "limit": str(PAGE), "offset": "0", "f": "json", "sortby": "UTC_DATE",
                             "skipGeometry": "true", "properties": props}, f"climate_{cid}_{y}_0"))
    return out


def iem_nws() -> list[Task]:
    url = "https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py"
    return [Task(f"{pil}/{y}", url, {"pil": pil, "sdate": f"{y}-01-01", "edate": f"{y + 1}-01-01", "fmt": "text",
                                    "limit": "9999"}, f"{pil}_{y}")
            for pil in NWS_PILS for y in _years(FIRST_YEAR)]


def ncei() -> list[Task]:
    url = "https://www.ncei.noaa.gov/access/services/data/v1"
    return [Task(f"{st}/{y}", url, {"dataset": "global-hourly", "stations": st, "startDate": f"{y}-01-01",
                                    "endDate": f"{y}-12-31", "format": "csv"}, f"global_hourly_{st}_{y}")
            for st in NCEI_STATIONS for y in _years(FIRST_YEAR)]


def snotel() -> list[Task]:
    url = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data"
    return [Task(f"hourly/{y}", url, {"stationTriplets": ",".join(SNOTEL), "elements": "PREC,TOBS,WTEQ,SNWD",
                                     "duration": "HOURLY", "beginDate": f"{y}-01-01", "endDate": f"{y}-12-31"},
                 f"snotel_hourly_{y}") for y in _years(FIRST_YEAR)]


def _om(kind: str, url: str, hourly: str, first_year: int) -> list[Task]:
    today = date.today()
    out = []
    for name, (lat, lon, _) in BASIN_POINTS.items():
        for y in _years(first_year):
            end = min(date(y, 12, 31), today)
            out.append(Task(f"{name}/{y}", url, {"latitude": f"{lat:.2f}", "longitude": f"{lon:.2f}",
                                                 "start_date": f"{y}-01-01", "end_date": end.isoformat(),
                                                 "hourly": hourly, "timezone": "GMT"}, f"{kind}_{name}_{y}"))
    return out


def openmeteo_archive() -> list[Task]:
    return _om("archive", "https://archive-api.open-meteo.com/v1/archive",
               "precipitation,rain,snowfall,temperature_2m,snow_depth,soil_moisture_0_to_7cm", FIRST_YEAR)


def openmeteo_histfc() -> list[Task]:
    # Assembled from the first hours of each archived model run (not a long-lead forecast); start probed per D-03.3.
    return _om("histfc", "https://historical-forecast-api.open-meteo.com/v1/forecast",
               "precipitation,rain,snowfall,temperature_2m,freezing_level_height", 2020)


def openmeteo_prevruns() -> list[Task]:
    # Forecasts as issued 1 and 2 days before the valid hour (`_previous_dayN`); probed to exist from early 2024.
    return _om("prevruns", "https://previous-runs-api.open-meteo.com/v1/forecast",
               "precipitation,precipitation_previous_day1,precipitation_previous_day2,"
               "temperature_2m,temperature_2m_previous_day1,temperature_2m_previous_day2", 2023)
