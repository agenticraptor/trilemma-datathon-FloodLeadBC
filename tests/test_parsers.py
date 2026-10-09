"""Parser tests on real, trimmed fixtures: ECCC CSV and listing, USGS OGC JSON, NWPS JSON."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from floodlead.sources import eccc, nwps, usgs
from tests.conftest import fixture_bytes

PUB = datetime(2026, 10, 7, 21, 1, 28, tzinfo=UTC)  # Last-Modified of the 08MH001 fixture


def test_eccc_hourly_csv_parses_offset_to_utc_and_keeps_raw() -> None:
    rows = eccc.parse_csv(fixture_bytes("eccc_hourly_08MH001.csv"), PUB)
    assert len(rows) == 8 * 2  # 8 data rows x (level, flow)
    first = rows[0]
    assert first.station_id == "eccc:08MH001"
    # 2026-10-05T00:00:00-08:00 is 08:00 UTC: the fixed -08:00 offset is applied, not local PDT.
    assert first.ts == datetime(2026, 10, 5, 8, 0, tzinfo=UTC)
    assert first.ts.utcoffset().total_seconds() == 0
    assert (first.param, first.raw_value, first.raw_unit, first.value) == ("level", 1.618, "m", 1.618)
    assert first.quality == {"grade": None, "symbol": None, "qaqc": "1"}
    flow = rows[1]
    assert (flow.param, flow.raw_value, flow.raw_unit) == ("flow", 21.0, "m3/s")
    last = rows[-1]
    assert last.ts == datetime(2026, 10, 7, 20, 20, tzinfo=UTC)  # 12:20-08:00
    assert all(r.published_at == PUB for r in rows)
    assert not any(r.is_sentinel for r in rows)


def test_eccc_sentinel_row_is_flagged_and_value_nulled() -> None:
    rows = eccc.parse_csv(fixture_bytes("eccc_daily_08NJ026_sentinel.csv"), PUB)
    sent = [r for r in rows if r.is_sentinel]
    assert len(sent) == 1
    s = sent[0]
    assert (s.station_id, s.param, s.raw_value, s.value) == ("eccc:08NJ026", "level", 99999.0, None)
    assert s.ts == datetime(2026, 10, 6, 23, 50, tzinfo=UTC)
    # The sentinel row has no discharge, so no flow row is produced for that timestamp.
    assert not [r for r in rows if r.ts == s.ts and r.param == "flow"]


def test_eccc_rejects_unexpected_header() -> None:
    with pytest.raises(ValueError):
        eccc.parse_csv(b"foo,bar\n1,2\n", PUB)


def test_eccc_listing() -> None:
    files = eccc.parse_listing(fixture_bytes("eccc_listing_hourly.html").decode())
    assert len(files) == 6
    name, ts = next(iter(sorted(files.items())))
    assert name.startswith("BC_") and name.endswith("_hourly_hydrometric.csv")
    assert ts.tzinfo is UTC and ts.year == 2026


def test_usgs_items_parse_units_and_primary_series() -> None:
    meta = usgs.parse_series_metadata(json.loads(fixture_bytes("usgs_time_series_metadata.json")))
    assert meta[("12210700", "00065")].time_series_id == "1fd347f7fda04be0b9fe0740438bfa43"
    assert meta[("12210700", "00065")].begin == datetime(2007, 10, 1, 8, 0, tzinfo=UTC)
    assert meta[("12210700", "00060")].begin == datetime(2004, 10, 15, 7, 0, tzinfo=UTC)
    allowed = usgs._allowed(meta, "12210700")
    rows, stats = usgs.parse_items(fixture_bytes("usgs_continuous_12210700.json"), allowed)
    assert stats["features"] == 6 and len(rows) == 6
    lvl = [r for r in rows if r.param == "level"][0]
    assert lvl.station_id == "usgs:12210700" and lvl.raw_unit == "ft" and lvl.raw_value == 138.77
    assert lvl.value == pytest.approx(138.77 * 0.3048)
    assert lvl.ts == datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    assert lvl.quality["approval_status"] == "Approved"
    assert lvl.published_at == datetime(2026, 9, 10, 16, 41, 12, 684353, tzinfo=UTC)
    flo = [r for r in rows if r.param == "flow"][0]
    assert flo.raw_unit == "ft3/s" and flo.value == pytest.approx(flo.raw_value * 0.028316846592)
    # A series that is not primary is skipped.
    rows2, stats2 = usgs.parse_items(fixture_bytes("usgs_continuous_12210700.json"), {"someothersensor"})
    assert rows2 == [] and stats2["skipped_series"] == 6
    assert usgs.next_link(fixture_bytes("usgs_continuous_12210700.json")).endswith("cursor=EXAMPLE&f=json")


def test_usgs_live_sites_drop_discontinued() -> None:
    meta = usgs.parse_series_metadata(json.loads(fixture_bytes("usgs_time_series_metadata.json")))
    # 12210500 (Deming) instantaneous data ended 2005-09-30: not live.
    assert usgs.live_sites(meta, datetime(2026, 10, 7, 21, 0, tzinfo=UTC)) == ["12210700"]


def test_nwps_thresholds_drop_undefined_and_convert() -> None:
    g = json.loads(fixture_bytes("nwps_gauge_NRKW1.json"))
    thr = nwps.thresholds_from_gauge(g, 7)
    cats = thr["categories"]
    assert set(cats) == {"action", "minor", "moderate", "major"}
    assert cats["action"] == {"stage_ft": 144.8, "stage_m": round(144.8 * 0.3048, 4)}
    assert "flow_cfs" not in cats["major"]  # -9999 means not defined
    assert thr["lid"] == "NRKW1" and thr["raw_object_id"] == 7


def test_nwps_forecast_parse_unmodified() -> None:
    issued, rows = nwps.parse_forecast(json.loads(fixture_bytes("nwps_stageflow_NRKW1.json")))
    assert issued == datetime(2026, 10, 7, 15, 36, tzinfo=UTC)
    assert len(rows) == 4
    assert rows[0]["valid_at"] == datetime(2026, 10, 7, 18, 0, tzinfo=UTC)
    assert (rows[0]["stage_ft"], rows[0]["flow_kcfs"]) == (138.05, 0.734)  # exactly as published


def test_nwps_forecast_only_endpoint_parses_the_whole_issuance() -> None:
    # gauges/{lid}/stageflow/forecast returns the forecast object itself, including points beyond the
    # combined endpoint's request time + 7 days cut (D-02.18).
    issued, rows = nwps.parse_forecast(json.loads(fixture_bytes("nwps_stageflow_forecast_NRKW1.json")))
    assert issued == datetime(2026, 10, 8, 15, 12, tzinfo=UTC)
    assert len(rows) == 6
    assert rows[-1]["valid_at"] == datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
    assert (rows[-1]["stage_ft"], rows[-1]["flow_kcfs"]) == (138.31, 1.05)
    assert rows[-1]["generated_at"] == datetime(2026, 10, 8, 15, 27, 41, tzinfo=UTC)


def test_nwps_missing_forecast_gives_no_rows() -> None:
    issued, rows = nwps.parse_forecast({"forecast": {"issuedTime": "0001-01-01T00:00:00Z", "data": []}})
    assert issued is None and rows == []
    issued, rows = nwps.parse_forecast({"issuedTime": "0001-01-01T00:00:00Z", "data": []})
    assert issued is None and rows == []


def test_nwis_iv_parse_offsets_qualifiers_and_peak() -> None:
    rows, stats = usgs.parse_nwis_iv(fixture_bytes("nwis_iv_12211200_2021-11.json"))
    assert stats["series"] == 2 and len(rows) == 8
    flows = [r for r in rows if r.param == "flow"]
    peak = max(flows, key=lambda r: r.raw_value)
    # 2021-11-15T13:40:00.000-08:00 (PST) is 21:40 UTC; the verified Everson peak.
    assert peak.ts == datetime(2021, 11, 15, 21, 40, tzinfo=UTC)
    assert (peak.station_id, peak.raw_value, peak.raw_unit) == ("usgs:12211200", 52300.0, "ft3/s")
    assert not peak.is_sentinel and peak.value == pytest.approx(52300 * 0.028316846592)
    assert peak.quality == {"approval_status": "Approved", "qualifier": None, "time_series_id": None,
                            "source_api": "nwis-iv"}
    # PDT values (-07:00) before the DST change are converted correctly too.
    assert flows[0].ts == datetime(2021, 11, 1, 0, 0, tzinfo=UTC)
    lvl = [r for r in rows if r.param == "level"][0]
    assert lvl.raw_unit == "ft" and lvl.raw_value == 75.79
