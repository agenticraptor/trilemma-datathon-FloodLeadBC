"""API contract tests against a disposable database loaded from real fixtures."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from fastapi.testclient import TestClient

from floodlead import api, store
from floodlead.config import ATTRIBUTION, get_settings
from floodlead.sources import eccc, nwps
from tests.conftest import fixture_bytes


@pytest.fixture
def client(conn: psycopg.Connection, test_dsn: str, tmp_path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", test_dsn)
    monkeypatch.setenv("ARCHIVE_DIR", str(tmp_path))
    get_settings.cache_clear()
    api._cache.clear()
    now = datetime.now(UTC)
    # Shift the real fixture rows so they are recent (the API's latest/health windows are relative).
    rows = eccc.parse_csv(fixture_bytes("eccc_hourly_08MH001.csv"), now)
    shift = now - timedelta(minutes=50) - max(r.ts for r in rows)
    rows = [store.Obs(r.station_id, r.ts + shift, r.param, r.value, r.raw_value, r.raw_unit, r.quality,
                      r.is_sentinel, r.published_at) for r in rows]
    sent = eccc.parse_csv(fixture_bytes("eccc_daily_08NJ026_sentinel.csv"), now)
    shift2 = now - timedelta(minutes=50) - max(r.ts for r in sent)
    sent = [store.Obs(r.station_id, r.ts + shift2, r.param, r.value, r.raw_value, r.raw_unit, r.quality,
                      r.is_sentinel, r.published_at) for r in sent]
    store.ensure_stations(conn, [
        {"station_id": "eccc:08MH001", "source": "eccc", "native_id": "08MH001", "params": ["flow", "level"]},
        {"station_id": "eccc:08NJ026", "source": "eccc", "native_id": "08NJ026", "params": ["flow", "level"]},
    ])
    with conn.transaction():
        store.upsert_observations(conn, rows + sent, None)
    store.upsert_station_meta(conn, {"station_id": "usgs:12210700", "source": "usgs", "native_id": "12210700",
                                     "name": "NOOKSACK RIVER AT NORTH CEDARVILLE, WA", "region": "WA"})
    nwps.attach_to_station(conn, "12210700", "NRKW1", json.loads(fixture_bytes("nwps_gauge_NRKW1.json")), None)
    _, fc = nwps.parse_forecast(json.loads(fixture_bytes("nwps_stageflow_NRKW1.json")))
    with conn.transaction():
        nwps.store_forecast(conn, "NRKW1", fc, now, None)
    conn.execute("INSERT INTO ingest_runs (source, job, status, finished_at) VALUES"
                 " ('eccc', 'live', 'ok', now()), ('usgs', 'live', 'ok', now()), ('nwps', 'live', 'ok', now())")
    with TestClient(api.app) as c:
        yield c
    get_settings.cache_clear()


def test_every_response_has_attribution(client: TestClient) -> None:
    for path in ["/v1/health", "/v1/stations", "/v1/stations/eccc:08MH001",
                 "/v1/stations/eccc:08MH001/observations", "/v1/official-forecasts/NRKW1",
                 "/v1/stations/nope", "/v1/stations/eccc:08MH001/observations?param=bogus"]:
        r = client.get(path)
        assert r.json()["attribution"] == ATTRIBUTION, path


def test_health_shape(client: TestClient) -> None:
    b = client.get("/v1/health").json()
    assert set(b["sources"]) == {"eccc", "usgs", "nwps"}
    e = b["sources"]["eccc"]
    for k in ("status", "last_successful_run", "newest_observation", "lag_min", "stations_reporting_3h"):
        assert k in e
    assert e["stations_reporting_3h"] == 2
    assert e["status"] == "green"
    assert b["sources"]["usgs"]["status"] == "red"  # no USGS observations in this DB
    assert b["status"] == "red"
    assert b["disk"]["status"] in {"green", "amber", "red"} and "used_pct" in b["disk"]
    assert {"files", "bytes_on_disk", "files_last_hour"} <= set(b["archive"])


def test_stations_and_filters(client: TestClient) -> None:
    b = client.get("/v1/stations").json()
    assert b["total"] == 3
    assert client.get("/v1/stations?source=usgs").json()["total"] == 1
    assert client.get("/v1/stations?q=cedarville").json()["stations"][0]["station_id"] == "usgs:12210700"
    one = client.get("/v1/stations/usgs:12210700").json()
    assert one["official_thresholds"]["categories"]["action"]["stage_ft"] == 144.8
    assert client.get("/v1/stations/nope").status_code == 404


def test_observations_window_units_and_sentinels(client: TestClient) -> None:
    b = client.get("/v1/stations/eccc:08MH001/observations?param=level&since="
                   + (datetime.now(UTC) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")).json()
    assert b["count"] == 8 and {o["unit"] for o in b["observations"]} == {"m"}
    assert all(o["raw_unit"] == "m" for o in b["observations"])
    since = (datetime.now(UTC) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    default = client.get(f"/v1/stations/eccc:08NJ026/observations?param=level&since={since}").json()
    withs = client.get(f"/v1/stations/eccc:08NJ026/observations?param=level&since={since}"
                       "&include_sentinels=true").json()
    assert withs["count"] == default["count"] + 1
    assert not any(o["is_sentinel"] for o in default["observations"])
    r = client.get("/v1/stations/eccc:08MH001/observations?since=2026-09-01T00:00:00Z&until=2026-09-10T00:00:00Z")
    assert r.status_code == 400
    assert client.get("/v1/stations/eccc:08MH001/observations?since=notadate").status_code == 400


def test_official_forecasts(client: TestClient) -> None:
    b = client.get("/v1/official-forecasts/nrkw1").json()
    assert b["lid"] == "NRKW1"
    assert b["issuances"][0]["issued_at"].startswith("2026-10-07T15:36:00")
    assert b["issuances"][0]["points"][0] == {"valid_at": "2026-10-07T18:00:00Z", "stage_ft": 138.05,
                                              "flow_kcfs": 0.734, "generated_at": "2026-10-07T15:56:31Z"}
    assert b["station"]["official_thresholds"]["categories"]["major"]["stage_ft"] == 150
    assert client.get("/v1/official-forecasts/XXXX1").status_code == 404


def test_head_is_allowed(client: TestClient) -> None:
    r = client.head("/v1/health")
    assert r.status_code == 200 and r.content == b""


def test_cors_allows_any_origin_for_get(client: TestClient) -> None:
    r = client.get("/v1/stations", headers={"Origin": "https://example.org"})
    assert r.headers["access-control-allow-origin"] == "*"


def test_rate_limiter_blocks_after_burst() -> None:
    rl = api.RateLimiter(3)
    assert [rl.allow("1.2.3.4") for _ in range(4)] == [True, True, True, False]
    assert rl.allow("5.6.7.8")


def _append_forecast(conn: psycopg.Connection) -> int:
    from floodlead import ledger

    now = datetime.now(UTC)
    base = now.replace(minute=0, second=0, microsecond=0)
    q = {k: 42.0 for k in ("0.05", "0.1", "0.25", "0.5", "0.75", "0.9", "0.95")}
    data = {"station_id": "usgs:12210700", "model": "persistence-v1", "base_time": ledger.ts(base),
            "data_as_of": ledger.ts(base - timedelta(minutes=45)), "stale_inputs": False, "input_age_min": 50.0,
            "level_at_data_as_of_m": 42.0, "units": "m", "input_hash": "0" * 64, "inputs_n": 13,
            "error_library": {"hash": "1" * 64, "paths": 100, "definition": "test"},
            "thresholds": [{"key": "rise:+0.25", "kind": "rise", "level_m": 42.25, "label": "+0.25 m"}],
            "horizons": [{"h": 6, "valid_at": ledger.ts(base + timedelta(hours=6)), "q": q, "qmax": q,
                          "p_exceed": {"rise:+0.25": 0.0}}]}
    with conn.transaction():
        written = ledger.append(conn, [ledger.Pending("forecast", data, now, station_id="usgs:12210700",
                                                      model="persistence-v1", base_time=base)])
    return written[-1].seq


@pytest.fixture
def lclient(client: TestClient, conn: psycopg.Connection) -> Iterator[TestClient]:
    yield client
    conn.execute("SET session_replication_role = replica")
    conn.execute("TRUNCATE forecast_scores, forecast_scores_naive, score_summaries, scorer_runs, ledger_anchors,"
                  " ledger_entries")
    conn.execute("SET session_replication_role = DEFAULT")


def test_ledger_endpoints_and_forecast(lclient: TestClient, conn: psycopg.Connection) -> None:
    assert lclient.get("/v1/ledger/head").status_code == 404  # empty ledger
    seq = _append_forecast(conn)
    head = lclient.get("/v1/ledger/head").json()
    assert head["seq"] == seq == 2 and head["anchor"]["status"] == "pending"
    page = lclient.get("/v1/ledger?after_seq=0&limit=1").json()
    assert page["count"] == 1 and page["next_after_seq"] == 1 and page["entries"][0]["entry_type"] == "genesis"
    e = lclient.get(f"/v1/ledger/{seq}").json()
    from floodlead import ledger

    assert ledger.entry_hash(e["prev_hash"], e["canonical"]) == e["entry_hash"]
    assert lclient.get("/v1/ledger?limit=5000").status_code == 422
    f = lclient.get("/v1/stations/usgs:12210700/forecast").json()
    m = f["models"][0]
    assert m["model"] == "persistence-v1" and m["seq"] == seq and m["horizons"][0]["h"] == 6
    assert f["label"].startswith("FloodLead baseline") and f["official"]["label"].endswith("(unmodified)")
    assert lclient.get("/v1/stations/eccc:08MH001/forecast").status_code == 404
    assert lclient.get("/v1/stations/nope/forecast").status_code == 404


def test_scores_endpoints_before_and_after_a_run(lclient: TestClient, conn: psycopg.Connection) -> None:
    assert lclient.get("/v1/scores/summary").status_code == 404
    rid = conn.execute("INSERT INTO scorer_runs (status) VALUES ('ok') RETURNING scorer_run_id").fetchone()[0]
    body = {"scorer_run_id": rid, "generated_at": "2026-10-09T00:40:00Z", "totals": {"scored": 0},
            "groups": [{"model": "trend3h-v1", "h": 6, "source": "usgs"}, {"model": "persistence-v1", "h": 1,
                                                                            "source": "eccc"}],
            "official": []}
    from psycopg.types.json import Jsonb

    conn.execute("INSERT INTO score_summaries VALUES (%s, now(), %s)", (rid, Jsonb(body)))
    s = lclient.get("/v1/scores/summary?source=usgs").json()
    assert s["scorer_run_id"] == rid and [g["h"] for g in s["groups"]] == [6]
    o = lclient.get("/v1/scores/official?lid=nrkw1").json()
    assert o["pairs"] == [] and "No matched pair" in o["note"]


def test_health_has_ledger_job_blocks(lclient: TestClient) -> None:
    b = lclient.get("/v1/health").json()
    assert {"issuer", "scorer", "anchor"} <= set(b)
    assert b["issuer"]["status"] == "red" and b["anchor"]["status"] == "amber"


def test_replay_endpoint_shape_on_empty_history(lclient: TestClient) -> None:
    r = lclient.get("/v1/replay/overflow").json()
    assert r["events"] == [] and r["summary"]["events_total"] == 0 and len(r["caveats"]) >= 3
    assert r["gauges"]["cedarville"]["stages_ft"]["minor"] == 146.5
    assert lclient.get("/v1/replay/overflow/2021-11-14/series").status_code == 404


def test_fraser_valley_contract(client: TestClient) -> None:
    b = client.get("/v1/gauges/fraser-valley").json()
    assert "not an official flood level" in b["label"] and b["attribution"]
    ids = [g["station_id"] for g in b["gauges"]]
    assert {"eccc:08MH029", "eccc:08MH001", "eccc:08MH103", "eccc:08MF005", "eccc:08MH024", "eccc:08MH155",
            "eccc:08MF062"} <= set(ids)
    g = {x["station_id"]: x for x in b["gauges"]}
    assert g["eccc:08MH024"]["tidal"] is True and "tide" in g["eccc:08MH024"]["note"]
    for x in b["gauges"]:
        assert set(x) >= {"short_name", "latest", "typical_peak", "typical_peak_note", "tidal", "note"}
        assert (x["typical_peak"] is None) != (x["typical_peak_note"] is None)


def test_track_record_contract(client: TestClient, conn: psycopg.Connection) -> None:
    assert client.get("/v1/track-record").status_code == 404  # no scorer run yet
    body = {"scorer_run_id": 1, "generated_at": "2026-10-09T20:40:00Z",
            "window": {"first_base_time": "2026-10-08T20:00:00Z", "last_valid_at": "2026-10-09T17:00:00Z"},
            "rules": {"crps": "fair"}, "official": [{"lid": "NRKW1", "model": "persistence-naive", "h": 6, "n": 3}],
            "groups": [{"model": "persistence-v1", "h": 1, "source": "eccc", "n": 500, "stations": 400, "days": 2,
                        "skill_vs": {"persistence-naive": {"n_pairs": 500, "crpss": 0.2, "mae_skill": -0.02,
                                                           "paired_crps": {"persistence-v1": 0.02,
                                                                           "persistence-naive": 0.025},
                                                           "paired_mae": {"persistence-v1": 0.0255,
                                                                          "persistence-naive": 0.025}}}},
                       {"model": "persistence-naive", "h": 1, "source": "eccc", "n": 500, "stations": 400,
                        "days": 2, "skill_vs": {}}]}
    conn.execute("INSERT INTO scorer_runs (scorer_run_id) VALUES (1)")
    conn.execute("INSERT INTO score_summaries (scorer_run_id, generated_at, body) VALUES (1, now(), %s)",
                 (json.dumps(body),))
    try:
        from floodlead import api

        api._cache.pop("track-record", None)
        b = client.get("/v1/track-record").json()
        assert b["scorer_run_id"] == 1 and b["noaa_matched_pairs"] == 3
        assert b["skill_vs_persistence"] == [{"source": "eccc", "model": "persistence-v1", "h": 1, "n_pairs": 500,
                                              "stations": 400, "days": 2, "crps_model_m": 0.02,
                                              "crps_naive_m": 0.025, "crpss": 0.2, "mae_model_m": 0.0255,
                                              "mae_naive_m": 0.025, "mae_skill": -0.02}]
        st = " ".join(b["statements"])
        assert "Neither baseline has a lower median error" in st and "spread" in st and "quiet rivers" in st
        assert set(b["verify"]) == {"api", "github", "spec_url"} and "forecasts" in b and "ledger" in b
    finally:
        conn.execute("DELETE FROM score_summaries")
        conn.execute("DELETE FROM scorer_runs")


def test_official_scorecard_contract(client: TestClient, conn: psycopg.Connection) -> None:
    assert client.get("/v1/official-scorecard").status_code == 404
    body = {"method": "m", "period": ["2006-11-06T12:22:00Z", "2026-03-20T23:16:00Z"],
            "points": {"NRKW1": "usgs:12210700"},
            "summary": {"NRKW1": {"n_events": 1, "lead_bins": []}, "NKSW1": {"n_events": 0, "lead_bins": []}},
            "events": [{"point": "NRKW1", "etn": 78}, {"point": "NKSW1", "etn": 5}]}
    conn.execute("INSERT INTO official_scorecards (generated_at, body) VALUES (now(), %s)", (json.dumps(body),))
    try:
        b = client.get("/v1/official-scorecard").json()
        assert b["summary"]["NRKW1"]["n_events"] == 1 and len(b["events"]) == 2 and b["attribution"]
        one = client.get("/v1/official-scorecard?point=NRKW1").json()
        assert [e["etn"] for e in one["events"]] == [78] and list(one["summary"]) == ["NRKW1"]
        assert client.get("/v1/official-scorecard?point=XXXX1").status_code == 422
    finally:
        conn.execute("DELETE FROM official_scorecards")
