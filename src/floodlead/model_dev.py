"""Stage 4 development: walk-forward on validation years only (protocol amendments 1 and 4).

`fit_candidates` fits each candidate (family, feature group, quiet-row subsample) on every walk-forward fold (train on
development years before k, validate on year k), checks every training row's water year, and saves the pooled
validation predictions (19 quantiles per target) and a fit log. `score` (below) reads them back with the dataset, so
scoring never refits. Everything here is "development (walk-forward), used to choose the model; not the result".
"""

from __future__ import annotations

import json
import resource
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from floodlead import model, train_data

LABEL = "development (walk-forward), used to choose the model; not the result"
BOOL_COLS = ("overflow_flowing", "nws_in_force", "holdout")


def read_frame(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    for c in BOOL_COLS:
        if c in df:
            df[c] = df[c].map({True: 1.0, False: 0.0, "True": 1.0, "False": 0.0}).astype(float)
    return df


def load_dev(path: Path) -> pd.DataFrame:
    """Development rows only (A1): selected by water year; a development row flagged holdout raises."""
    df = read_frame(path)
    df = df[df["wy"].isin(train_data.DEVELOPMENT_WY)]
    if (df["holdout"] == 1.0).any():
        raise train_data.HeldOutRowError("a development-year row is flagged holdout")
    df = model.targets(df)
    return df.reset_index(drop=True).copy()


def check_fold(train: pd.DataFrame, k: int) -> list[int]:
    """Every training row is a development year before the validation year k (A1); raises otherwise."""
    years = sorted(int(y) for y in train["wy"].unique())
    train_data.check_training_rows({"wy": str(y)} for y in years)
    bad = [y for y in years if y >= k]
    if bad:
        raise train_data.HeldOutRowError(f"fold {k}: training years {bad} are not before the validation year")
    return years


def parse_candidate(c: str) -> tuple[str, str, bool]:
    fam, group, sub = c.split(":")
    if fam not in ("lgb", "linear") or group not in model.GROUPS or sub not in ("sub", "full"):
        raise ValueError(f"bad candidate {c!r}: family:group:sub|full")
    return fam, group, sub == "sub"


def candidate_id(fam: str, group: str, sub: bool) -> str:
    return f"{fam}_{group.replace('+', '')}_{'sub' if sub else 'full'}"


def fit_candidates(datasets: Path, out: Path, candidates: list[str], targets: tuple[str, ...],
                   folds: list[int] | None = None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    frames: dict[str, pd.DataFrame] = {}
    for cand in candidates:
        fam, group, sub = parse_candidate(cand)
        name = "nooksack_hourly_oracle_v1.csv.gz" if group == "oracle" else "nooksack_hourly_honest_v1.csv.gz"
        if name not in frames:
            frames[name] = load_dev(datasets / name)
        df = frames[name]
        cid = candidate_id(fam, group, sub)
        preds: dict[str, list[np.ndarray]] = {t: [] for t in targets}
        times: list[np.ndarray] = []
        wys: list[np.ndarray] = []
        c0 = time.monotonic()
        for train_years, k in train_data.walk_forward_folds():
            if folds and k not in folds:
                continue
            train = df[df["wy"].isin(train_years)]
            years = check_fold(train, k)
            t0 = time.monotonic()
            fm = model.fit(train, fam, group, sub, years, targets)
            val = df[df["wy"] == k]
            p = model.predict(fm, val)
            for t in targets:
                preds[t].append(p[t].astype(np.float32))
            times.append(val["issue_time"].to_numpy(dtype=str))
            wys.append(val["wy"].to_numpy(dtype=int))
            rec = {"candidate": cid, "family": fam, "group": group, "subsample": sub, "targets": list(targets),
                   "validate_wy": k, "train_wy": years, "train_rows": int(len(train)), "fit_s": fm.fit_seconds,
                   "fit_predict_s": round(time.monotonic() - t0, 1),
                   "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
                   "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
            with (out / "fitlog.jsonl").open("a") as f:
                f.write(json.dumps(rec) + "\n")
            print(json.dumps(rec), flush=True)
        np.savez_compressed(out / f"preds-{cid}.npz", issue_time=np.concatenate(times), wy=np.concatenate(wys),
                            **{t: np.vstack(v) for t, v in preds.items()})
        print(json.dumps({"candidate": cid, "done_s": round(time.monotonic() - c0, 1)}), flush=True)


def load_preds(path: Path) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    z = np.load(path)
    idx = pd.DataFrame({"issue_time": z["issue_time"], "wy": z["wy"]})
    return idx, {k: z[k].astype(float) for k in z.files if k not in ("issue_time", "wy")}


def merge_preds(paths: list[Path], out: Path) -> list[str]:
    """One candidate's predictions from several runs (e.g. selection targets + the remaining targets), checked to
    cover the same rows in the same order."""
    base = np.load(paths[0])
    arrays = {k: base[k] for k in base.files}
    for p in paths[1:]:
        z = np.load(p)
        if not (np.array_equal(z["issue_time"], arrays["issue_time"]) and np.array_equal(z["wy"], arrays["wy"])):
            raise ValueError(f"{p} covers different rows")
        arrays.update({k: z[k] for k in z.files if k not in ("issue_time", "wy")})
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, **arrays)
    return sorted(k for k in arrays if k not in ("issue_time", "wy"))
