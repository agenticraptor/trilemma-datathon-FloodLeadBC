"""Scoring rules, plus an end-to-end issue -> settle -> score run on synthetic data in a disposable database."""

from __future__ import annotations

import math
import random
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from statistics import NormalDist, fmean

import psycopg
import pytest

from floodlead import crps, db, issuer, ledger, scorer, store

N = NormalDist()
QN = {k: N.inv_cdf(t) for t, k in zip(scorer.TAUS, scorer.KEYS, strict=True)}


def test_fair_crps_and_quantile_score_equal_absolute_error_for_a_point_forecast() -> None:
    q = {k: 2.0 for k in scorer.KEYS}
    for y in (2.0, 2.3, 1.1, -5.0):
        assert crps.fair(q, y) == pytest.approx(abs(y - 2.0))
        assert crps.quantile_score(q, y) == pytest.approx(abs(y - 2.0))


def test_fair_crps_matches_normal_crps_where_the_quantile_score_did_not() -> None:
    """The fair CRPS of the 7 stored quantiles of N(0,1) is within 1 % of the analytic CRPS in expectation; the
    quantile score (kept as crps_qs) is 15-25 % low (measured: -19.4 %)."""
    def analytic(z: float) -> float:
        return z * (2 * N.cdf(z) - 1) + 2 * N.pdf(z) - 1 / math.sqrt(math.pi)

    r = random.Random(3)
    ys = [r.gauss(0, 1) for _ in range(20000)]
    ex = fmean(analytic(y) for y in ys)
    assert 0.99 <= fmean(crps.fair(QN, y) for y in ys) / ex <= 1.01
    assert 0.75 <= fmean(crps.quantile_score(QN, y) for y in ys) / ex <= 0.85


def test_pit_bin() -> None:
    assert scorer.pit_bin(QN, -3) == 0 and scorer.pit_bin(QN, 0.0) == 4 and scorer.pit_bin(QN, 3) == 7


def _obs(times_values: list[tuple[datetime, float]]) -> list[tuple[datetime, float, datetime, int]]:
    return [(t, v, t, 0) for t, v in times_values]


def test_truth_matching_within_10_min() -> None:
    t = datetime(2026, 10, 9, 0, 0, tzinfo=UTC)
    obs = _obs([(t - timedelta(minutes=15), 1.0), (t + timedelta(minutes=7), 2.0), (t + timedelta(minutes=12), 3.0)])
    assert scorer.truth_at(obs, t)[1] == 2.0  # nearest within +/-10 min
    assert scorer.truth_at(_obs([(t, 5.0), (t + timedelta(minutes=5), 6.0)]), t)[1] == 5.0  # exact wins
    assert scorer.truth_at(_obs([(t + timedelta(minutes=11), 1.0)]), t) is None  # outside tolerance: no_truth


def test_window_coverage_rule() -> None:
    t0 = datetime(2026, 10, 9, 0, 0, tzinfo=UTC)
    step = timedelta(minutes=15)
    full = _obs([(t0 + step * i, 1.0 + i / 100) for i in range(1, 25)])  # 24 of 24 points in (t0, t0+6h]
    mx, cov = scorer.window(full, t0, t0 + timedelta(hours=6), step)
    assert cov == 1.0 and mx == pytest.approx(1.24)
    sparse = full[::2]
    _, cov = scorer.window(sparse, t0, t0 + timedelta(hours=6), step)
    assert cov == 0.5 < scorer.MIN_COVERAGE


@pytest.fixture
def fresh(test_dsn: str) -> Iterator[psycopg.Connection]:
    with db.connect(test_dsn, autocommit=True) as c:
        c.execute("SET session_replication_role = replica")
        c.execute("TRUNCATE forecast_scores, forecast_scores_naive, score_summaries, scorer_runs, ledger_anchors,"
                  " ledger_entries,"
                  " observations, observation_revisions, official_forecasts, history_downloads,"
                  " eccc_annual_peaks, eccc_daily, typical_peaks, nws_vtec, nws_products, rain_hourly,"
                  " openmeteo_hourly,"
                  " raw_objects,"
                  " stations")
        c.execute("SET session_replication_role = DEFAULT")
        yield c


