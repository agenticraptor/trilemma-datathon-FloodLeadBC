"""Stage 4 final models (protocol amendment 1, A2) and their manifest. The only caller of
`train_data.final_training_rows()`.

- `heldout_wy2022`: trained on WY2005-2021, scores WY2022.
- `heldout_wy2026`: trained on WY2005-2025 (including WY2022), scores WY2026; the same artifact scores the live period
  (WY2027), as `final_run_folds()['live']` has the same years.
The configuration, features, (p*, k) and calibration are frozen from the walk-forward development (amendment 4).
Artifacts go to a new directory and are never overwritten; the manifest records every sha256.
"""

from __future__ import annotations

import hashlib
import json
import pickle
import resource
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from floodlead import ledger, model, model_dev, train_data

MODEL_NAME = "floodlead-nooksack-v1"
HONEST = "nooksack_hourly_honest_v1.csv.gz"
ORACLE = "nooksack_hourly_oracle_v1.csv.gz"
METRIC_TARGETS = ("d_6", "d_12", "d_24", "m_12", "m_24", "m_48")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def final_frame(path: Path, fold: str) -> pd.DataFrame:
    """The A2 training rows of `fold`, selected through `final_training_rows()` and re-checked."""
    allowed = {r["issue_time"] for r in train_data.final_training_rows(path, fold)}
    df = model_dev.read_frame(path)
    df = df[df["issue_time"].isin(allowed)]
    train_data.check_final_rows(({"wy": str(w)} for w in df["wy"].unique()), fold)
    return model.targets(df).reset_index(drop=True)


def plan(family: str, sub: bool) -> list[dict[str, Any]]:
    """The artifacts the checkpoint fixes: the primary (G+R, every target) for both A2 folds, and each ablation
    (its metric targets) for the folds it is scored on."""
    out = []
    for fold in ("heldout_wy2022", "heldout_wy2026"):
        out.append({"group": "G+R", "fold": fold, "targets": list(model.TARGETS), "role": "primary"})
        out.append({"group": "G", "fold": fold, "targets": list(METRIC_TARGETS), "role": "ablation: gauges only"})
        out.append({"group": "oracle", "fold": fold, "targets": list(METRIC_TARGETS),
                    "role": "ablation: oracle (future observed rain), an upper bound"})
    out.append({"group": "G+R+F", "fold": "heldout_wy2026", "targets": list(METRIC_TARGETS),
                "role": "ablation: plus as-issued forecast rain (exists from 2024-01-19; scored on WY2026 only)"})
    for p in out:
        p.update({"family": family, "subsample": sub})
    return out


