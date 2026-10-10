"""Stage 4 final models: A2 rows only, artifacts refused on a hash mismatch, rules frozen from development."""

import json
import pickle
from pathlib import Path

import pandas as pd
import pytest

from floodlead import model, model_final


def write(path: Path, years: list[int]) -> Path:
    rows = []
    for wy in years:
        r = {"issue_time": f"{wy - 1}-12-01T00:00:00Z", "wy": wy, "nc_lvl": 140.0, "nc_d3h": 0.0,
             "holdout": wy in (2022, 2026)}
        r.update({f"y_lvl_h{h}": 140.0 for h in range(1, 49)})
        rows.append(r)
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_final_frame_reads_exactly_the_a2_years(tmp_path: Path) -> None:
    p = write(tmp_path / "d.csv.gz", [2009, 2021, 2022, 2025, 2026, 2027])
    assert sorted(model_final.final_frame(p, "heldout_wy2022")["wy"]) == [2009, 2021]
    assert sorted(model_final.final_frame(p, "heldout_wy2026")["wy"]) == [2009, 2021, 2022, 2025]


def test_artifact_with_a_different_hash_is_refused(tmp_path: Path) -> None:
    a = tmp_path / "GR_heldout_wy2026.pkl"
    a.write_bytes(pickle.dumps(model.Fitted("lgb", "G+R", ["nc_lvl"], True, [2005])))
    good = model_final.sha256_file(a)
    assert model_final.load_artifact(a, good).group == "G+R"
    with pytest.raises(ValueError, match="refusing"):
        model_final.load_artifact(a, "0" * 64)
    a.write_bytes(a.read_bytes() + b"x")
    with pytest.raises(ValueError, match="refusing"):
        model_final.load_artifact(a, good)


def test_rules_are_frozen_from_each_variants_validation_choice() -> None:
    def cand(cid: str, p: float) -> dict:
        ch = {"chosen": {"p_star": p, "k": 2}, "far_limit_met": True}
        return {"candidate": cid, "alerts": {"prepare": ch, "move": ch}}

    dev = {"candidates": [cand("lgb_GR_sub", 0.3), cand("lgb_G_sub", 0.5), cand("lgb_oracle_sub", 0.4)]}
    r = model_final.freeze_from_dev(dev, "lgb_GR_sub")
    assert r["G+R"]["prepare"]["p_star"] == 0.3 and r["G"]["move"]["p_star"] == 0.5
    assert r["oracle"]["prepare"]["p_star"] == 0.4 and r["G+R+F"]["prepare"]["p_star"] == 0.3


def test_plan_covers_both_folds_and_the_ablations() -> None:
    names = {(p["group"], p["fold"]) for p in model_final.plan("lgb", True)}
    assert ("G+R", "heldout_wy2022") in names and ("G+R", "heldout_wy2026") in names
    assert ("G+R+F", "heldout_wy2026") in names and ("G+R+F", "heldout_wy2022") not in names
    assert {g for g, _ in names} == {"G+R", "G", "oracle", "G+R+F"}


def test_card_carries_the_manifest_hash(tmp_path: Path) -> None:
    m = tmp_path / "m.json"
    m.write_text(json.dumps({"code_commit": "abc", "protocol": {"sha256": "p"}, "chosen": {"family": "lgb"}}))
    c = model_final.card(m)
    assert c["params"]["manifest_sha256"] == model_final.sha256_file(m) and len(c["params_hash"]) == 64


def synthetic_dataset(path: Path, oracle: bool = False) -> Path:
    import numpy as np

    rng = np.random.default_rng(11)
    parts = []
    for wy in (2019, 2021, 2022, 2025, 2026, 2027):
        t = pd.date_range(f"{wy - 1}-11-01", periods=240, freq="h", tz="UTC")
        lvl = 145 + 3.5 * np.sin(np.arange(len(t)) / 30) + rng.normal(0, 0.05, len(t))
        d = {"issue_time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "wy": wy, "holdout": wy in (2022, 2026), "nc_lvl": lvl,
             "nc_d3h": np.r_[np.zeros(3), lvl[3:] - lvl[:-3]], "overflow_flowing": False, "nws_in_force": False,
             "nws_p_ge_148": 0.0, "nws_p_ge_150": 0.0, "nws_crest_ft": np.nan, "nws_issued_at": ""}
        for c in set(model.G + model.R + model.F) - {"nc_lvl", "nc_d3h"}:
            d[c] = rng.normal(size=len(t))
        if oracle:
            for c in model.ORACLE:
                d[c] = rng.random(len(t))
        for h in range(1, 49):
            d[f"y_lvl_h{h}"] = np.r_[lvl[h:], np.full(h, np.nan)]
        df = pd.DataFrame(d)
        for name, x in (("minor", 146.5), ("moderate", 148.0), ("major", 150.0)):
            for w in (6, 12, 24, 48):
                m = np.nanmax(df[[f"y_lvl_h{h}" for h in range(1, w + 1)]].to_numpy(), axis=1)
                df[f"y_{name}_{w}h"] = (m >= x).astype(float)
        for w in (6, 12, 24):
            df[f"y_overflow_{w}h"] = df[f"y_moderate_{w}h"]
        parts.append(df)
    pd.concat(parts).to_csv(path, index=False)
    return path


