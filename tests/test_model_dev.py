"""Stage 4 development loader: no held-out or live row reaches a development fit (A1)."""

from pathlib import Path

import pandas as pd
import pytest

from floodlead import model, model_dev, train_data


def write(path: Path, years: list[int], flag_dev_holdout: bool = False) -> Path:
    rows = []
    for wy in years:
        r = {"issue_time": f"{wy - 1}-12-01T00:00:00Z", "wy": wy, "nc_lvl": 140.0, "nc_d3h": 0.0,
             "holdout": wy in (2022, 2026) or (flag_dev_holdout and wy == 2010)}
        r.update({f"y_lvl_h{h}": 140.0 for h in range(1, 49)})
        rows.append(r)
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_load_dev_keeps_development_years_only(tmp_path: Path) -> None:
    p = write(tmp_path / "d.csv", [2009, 2016, 2021, 2022, 2025, 2026, 2027])
    df = model_dev.load_dev(p)
    assert sorted(df["wy"]) == [2009, 2016, 2021, 2025]
    assert set(model.TARGETS) <= set(df.columns)


def test_load_dev_raises_on_a_flagged_development_row(tmp_path: Path) -> None:
    with pytest.raises(train_data.HeldOutRowError):
        model_dev.load_dev(write(tmp_path / "d.csv", [2010, 2011], flag_dev_holdout=True))


def test_every_walk_forward_fold_trains_on_earlier_development_years_only() -> None:
    for train_years, k in train_data.walk_forward_folds():
        years = model_dev.check_fold(pd.DataFrame({"wy": list(train_years)}), k)
        assert not set(years) & {2022, 2026} and max(years) < k < 2026
    for bad in ([2022], [2026], [2027], [2019]):
        with pytest.raises(train_data.HeldOutRowError):
            model_dev.check_fold(pd.DataFrame({"wy": [2015, *bad]}), 2019)