def train(datasets: Path, out: Path, family: str, sub: bool, only: list[str] | None = None) -> list[dict[str, Any]]:
    out.mkdir(parents=True, exist_ok=True)
    frames: dict[tuple[str, str], pd.DataFrame] = {}
    arts = []
    for p in plan(family, sub):
        name = f"{p['group'].replace('+', '')}_{p['fold']}"
        if only and name not in only:
            continue
        dest = out / f"{name}.pkl"
        if dest.exists():
            raise FileExistsError(f"{dest} exists; final artifacts are never overwritten")
        ds = ORACLE if p["group"] == "oracle" else HONEST
        key = (ds, p["fold"])
        if key not in frames:
            frames.clear()
            frames[key] = final_frame(datasets / ds, p["fold"])
        df = frames[key]
        years = sorted(int(y) for y in df["wy"].unique())
        assert years == list(train_data.final_run_folds()[p["fold"]]), (years, p["fold"])
        t0 = time.monotonic()
        fm = model.fit(df, family, p["group"], sub, years, tuple(p["targets"]))
        dest.write_bytes(pickle.dumps(fm))
        rec = {**p, "artifact": dest.name, "sha256": sha256_file(dest), "train_wy": years, "train_rows": int(len(df)),
               "features": fm.features, "fit_s": round(time.monotonic() - t0, 1),
               "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
               "trained_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
        with (out / "artifacts.jsonl").open("a") as f:
            f.write(json.dumps(rec) + "\n")
        print(json.dumps({k: rec[k] for k in ("artifact", "sha256", "train_rows", "fit_s", "peak_rss_mb")}), flush=True)
        arts.append(rec)
    return arts


def load_artifact(path: Path, sha256: str) -> model.Fitted:
    got = sha256_file(path)
    if got != sha256:
        raise ValueError(f"{path.name}: sha256 {got} does not match the manifest ({sha256}); refusing to run")
    return pickle.loads(path.read_bytes())  # noqa: S301 - our own artifact, hash-checked against the manifest


def manifest(run_dir: Path, datasets: Path, dev_report: dict[str, Any], chosen: str, rules: dict[str, Any],
             calibration: dict[str, Any], inputs_path: Path, protocol_path: Path) -> dict[str, Any]:
    arts = [json.loads(line) for line in (run_dir / "artifacts.jsonl").read_text().splitlines()]
    fam, group, sub = chosen.split("_")[0], "G+R", chosen.endswith("_sub")
    return {
        "model": MODEL_NAME,
        "what": "The Stage 4 final models, fixed before any held-out row is scored (protocol amendment 1 A2, "
                "amendment 4 item 10). The final run refuses to start if any artifact's sha256 differs.",
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "code_commit": ledger.code_commit(),
        "run_dir": str(run_dir),
        "protocol": {"file": "docs/evaluation-protocol.md", "sha256": sha256_file(protocol_path),
                     "amendments": "1-4"},
        "datasets": {n: sha256_file(datasets / n) for n in (HONEST, ORACLE)},
        "inputs": {"file": "docs/data/stage4-inputs-v1.json", "sha256": sha256_file(inputs_path)},
        "chosen": {"candidate": chosen, "family": fam, "group": group, "subsample": sub,
                   "why": "lowest pooled walk-forward validation fair CRPS over 6/12/24 h among the G+R candidates "
                          "(amendment 4, item 6); see docs/data/stage4-development-v1.json"},
        "config": {"fit_levels": list(model.FIT_LEVELS), "levels": list(model.LEVELS), "horizons": list(model.HORIZONS),
                   "windows": list(model.WINDOWS), "lgb_params": model.LGB_PARAMS,
                   "linear_features": model.LINEAR_FEATURES, "linear_max_rows": model.LINEAR_MAX_ROWS,
                   "linear_solver": "highs-ipm", "seed": model.SEED,
                   "quiet_rows": "|nc_d3h| < 0.1 ft and nc_lvl < 144 ft; 20 % kept when subsampling",
                   "crossing": "P(>= X within H) = 1 - F_H(X - nc_lvl), F_H piecewise linear between the 19 window-max "
                               "quantiles with crps.py exponential tails",
                   "overflow": "mean over the development onset levels L_j of P(M_H >= L_j); 6 h uses the 6-h level "
                               "quantiles; onset time = median path reaching the median L_j"},
        "features": {g: model.GROUPS[g] for g in model.GROUPS},
        "onset_levels_ft": dev_report["inputs"]["onset_levels_ft"],
        "alert_rules": rules,
        "calibration": calibration,
        "artifacts": arts,
        "final_run": {"heldout_wy2022": "artifacts *_heldout_wy2022 (trained WY2005-2021)",
                      "heldout_wy2026": "artifacts *_heldout_wy2026 (trained WY2005-2025, incl. WY2022)",
                      "live": "the heldout_wy2026 artifacts (final_run_folds()['live'] has the same years)"},
    }


def card(manifest_path: Path) -> dict[str, Any]:
    """The ledger model_card for the manifest (docs/ledger-spec.md §4)."""
    m = json.loads(manifest_path.read_text())
    params = {"model": MODEL_NAME, "manifest_file": "docs/data/stage4-final-manifest-v1.json",
              "manifest_sha256": sha256_file(manifest_path), "code_commit_trained": m["code_commit"],
              "protocol_sha256": m["protocol"]["sha256"], "status": "fixed before any held-out row is scored; "
              "not issued live until Stage 5"}
    return {"model": MODEL_NAME,
            "method": "North Cedarville level quantiles (19) at 1-48 h and window maxima at 12/24/48 h from "
                      f"{m['chosen']['family']} quantile models on gauges and observed rain (Stage 4, amendment 4); "
                      "P(>= 148/150 ft) from the window-maximum distribution; overflow onset from the North "
                      "Cedarville level at past onsets. Every parameter and artifact hash is in the manifest.",
            "params": params, "params_hash": hashlib.sha256(ledger.canonical_json(params).encode()).hexdigest(),
            "code_commit": ledger.code_commit()}


def append_card(conn: Any, manifest_path: Path) -> dict[str, Any]:
    data = card(manifest_path)
    with conn.transaction():
        last = conn.execute("SELECT seq FROM ledger_entries WHERE entry_type = 'model_card' AND model = %s"
                            " ORDER BY seq DESC LIMIT 1", (MODEL_NAME,)).fetchone()
        if last:
            raise RuntimeError(f"{MODEL_NAME} already has a card (seq {last[0]}); a new one needs a new version")
        written = ledger.append(conn, [ledger.Pending("model_card", data, datetime.now(UTC), model=MODEL_NAME)])
    e = written[0]
    return {"seq": e.seq, "entry_hash": e.entry_hash, "created_at": ledger.ts(e.created_at, ms=True),
            "manifest_sha256": data["params"]["manifest_sha256"]}



def freeze_from_dev(dev: dict[str, Any], chosen: str) -> dict[str, Any]:
    """(p*, k) per variant from the development report: each variant's own validation choice; G+R+F has no
    validation event in WY2024-2025, so it uses the primary's rule (D-04.11)."""
    by = {c["candidate"]: c for c in dev["candidates"]}
    sub = chosen.split("_", 2)[2]
    fam = chosen.split("_")[0]
    rules: dict[str, Any] = {}
    for group, cid in (("G+R", chosen), ("G", f"{fam}_G_{sub}"), ("oracle", f"{fam}_oracle_{sub}")):
        c = by.get(cid)
        if c is None:
            continue
        rules[group] = {t: {"p_star": c["alerts"][t]["chosen"]["p_star"], "k": c["alerts"][t]["chosen"]["k"],
                            "far_limit_met_on_validation": c["alerts"][t]["far_limit_met"],
                            "chosen_on": f"{cid} pooled walk-forward validation predictions"}
                        for t in ("prepare", "move") if t in c["alerts"]}
    rules["G+R+F"] = {t: {**v, "chosen_on": "the primary's rule: no validation event lies in WY2024-2025"}
                      for t, v in rules["G+R"].items()}
    return rules


def calibration_maps(datasets: Path, preds_path: Path, dev: dict[str, Any], chosen: str) -> dict[str, Any]:
    """D-04.9: isotonic maps for the 148-ft probabilities only if the LOYO check won; otherwise none."""
    from floodlead import model_report

    c = next(c for c in dev["candidates"] if c["candidate"] == chosen)
    chk = c["isotonic_check_148ft_24h"]
    if not chk["isotonic_wins"]:
        return {"used": False, "why": f"LOYO isotonic Brier {chk['brier_loyo_isotonic']} did not beat raw "
                                      f"{chk['brier_raw']} (>= 148 ft within 24 h); raw CDF probabilities are used"}
    frame = model_dev.load_dev(datasets / HONEST)
    idx, preds = model_dev.load_preds(preds_path)
    val, jp = model_report.joined(frame, idx, preds)
    maps = {}
    for w in (12, 24, 48):
        p = model.crossing_prob(jp[f"m_{w}"], val["nc_lvl"].to_numpy(dtype=float), 148.0)
        maps[f"moderate_148ft_within_{w}h"] = model_report.fit_calibration(
            p, val[f"y_moderate_{w}h"].to_numpy(dtype=float), val["wy"].to_numpy(dtype=int))
    return {"used": True, "why": f"LOYO isotonic Brier {chk['brier_loyo_isotonic']} < raw {chk['brier_raw']}",
            "maps": maps, "applies_to": "148-ft crossing probabilities only (D-04.9)"}