def test_issue_then_score_end_to_end(fresh: psycopg.Connection, test_dsn: str) -> None:
    sid = "usgs:9999999"
    store.upsert_station_meta(fresh, {"station_id": sid, "source": "usgs", "native_id": "9999999", "name": "Test",
                                      "params": ["level"],
                                      "official_thresholds": {"lid": "TEST1", "categories": {
                                          "action": {"stage_ft": 10.0, "stage_m": 3.048}}}})
    created = datetime(2026, 10, 8, 20, 15, tzinfo=UTC)
    step = timedelta(minutes=15)
    start = created - timedelta(days=35)
    r = random.Random(5)
    level = 2.0
    rows = []
    t = start
    end = created + timedelta(hours=55)
    while t <= end:
        level += r.gauss(0, 0.005)
        rows.append((t, level))
        t += step
    def obs(seen_at: datetime, sel: list[tuple[datetime, float]]) -> list[store.Obs]:
        return [store.Obs(sid, ts, "level", v, v / 0.3048, "ft", {}, False, None) for ts, v in sel]
    past = [(ts, v) for ts, v in rows if ts <= created - timedelta(minutes=45)]
    future = [(ts, v) for ts, v in rows if ts > created - timedelta(minutes=45)]
    with fresh.transaction():
        store.upsert_observations(fresh, obs(created, past), None, now=created - timedelta(minutes=10))
    with fresh.transaction():  # rows that arrive after created_at must not be used by the forecast
        store.upsert_observations(fresh, obs(created, future), None, now=created + timedelta(minutes=30))
    pool = db.pool(test_dsn, max_size=2)
    try:
        res = issuer.run(pool, now=created)
        assert res["status"] == "issued" and res["forecasts"] == {"persistence-v1": 1, "trend3h-v1": 1}
        f = [e for e in fresh.execute("SELECT canonical FROM ledger_entries WHERE entry_type = 'forecast'")]
        import json
        d = json.loads(f[0][0])["data"]
        assert datetime.fromisoformat(d["data_as_of"].replace("Z", "+00:00")) <= created - timedelta(minutes=45)
        assert [h["h"] for h in d["horizons"]] == [1, 3, 6, 12, 18, 24, 36, 48]
        assert ledger.verify_db(fresh).ok
        # Before anything settles: nothing to score. After 52 h: every horizon scored.
        assert scorer.run(pool, now=created + timedelta(hours=1))["scored"] == 0
        out = scorer.run(pool, now=created + timedelta(hours=52))
        assert out["scored"] == 16
        n, nt = fresh.execute("SELECT count(*) FILTER (WHERE status = 'scored'), count(*) FILTER (WHERE"
                              " status = 'no_truth') FROM forecast_scores").fetchone()
        assert (n, nt) == (16, 0)
        ev = fresh.execute("SELECT events FROM forecast_scores WHERE h = 6 AND model = 'persistence-v1'").fetchone()[0]
        assert set(ev) == {"official:action", "rise:+0.25", "rise:+0.5", "rise:+1.0"}
        assert ev["official:action"]["outcome"] == 0
        # Idempotent: a second run scores nothing new.
        assert scorer.run(pool, now=created + timedelta(hours=53))["scored"] == 0
        summ = fresh.execute("SELECT body FROM score_summaries ORDER BY scorer_run_id DESC LIMIT 1").fetchone()[0]
        g = [x for x in summ["groups"] if x["model"] == "trend3h-v1" and x["h"] == 6][0]
        assert g["n"] == 1 and set(g["skill_vs"]) == {"persistence-v1", "persistence-naive"}
        assert g["brier"]["official"]["note"] == "too few events to judge"
        # Pure persistence is scored from the persistence-v1 entries: CRPS equals the absolute error.
        nv = fresh.execute("SELECT count(*), bool_and(crps = abs(truth_m - q50_m)) FROM forecast_scores_naive"
                           " WHERE status = 'scored'").fetchone()
        assert nv == (8, True)
        assert [x for x in summ["groups"] if x["model"] == "persistence-naive" and x["h"] == 6][0]["coverage"] is None
        # F1: fair CRPS and the secondary quantile score are stored; MAE skill is paired point-vs-point.
        before = fresh.execute("SELECT seq, h, crps, crps_qs FROM forecast_scores WHERE status = 'scored'"
                               " ORDER BY seq, h").fetchall()
        assert all(r[2] is not None and r[3] is not None for r in before)
        assert "mae_skill" in g["skill_vs"]["persistence-naive"]
        # Recomputing from the ledger reproduces the stored values exactly (idempotent), and naive keeps CRPS = AE.
        fresh.execute("UPDATE forecast_scores SET crps = NULL, crps_qs = NULL")
        # A new pool, as in production (`floodlead score --recompute-crps` is its own process): its connections are
        # not in autocommit, which the first version did not handle (it rolled back on production, 19:56Z).
        pool2 = db.pool(test_dsn, max_size=1)
        try:
            rc = scorer.recompute_crps(pool2)
        finally:
            pool2.close()
        assert rc["recompute_crps"]["rows"] == 16
        after = fresh.execute("SELECT seq, h, crps, crps_qs FROM forecast_scores WHERE status = 'scored'"
                              " ORDER BY seq, h").fetchall()
        assert after == before
        assert fresh.execute("SELECT bool_and(crps = crps_qs AND crps = ae_median) FROM forecast_scores_naive"
                             " WHERE status = 'scored'").fetchone()[0]
    finally:
        pool.close()