def test_final_run_end_to_end_and_refusal(tmp_path: Path) -> None:
    import warnings

    warnings.filterwarnings("ignore")
    ds = tmp_path / "ds"
    ds.mkdir()
    synthetic_dataset(ds / model_final.HONEST)
    synthetic_dataset(ds / model_final.ORACLE, oracle=True)
    run = tmp_path / "run"
    run.mkdir()
    arts = []
    for fold, years in (("heldout_wy2022", [2019, 2021]), ("heldout_wy2026", [2019, 2021, 2022, 2025])):
        df = model.targets(pd.read_csv(ds / model_final.HONEST))
        df = df[df["wy"].isin(years)]
        fm = model.fit(df, "lgb", "G+R", False, years, model_final.METRIC_TARGETS + ("d_1", "d_3"))
        a = run / f"GR_{fold}.pkl"
        a.write_bytes(pickle.dumps(fm))
        arts.append({"artifact": a.name, "sha256": model_final.sha256_file(a), "group": "G+R", "fold": fold})
    rule = {"prepare": {"p_star": 0.5, "k": 1}, "move": {"p_star": 0.5, "k": 1}}
    man = {"datasets": {n: model_final.sha256_file(ds / n) for n in (model_final.HONEST, model_final.ORACLE)},
           "artifacts": arts, "alert_rules": {"G+R": rule}, "calibration": {"used": False}}
    mp = tmp_path / "manifest.json"
    mp.write_text(json.dumps(man))
    hi22 = "2021-11-03T00:00:00Z"
    cat = {"nooksack": [
        {"event_id": "2021-11-03", "wy": 2022, "minor_first": hi22, "moderate_first": hi22, "major_first": None,
         "overflow_onset": hi22, "overflow_gauge_operating": True, "crest_ft": 148.4, "crest_at": hi22,
         "first_nws_warning": {"issued_at": "2021-11-02T10:00:00Z"}},
        {"event_id": "2025-11-03", "wy": 2026, "minor_first": "2025-11-03T00:00:00Z", "moderate_first": None,
         "major_first": None, "overflow_onset": None, "overflow_gauge_operating": True, "crest_ft": 147.0,
         "crest_at": "2025-11-03T03:00:00Z", "first_nws_warning": None}]}
    trust = {"tiers": {"prepare": {"list": [{"at": "2021-11-02T12:00:00Z"}]}, "move_now_5.0ft": {"list": []}}}
    for name, body in (("cat.json", cat), ("relay.json", {"events": []}), ("trust.json", trust),
                       ("inputs.json", {"onset_levels_ft": [147.6, 147.92, 148.44]})):
        (tmp_path / name).write_text(json.dumps(body))
    res = model_final.final_run(ds, mp, run, tmp_path / "inputs.json", tmp_path / "cat.json",
                                tmp_path / "relay.json", tmp_path / "trust.json")
    assert set(res["variants"]["G+R"]) == {"heldout_wy2022", "heldout_wy2026", "live_wy2027", "heldout_pooled"}
    assert res["section11"] and res["kill_criteria"]["what_ships_in_stage_5"]
    ev = res["variants"]["G+R"]["heldout_wy2022"]["events"][0]
    assert ev["relay_v2"]["prepare"] == "2021-11-02T12:00:00Z" and "hours_before_onset" in ev
    json.dumps(res, default=float)
    (run / "GR_heldout_wy2026.pkl").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="refusing"):
        model_final.final_run(ds, mp, run, tmp_path / "inputs.json", tmp_path / "cat.json",
                              tmp_path / "relay.json", tmp_path / "trust.json")
