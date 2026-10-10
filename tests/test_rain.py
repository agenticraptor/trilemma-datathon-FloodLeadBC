"""Rainfall parsers: time conventions (UTC, hour ending), units and edge cases. The payloads below are trimmed copies
of the real formats (field names and value encodings as returned by each API), with values chosen for the checks."""

from datetime import UTC, datetime

import pytest

from floodlead.history import rain

NCEI = (
    '"STATION","DATE","SOURCE","REPORT_TYPE","AA1","TMP"\n'
    '"72797624217","2021-11-14T10:53:00","7","FM-15","01,0008,9,5","+0133,5"\n'
    '"72797624217","2021-11-14T11:10:00","7","FM-16","01,0002,9,5","+0135,5"\n'
    '"72797624217","2021-11-14T11:53:00","7","FM-15","01,9999,9,5","+9999,9"\n'
    '"72797624217","2021-11-14T12:53:00","7","FM-15","","+0139,5"\n'
)


def test_ncei_routine_hourly_reports_only_assigned_to_the_hour_ending() -> None:
    rows = list(rain.ncei(NCEI, 1))
    assert [(r[2], r[3], r[4]) for r in rows] == [
        (datetime(2021, 11, 14, 11, tzinfo=UTC), 0.8, 13.3),
        (datetime(2021, 11, 14, 12, tzinfo=UTC), None, None),  # 9999 / +9999 = missing
        (datetime(2021, 11, 14, 13, tzinfo=UTC), None, 13.9),  # no AA1 group
    ]


def test_snotel_accumulation_to_hourly_amounts_in_utc() -> None:
    doc = [{"stationTriplet": "909:WA:SNTL", "data": [
        {"stationElement": {"elementCode": "PREC"}, "values": [
            {"date": "2021-11-14 00:00", "value": 30.0}, {"date": "2021-11-14 01:00", "value": 30.1},
            {"date": "2021-11-14 02:00", "value": 30.05}, {"date": "2021-11-14 04:00", "value": 30.3}]},
        {"stationElement": {"elementCode": "TOBS"}, "values": [{"date": "2021-11-14 01:00", "value": 41.0}]}]}]
    rows = {r[2]: r for r in rain.snotel(doc, 1)}
    t1 = datetime(2021, 11, 14, 9, tzinfo=UTC)  # 01:00 PST = 09:00 UTC
    assert rows[t1][3] == pytest.approx(0.1 * 25.4) and rows[t1][4] == pytest.approx(5.0)
    assert rows[datetime(2021, 11, 14, 10, tzinfo=UTC)][3:8:4] == (0.0, "neg_step")
    assert rows[datetime(2021, 11, 14, 12, tzinfo=UTC)][3] is None  # gap before it: no hourly amount
    assert rows[datetime(2021, 11, 14, 8, tzinfo=UTC)][3] is None  # first value: no previous accumulation


def test_eccc_climate_and_openmeteo_rows() -> None:
    doc = {"features": [{"properties": {"CLIMATE_IDENTIFIER": "1100031", "UTC_DATE": "2021-11-14T22:00:00",
                                        "PRECIP_AMOUNT": 4.2, "PRECIP_AMOUNT_FLAG": None, "TEMP": 9.1,
                                        "TEMP_FLAG": "E"}}]}
    assert list(rain.eccc_climate(doc, 7)) == [("eccc-climate", "1100031", datetime(2021, 11, 14, 22, tzinfo=UTC),
                                                4.2, 9.1, None, None, "E", 7)]
    om = {"hourly": {"time": ["2024-02-01T00:00", "2024-02-01T01:00"], "precipitation": [0.5, None],
                     "precipitation_previous_day1": [0.4, None]}}
    rows = list(rain.openmeteo(om, "prevruns", "nooksack-nf", 3))
    assert len(rows) == 1 and rows[0][:3] == ("prevruns", "nooksack-nf", datetime(2024, 2, 1, tzinfo=UTC))
    vals = dict(zip(rain.OM_ORDER, rows[0][3:-1], strict=True))
    assert vals["precip_mm"] == 0.5 and vals["precip_prev_day1_mm"] == 0.4 and vals["temp_c"] is None


def test_load_two_overlapping_payloads(conn, test_dsn: str, tmp_path, monkeypatch) -> None:  # noqa: ANN001
    """Two yearly payloads share one boundary hour: the load keeps one row for it and does not fail on the second
    payload (the first version reused a temp table that only dropped at commit)."""
    import json

    from floodlead import archive, db, http
    from floodlead.config import get_settings
    from floodlead.history import download

    monkeypatch.setenv("ARCHIVE_DIR", str(tmp_path))
    get_settings.cache_clear()

    def page(times: list[str]) -> bytes:
        return json.dumps({"features": [{"properties": {"CLIMATE_IDENTIFIER": "1106178", "UTC_DATE": t,
                                                        "PRECIP_AMOUNT": 1.0, "TEMP": 5.0}} for t in times]}).encode()

    for key, times in (("1106178/2021/0", ["2021-12-31T23:00:00", "2022-01-01T00:00:00"]),
                       ("1106178/2022/0", ["2022-01-01T00:00:00", "2022-01-01T01:00:00"])):
        f = http.Fetched(url=f"https://example.test/{key}", status=200, content=page(times), last_modified=None,
                         fetched_at=datetime(2026, 10, 9, tzinfo=UTC), elapsed_s=0.1)
        ref = archive.store(conn, tmp_path, "eccc-climate", key.replace("/", "_"), f)
        download.record(conn, "eccc-climate", download.Task(key, f.url), f.url, "ok", 200, len(f.content),
                        ref.raw_object_id, f.fetched_at, 0.1, None)
    pool = db.pool(test_dsn, max_size=1)
    try:
        out = rain.load(pool)
    finally:
        pool.close()
        get_settings.cache_clear()
    assert out == {"eccc-climate": 3}
    assert conn.execute("SELECT count(*) FROM rain_hourly WHERE site = '1106178'").fetchone()[0] == 3