def test_noaa_point_respects_fetched_at(fresh: psycopg.Connection) -> None:
    issued = datetime(2026, 10, 8, 15, 12, tzinfo=UTC)
    valid = datetime(2026, 10, 9, 0, 0, tzinfo=UTC)
    fresh.execute("INSERT INTO official_forecasts (lid, issued_at, valid_at, stage_ft, flow_kcfs, fetched_at)"
                  " VALUES ('NRKW1', %s, %s, 138.1, 0.7, %s)", (issued, valid, issued + timedelta(minutes=23)))
    later = issued + timedelta(hours=6)
    fresh.execute("INSERT INTO official_forecasts (lid, issued_at, valid_at, stage_ft, flow_kcfs, fetched_at)"
                  " VALUES ('NRKW1', %s, %s, 139.0, 0.9, %s)", (later, valid, later + timedelta(minutes=20)))
    created = issued + timedelta(hours=3)  # only the first issuance had been fetched by then
    p = scorer._noaa_point(fresh, "NRKW1", created, created - timedelta(hours=1), valid)
    assert p["stage_ft"] == 138.1 and p["issued_at"] == "2026-10-08T15:12:00Z" and p["lead_h"] == pytest.approx(8.8)
    assert scorer._noaa_point(fresh, "NRKW1", issued, issued, valid) is None  # nothing fetched yet


def test_typical_peaks_enter_the_ledger_in_new_cards_before_first_use(fresh: psycopg.Connection,
                                                                     test_dsn: str) -> None:
    """D-03.8: the thresholds and their provenance go into new model cards (old cards untouched), in the same
    issuance and at lower seq than the first forecast that uses them."""
    import json

    sid = "usgs:9999998"
    store.upsert_station_meta(fresh, {"station_id": sid, "source": "usgs", "native_id": "9999998", "name": "T",
                                      "params": ["level"]})
    created = datetime(2026, 10, 8, 20, 15, tzinfo=UTC)
    rows = [(created - timedelta(days=35) + i * timedelta(minutes=15), 2.0 + 0.001 * (i % 7))
            for i in range(35 * 96 + 8)]
    obs = [store.Obs(sid, ts, "level", v, v / 0.3048, "ft", {}, False, None) for ts, v in rows
           if ts <= created + timedelta(hours=2)]
    with fresh.transaction():
        store.upsert_observations(fresh, obs, None, now=created - timedelta(minutes=10))
    pool = db.pool(test_dsn, max_size=2)
    try:
        assert issuer.run(pool, now=created)["status"] == "issued"
        cards1 = fresh.execute("SELECT seq, canonical FROM ledger_entries WHERE entry_type = 'model_card'"
                               " ORDER BY seq").fetchall()
        assert all("typical_peak" not in json.loads(c)["data"]["params"] for _, c in cards1)
        fresh.execute("INSERT INTO typical_peaks (method, station_id, status, value_m, n_years, first_year, last_year,"
                      " computed_at) VALUES ('typical-peak-v1', %s, 'ok', 2.5, 20, 2005, 2024, now())", (sid,))
        assert issuer.run(pool, now=created + timedelta(hours=1))["status"] == "issued"
        cards2 = fresh.execute("SELECT seq, canonical FROM ledger_entries WHERE entry_type = 'model_card'"
                               " ORDER BY seq").fetchall()
        new = [(s, json.loads(c)["data"]) for s, c in cards2[len(cards1):]]
        assert len(new) == 2 and cards2[:len(cards1)] == cards1  # appended; the old cards are unchanged
        for _, card in new:
            assert card["params"]["typical_peak"]["values"][sid] == {"level_m": 2.5, "n_years": 20,
                                                                     "years": [2005, 2024]}
            assert card["change"].startswith("typical yearly peak thresholds added") and card["supersedes_seq"]
        fc = fresh.execute("SELECT seq, canonical FROM ledger_entries WHERE entry_type = 'forecast'"
                           " AND base_time = %s ORDER BY seq", (created.replace(minute=0) + timedelta(hours=1),)
                           ).fetchall()
        assert fc and min(s for s, _ in fc) > max(s for s, _ in new)  # cards before first use
        d = json.loads(fc[0][1])["data"]
        assert {"key": "typical:peak", "kind": "typical", "level_m": 2.5} == {
            k: v for k, v in next(t for t in d["thresholds"] if t["key"] == "typical:peak").items()
            if k in ("key", "kind", "level_m")}
        assert all("typical:peak" in hz["p_exceed"] for hz in d["horizons"])
        assert ledger.verify_db(fresh).ok
    finally:
        pool.close()
