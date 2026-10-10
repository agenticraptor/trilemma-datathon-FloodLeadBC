"""Stage 4 report scoring on a synthetic validation set; calibration refuses any non-validation year."""

from statistics import NormalDist

import numpy as np
import pandas as pd
import pytest

from floodlead import model, model_report, train_data


def synthetic(years: tuple[int, ...] = (2018, 2019)) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, np.ndarray]]:
    rng = np.random.default_rng(5)
    parts = []
    for wy in years:
        t = pd.date_range(f"{wy - 1}-11-01", periods=400, freq="h", tz="UTC")
        lvl = 144 + 3 * np.sin(np.arange(len(t)) / 40) + rng.normal(0, 0.05, len(t))
        d = {"issue_time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "wy": wy, "nc_lvl": lvl,
             "nc_d3h": np.r_[np.zeros(3), lvl[3:] - lvl[:-3]], "overflow_flowing": 0.0, "nws_in_force": 0.0,
             "nws_p_ge_148": 0.0, "nws_p_ge_150": 0.0}
        for h in range(1, 49):
            d[f"y_lvl_h{h}"] = np.r_[lvl[h:], np.full(h, np.nan)]
        parts.append(pd.DataFrame(d))
    df = model.targets(pd.concat(parts, ignore_index=True))
    for name, x in model_report.THRESH.items():
        for w in (6, 12, 24, 48):
            m = np.nanmax(df[[f"y_lvl_h{h}" for h in range(1, w + 1)]].to_numpy(), axis=1)
            df[f"y_{name}_{w}h"] = (m >= x).astype(float)
    for w in (6, 12, 24):
        df[f"y_overflow_{w}h"] = df[f"y_moderate_{w}h"]
    z = np.array([NormalDist().inv_cdf(p) for p in model.LEVELS])
    preds = {t: (df[t].fillna(0).to_numpy()[:, None] + 0.3 * z[None, :]) for t in model.TARGETS}
    return df, df[["issue_time", "wy"]], preds


def test_score_runs_and_reports_every_block() -> None:
    df, idx, preds = synthetic()
    events = {"ge_148ft": [], "overflow_onset": []}
    inputs = {"onset_levels_ft": [147.6, 147.92, 148.44]}
    out = model_report.score(df, idx, preds, inputs, events)
    assert out["headline_fair_crps_6_12_24"] is not None and out["rows"] == len(df)
    assert {"moderate_148ft_within_24h", "major_150ft_within_48h"} <= set(out["crossing"])
    assert {"onset_within_6h", "onset_within_12h"} <= set(out["overflow"])
    assert {"prepare", "move"} <= set(out["alerts"])
    t6 = {(r["h"], r["rising_only"]): r for r in out["T6_level"]}
    assert t6[(6, False)]["fair_crpss_vs_persistence"] > 0  # an informed synthetic forecast beats persistence


def test_calibration_refuses_any_non_validation_year() -> None:
    p, o = np.array([0.1, 0.8, 0.4]), np.array([0.0, 1.0, 0.0])
    model_report.fit_calibration(p, o, np.array([2016, 2020, 2025]))
    for bad in (2022, 2026, 2027, 2010):
        with pytest.raises(train_data.HeldOutRowError):
            model_report.fit_calibration(p, o, np.array([2016, 2020, bad]))
        with pytest.raises(train_data.HeldOutRowError):
            model_report.isotonic_loyo(p, o, np.array([2016, 2020, bad]))


def test_median_path_crossing() -> None:
    assert model_report.median_path_crossing(146.0, {1: 0.5, 3: 1.5, 6: 3.0, 12: 4.0}, 147.0) == pytest.approx(2.0)
    assert model_report.median_path_crossing(146.0, {1: 0.0, 3: 0.1, 6: 0.2, 12: 0.3}, 147.0) is None
    assert model_report.median_path_crossing(148.0, {1: 0.0, 3: 0.0, 6: 0.0, 12: 0.0}, 147.0) == 0.0


def test_development_report_end_to_end(tmp_path) -> None:  # noqa: ANN001
    import json

    df, idx, preds = synthetic()
    df["holdout"] = False
    df.to_csv(tmp_path / "nooksack_hourly_honest_v1.csv.gz", index=False)
    pd_dir = tmp_path / "p"
    pd_dir.mkdir()
    np.savez_compressed(pd_dir / "preds-lgb_GR_sub.npz", issue_time=idx["issue_time"].to_numpy(dtype=str),
                        wy=idx["wy"].to_numpy(), **{k: v.astype(np.float32) for k, v in preds.items()})
    hi = df.loc[df["nc_lvl"] >= 147.0, "issue_time"].iloc[0]
    inputs = {"onset_levels_ft": [147.6, 147.92, 148.44],
              "validation_events": {"ge_148ft": [hi], "overflow_onset": [hi]},
              "development_events_ge_148ft": [{"event_id": "e1"}], "development_overflow_onsets": [{"event_id": "e1"}]}
    cat = {"nooksack": [{"event_id": "e1", "wy": 2018, "crest_ft": 147.1, "minor_first": hi, "moderate_first": hi,
                         "overflow_gauge_operating": True, "overflow_onset": hi, "first_nws_warning": None},
                        {"event_id": "e0", "wy": 2009, "crest_ft": 148.0, "minor_first": hi, "moderate_first": hi,
                         "overflow_gauge_operating": False, "overflow_onset": None}]}
    for name, body in (("inputs.json", inputs), ("cat.json", cat), ("relay.json", {"events": []})):
        (tmp_path / name).write_text(json.dumps(body))
    rep = model_report.development_report(tmp_path, [pd_dir], tmp_path / "inputs.json", tmp_path / "cat.json",
                                          tmp_path / "relay.json", None)
    c = rep["candidates"][0]
    assert rep["ranking_G+R"][0]["candidate"] == "lgb_GR_sub"
    assert {r["target"] for r in c["T_table"]} >= {"T1", "T2", "T3", "T5", "T6"}
    assert c["events"][0]["event_id"] == "e1" and "isotonic_wins" in c["isotonic_check_148ft_24h"]
    json.dumps(rep, default=float)
