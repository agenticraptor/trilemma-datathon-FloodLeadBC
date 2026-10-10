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
