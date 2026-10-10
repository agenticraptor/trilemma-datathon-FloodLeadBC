"""Protocol amendment 1 (A1, A2): training never sees held-out or live rows."""

import csv
import gzip
from pathlib import Path

import pytest

from floodlead import train_data as td


def write(path: Path, years: list[tuple[int, str]]) -> Path:
    with gzip.open(path, "wt", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["issue_time", "wy", "holdout", "x"])
        w.writeheader()
        for wy, hold in years:
            w.writerow({"issue_time": f"{wy - 1}-12-01T00:00:00Z", "wy": wy, "holdout": hold, "x": 1})
    return path


def test_development_years_are_explicit() -> None:
    assert 2022 not in td.DEVELOPMENT_WY and 2026 not in td.DEVELOPMENT_WY and 2027 not in td.DEVELOPMENT_WY
    assert min(td.DEVELOPMENT_WY) == 2005 and max(td.DEVELOPMENT_WY) == 2025
    assert td.split_of(2022) == "heldout_wy2022" and td.split_of(2027) == "live" and td.split_of(2030) == "live"


def test_loader_rejects_heldout_and_live_rows(tmp_path: Path) -> None:
    # the frozen files flag WY2027 (live, Oct 2026) as holdout=False: the loader must still drop it
    p = write(tmp_path / "d.csv.gz", [(2020, "False"), (2022, "True"), (2023, "False"), (2026, "True"),
                                      (2027, "False")])
    got = [int(r["wy"]) for r in td.development_rows(p)]
    assert got == [2020, 2023]
    for y in (2022, 2026, 2027):
        with pytest.raises(td.HeldOutRowError):
            list(td.development_rows(p, years=[y]))
        with pytest.raises(td.HeldOutRowError):
            td.check_training_rows([{"wy": str(y)}])
    assert td.check_training_rows(td.development_rows(p)) == 2


def test_contradicting_holdout_flag_raises(tmp_path: Path) -> None:
    p = write(tmp_path / "bad.csv.gz", [(2019, "True")])
    with pytest.raises(td.HeldOutRowError):
        list(td.development_rows(p))


def test_walk_forward_never_trains_on_wy2022_and_final_run_folds() -> None:
    for train, k in td.walk_forward_folds():
        assert k in td.DEVELOPMENT_WY and 2022 not in train and all(y < k for y in train)
    assert [k for _, k in td.walk_forward_folds()] == [2016, 2017, 2018, 2019, 2020, 2021, 2023, 2024, 2025]
    f = td.final_run_folds()
    assert f["heldout_wy2022"][-1] == 2021 and 2022 in f["heldout_wy2026"] and f["live"] == f["heldout_wy2026"]


def test_final_training_rows_allow_exactly_the_a2_folds(tmp_path: Path) -> None:
    years = [(2015, "False"), (2021, "False"), (2022, "True"), (2025, "False"), (2026, "True"), (2027, "False")]
    p = write(tmp_path / "f.csv.gz", years)
    got = {f: sorted({int(r["wy"]) for r in td.final_training_rows(p, f)}) for f in td.final_run_folds()}
    assert got["heldout_wy2022"] == [2015, 2021]  # WY2022 refused in its own fold
    assert got["heldout_wy2026"] == [2015, 2021, 2022, 2025] == got["live"]  # WY2022 allowed, as in A2
    for f in td.final_run_folds():
        assert 2026 not in got[f] and 2027 not in got[f]
        with pytest.raises(td.HeldOutRowError):
            td.check_final_rows([{"wy": "2026"}], f)
        with pytest.raises(td.HeldOutRowError):
            td.check_final_rows([{"wy": "2027"}], f)
    with pytest.raises(td.HeldOutRowError):
        td.check_final_rows([{"wy": "2022"}], "heldout_wy2022")
    with pytest.raises(td.HeldOutRowError):
        list(td.final_training_rows(p, "development"))


def test_only_the_final_run_module_calls_final_training_rows() -> None:
    src = Path(__file__).resolve().parents[1] / "src" / "floodlead"
    callers = {p.name for p in src.rglob("*.py") if "final_training_rows(" in p.read_text()}
    assert callers <= {"train_data.py", "model_final.py"}, callers
