"""Training sets: leakage (no feature sees data after issue time - latency) and split integrity. Synthetic inputs."""

import math
from datetime import UTC, datetime, timedelta

import numpy as np

from floodlead import datasets as ds

T0 = datetime(2021, 9, 1, tzinfo=UTC)
T1 = datetime(2021, 12, 31, tzinfo=UTC)


def grid(step: timedelta, f) -> ds.Grid:  # noqa: ANN001
    n = int((T1 - T0) / step) + 1
    return ds.Grid(T0, step, np.array([f(T0 + k * step) for k in range(n)], dtype=float))


def inputs(poison_after: datetime | None = None) -> ds.Inputs:
    def val(t: datetime) -> float:  # a smooth stage; replaced by 999 after the poison time
        return 999.0 if poison_after and t > poison_after else 140.0 + 5 * math.sin((t - T0).total_seconds() / 2e5)

    def rain(t: datetime) -> float:
        return 999.0 if poison_after and t > poison_after else 1.0

    g = {k: grid(ds.STEP, val) for k in ds.GAUGES}
    nws = [{"issued_at": datetime(2021, 11, 14, 19, 50, tzinfo=UTC), "end": datetime(2021, 11, 17, tzinfo=UTC),
            "action": "NEW", "severity": "2", "crest_ft": 148.9, "event": (78, 2022)},
           {"issued_at": datetime(2021, 11, 15, 10, 7, tzinfo=UTC), "end": datetime(2021, 11, 17, tzinfo=UTC),
            "action": "EXT", "severity": "3", "crest_ft": 150.5, "event": (78, 2022)}]
    hourly = {s: grid(ds.HOUR, rain) for s in ds.SNOTEL_SITES}
    return ds.Inputs(g, grid(ds.STEP, lambda t: math.nan), hourly, hourly, grid(ds.HOUR, rain),
                     grid(ds.HOUR, rain), grid(ds.HOUR, rain), grid(ds.HOUR, rain), nws,
                     datetime(2026, 10, 7, tzinfo=UTC))


def test_no_feature_sees_data_after_its_cutoff() -> None:
    clean = inputs()
    for t in (datetime(2021, 11, 14, 21, tzinfo=UTC), datetime(2021, 11, 15, 11, tzinfo=UTC)):
        r = ds.row(clean, t, oracle=False)
        assert r["asof_usgs"] <= t - timedelta(minutes=ds.LATENCY["usgs"])
        assert r["asof_snotel"] <= t - timedelta(minutes=ds.LATENCY["snotel"])
        assert r["asof_kbli"] <= t - timedelta(minutes=ds.LATENCY["kbli"])
        assert r["nws_issued_at"] is None or r["nws_issued_at"] <= t
        # Poison everything after each source's own cut-off: no honest feature may change.
        for src, lat in (("usgs", ds.LATENCY["usgs"]), ("snotel", ds.LATENCY["snotel"]), ("kbli", ds.LATENCY["kbli"])):
            cut = t - timedelta(minutes=lat)
            p = ds.row(inputs(poison_after=cut), t, oracle=False)
            feats = [k for k in r if not k.startswith(("y_", "fc_rain")) and
                     k.split("_")[0] in {"usgs": ("nc", "nf", "mf", "sf", "everson", "ferndale"),
                                         "snotel": ("snotel",), "kbli": ("kbli",)}[src]]
            assert feats
            for k in feats:
                a, b = r[k], p[k]
                assert (a == b) or (isinstance(a, float) and math.isnan(a) and math.isnan(b)), (src, k, a, b)
        # targets do look ahead (by design), so poisoning after t changes them
        assert ds.row(inputs(poison_after=t), t, oracle=False)["y_lvl_h6"] == 999.0


def test_nws_comparator_in_force() -> None:
    inp = inputs()
    before = ds.row(inp, datetime(2021, 11, 14, 19, tzinfo=UTC), oracle=False)
    assert before["nws_in_force"] is False and before["nws_p_ge_148"] == 0.0
    first = ds.row(inp, datetime(2021, 11, 14, 20, tzinfo=UTC), oracle=False)
    assert first["nws_crest_ft"] == 148.9 and first["nws_p_ge_148"] == 1.0 and first["nws_p_ge_150"] == 0.0
    upg = ds.row(inp, datetime(2021, 11, 15, 11, tzinfo=UTC), oracle=False)
    assert upg["nws_p_ge_150"] == 1.0
    assert ds.row(inp, datetime(2021, 11, 17, 1, tzinfo=UTC), oracle=False)["nws_in_force"] is False  # ended


def test_variants_and_split() -> None:
    inp = inputs()
    t = datetime(2021, 11, 14, 21, tzinfo=UTC)
    h, o = ds.row(inp, t, oracle=False), ds.row(inp, t, oracle=True)
    assert h["variant"] == "honest" and not any(k.startswith("oracle_") for k in h)
    assert o["variant"] == "oracle" and o["oracle_future_rain_24h"] == 24.0
    assert math.isnan(h["fc_rain_0_18h"])  # before 2024-01-19 there is no as-issued forecast rain
    assert h["wy"] == 2022 and h["holdout"] is True  # the Nov 2021 flood's water year is held out
    assert ds.row(inp, datetime(2021, 9, 15, tzinfo=UTC), oracle=False)["holdout"] is False  # WY2021
