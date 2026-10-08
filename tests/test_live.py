"""Checks against the real sources. Excluded by default; run with `pytest -m live`."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from floodlead import http
from floodlead.sources import eccc, nwps, usgs

pytestmark = pytest.mark.live


def test_eccc_listing_has_hundreds_of_bc_files_and_csv_parses() -> None:
    with http.client() as c:
        f = http.fetch(c, eccc.listing_url("hourly"))
        files = eccc.parse_listing(f.content.decode())
        assert len(files) >= 400
        g = http.fetch(c, eccc.listing_url("hourly") + "BC_08MH001_hourly_hydrometric.csv")
    rows = eccc.parse_csv(g.content, g.last_modified)
    assert rows and datetime.now(UTC) - max(r.ts for r in rows) < timedelta(hours=6)


def test_usgs_ogc_v1_continuous_returns_recent_stage() -> None:
    now = datetime.now(UTC)
    with http.client() as c:
        try:
            f = http.fetch(c, f"{usgs._base()}/collections/continuous/items", params={
                "f": "json", "monitoring_location_id": "USGS-12210700", "parameter_code": "00065",
                "datetime": f"{now - timedelta(hours=6):%Y-%m-%dT%H:%M:%SZ}/{now:%Y-%m-%dT%H:%M:%SZ}",
                "limit": "100", "skipGeometry": "true"}, headers=usgs._headers(), attempts=1)
        except http.RateLimited as e:
            pytest.skip(f"USGS OGC API rate-limited this IP (keyless limit): {e}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 429:
                raise
            pytest.skip("USGS OGC API rate-limited this IP (HTTP 429, short Retry-After)")
    rows, _ = usgs.parse_items(f.content, None)
    assert rows and rows[0].raw_unit == "ft"


def test_usgs_nwis_iv_fallback_returns_recent_stage_and_flow() -> None:
    now = datetime.now(UTC)
    with http.client() as c:
        f = http.fetch(c, usgs.NWIS_IV_URL, params={
            "format": "json", "sites": "12210700", "parameterCd": "00065,00060", "siteStatus": "all",
            "startDT": f"{now - timedelta(hours=6):%Y-%m-%dT%H:%MZ}", "endDT": f"{now:%Y-%m-%dT%H:%MZ}"})
    rows, _ = usgs.parse_nwis_iv(f.content)
    assert {r.param for r in rows} == {"level", "flow"}
    assert now - max(r.ts for r in rows) < timedelta(hours=3)


def test_nwps_nrkw1_has_official_forecast() -> None:
    with http.client() as c:
        f = http.fetch(c, "https://api.water.noaa.gov/nwps/v1/gauges/NRKW1/stageflow")
    issued, rows = nwps.parse_forecast(json.loads(f.content))
    assert issued is not None and len(rows) >= 10
