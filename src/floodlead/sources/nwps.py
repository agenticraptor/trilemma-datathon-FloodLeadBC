"""NOAA NWS National Water Prediction Service: official forecasts and flood categories.

Every distinct forecast issuance (keyed by issuedTime) is stored unmodified in
official_forecasts. Flood categories become `official_thresholds` on the matching USGS station.
NWPS observed series duplicate USGS gauge data, so they are archived raw but not loaded into
observations (USGS is the system of record for observations).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from floodlead import archive, http, log, store, units
from floodlead.config import get_settings

L = log.get(__name__)

SOURCE = "nwps"
GAUGES = ["NRKW1", "NREW1", "NOEW1", "NKLW1", "NKSW1", "SUMW1"]
NOT_DEFINED = -9999  # NWPS marks undefined flood categories with -9999


def _ts(s: str | None) -> datetime | None:
    if not s or s.startswith("0001-"):
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)


def thresholds_from_gauge(g: dict[str, Any], raw_object_id: int | None) -> dict[str, Any]:
    flood = g.get("flood") or {}
    cats: dict[str, Any] = {}
    for name, v in (flood.get("categories") or {}).items():
        stage = v.get("stage")
        flow = v.get("flow")
        entry: dict[str, Any] = {}
        if stage is not None and stage != NOT_DEFINED:
            entry["stage_ft"] = stage
            entry["stage_m"] = round(stage * units.FT_TO_M, 4)
        if flow is not None and flow != NOT_DEFINED:
            entry["flow_cfs"] = flow
            entry["flow_m3s"] = round(flow * units.CFS_TO_CMS, 3)
        if entry:
            cats[name] = entry
    return {
        "source": "NOAA NWS National Water Prediction Service (official flood categories)",
        "lid": g.get("lid"),
        "stage_units": flood.get("stageUnits"),
        "flow_units": flood.get("flowUnits"),
        "categories": cats,
        "raw_object_id": raw_object_id,
    }


def parse_forecast(payload: dict[str, Any]) -> tuple[datetime | None, list[dict[str, Any]]]:
    fc = payload.get("forecast") or {}
    issued = _ts(fc.get("issuedTime"))
    rows = []
    for d in fc.get("data") or []:
        valid = _ts(d.get("validTime"))
        if issued is None or valid is None:
            continue
        rows.append({"issued_at": issued, "valid_at": valid, "stage_ft": d.get("primary"),
                     "flow_kcfs": d.get("secondary"), "generated_at": _ts(d.get("generatedTime"))})
    return issued, rows


def store_forecast(
    conn: psycopg.Connection, lid: str, rows: list[dict[str, Any]], fetched_at: datetime, rid: int
) -> int:
    n = 0
    for r in rows:
        cur = conn.execute(
            """
            INSERT INTO official_forecasts (lid, issued_at, valid_at, stage_ft, flow_kcfs, generated_at,
                                            fetched_at, raw_object_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (lid, issued_at, valid_at) DO NOTHING
            """,
            (lid, r["issued_at"], r["valid_at"], r["stage_ft"], r["flow_kcfs"], r["generated_at"],
             fetched_at, rid),
        )
        n += cur.rowcount
    return n


def attach_to_station(
    conn: psycopg.Connection, usgs_id: str, lid: str, g: dict[str, Any], raw_object_id: int | None
) -> None:
    """Set official thresholds and NWPS links on the USGS station. Name and location come from
    USGS when the station already exists; NWPS only fills them for a station not yet seen."""
    conn.execute(
        """
        INSERT INTO stations (station_id, source, native_id, name, lat, lon, region, official_thresholds,
                              links, meta)
        VALUES (%(sid)s, 'usgs', %(nid)s, %(name)s, %(lat)s, %(lon)s, %(region)s, %(thr)s, %(links)s, %(meta)s)
        ON CONFLICT (station_id) DO UPDATE SET
            official_thresholds = EXCLUDED.official_thresholds,
            links = stations.links || EXCLUDED.links,
            meta = stations.meta || EXCLUDED.meta,
            updated_at = now()
        """,
        {
            "sid": f"usgs:{usgs_id}", "nid": usgs_id, "name": g.get("name"), "lat": g.get("latitude"),
            "lon": g.get("longitude"), "region": (g.get("state") or {}).get("abbreviation"),
            "thr": Jsonb(thresholds_from_gauge(g, raw_object_id)),
            "links": Jsonb({"nwps_lid": lid, "nwps": f"https://water.noaa.gov/gauges/{lid.lower()}"}),
            "meta": Jsonb({"nwps_forecast_service": g.get("forecastReliability")}),
        },
    )


def ingest_live(pool: ConnectionPool, job: str = "live") -> int:
    s = get_settings()
    base = s.nwps_base
    with pool.connection() as conn, http.client() as c:
        conn.autocommit = True
        with store.Run(conn, SOURCE, job) as run:
            run.items_total = len(GAUGES)
            issued: dict[str, Any] = {}
            for lid in GAUGES:
                try:
                    g = http.fetch(c, f"{base}/gauges/{lid}")
                    sf = http.fetch(c, f"{base}/gauges/{lid}/stageflow")
                    run.items_fetched += 2
                    with conn.transaction():
                        gref = archive.store(conn, s.archive_dir, SOURCE, f"gauge_{lid}", g)
                        sref = archive.store(conn, s.archive_dir, SOURCE, f"stageflow_{lid}", sf)
                    gj = json.loads(g.content)
                    usgs_id = gj.get("usgsId")
                    issued_at, rows = parse_forecast(json.loads(sf.content))
                    with conn.transaction():
                        if usgs_id:
                            attach_to_station(conn, usgs_id, lid, gj, gref.raw_object_id)
                        new = store_forecast(conn, lid, rows, sf.fetched_at, sref.raw_object_id)
                    run.rows.inserted += new
                    issued[lid] = {"issued_at": issued_at.isoformat() if issued_at else None,
                                   "points": len(rows), "new_rows": new, "usgs_id": usgs_id}
                except Exception as e:  # noqa: BLE001 - one gauge never stops the others
                    run.fail(lid, e)
            run.details = {"gauges": issued}
            return run.run_id
