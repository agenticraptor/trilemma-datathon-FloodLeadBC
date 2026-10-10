"""Stage 4 data loader for the frozen training sets (protocol amendment 1, A1 and A2; D-03.20).

The frozen files mark only WY2022 and WY2026 as `holdout`; rows from WY2027 onward (the live period, from
2026-10-01) are marked `holdout = false`. They are not rebuilt (their sha256 values are pinned). Instead every Stage 4
read goes through this module, which selects rows by water year:

- development years: WY2005-WY2025 except WY2022; every training fold and every calibration fit uses only these;
- held-out years: WY2022 (Nov 2021 flood) and WY2026 (Dec 2025 flood), read only by the single final run;
- live period: WY2027 onward, never trained on, scored live.

Walk-forward (A1): validate on WY k (2016-2025 except 2022), train on development years < k.
Final run (A2): WY2022 is scored by a model trained on WY2005-2021; WY2026 by a model trained on WY2005-2025
including WY2022 (a live system would have had the 2021 flood by Dec 2025); the live period by the WY2026 model.
"""

from __future__ import annotations

import csv
import gzip
from collections.abc import Iterable, Iterator
from pathlib import Path

FIRST_WY, LAST_DEV_WY = 2005, 2025
HELDOUT_WY = frozenset({2022, 2026})
LIVE_FROM_WY = 2027
DEVELOPMENT_WY = frozenset(set(range(FIRST_WY, LAST_DEV_WY + 1)) - HELDOUT_WY)
VALIDATION_WY = tuple(sorted(y for y in DEVELOPMENT_WY if y >= 2016))


class HeldOutRowError(ValueError):
    """A held-out or live row reached a development read."""


def split_of(wy: int) -> str:
    if wy in DEVELOPMENT_WY:
        return "development"
    if wy in HELDOUT_WY:
        return f"heldout_wy{wy}"
    if wy >= LIVE_FROM_WY:
        return "live"
    return "before_record"


def walk_forward_folds() -> list[tuple[tuple[int, ...], int]]:
    """(train water years, validation water year) for every validation year: development years only."""
    return [(tuple(sorted(y for y in DEVELOPMENT_WY if y < k)), k) for k in VALIDATION_WY]


def final_run_folds() -> dict[str, tuple[int, ...]]:
    """Training water years for each held-out score (A2), fixed before any model is trained."""
    return {"heldout_wy2022": tuple(range(FIRST_WY, 2022)),
            "heldout_wy2026": tuple(range(FIRST_WY, 2026)),  # includes WY2022, as a live system would have
            "live": tuple(range(FIRST_WY, 2026))}            # the WY2026 model


def rows(path: Path) -> Iterator[dict[str, str]]:
    with gzip.open(path, "rt", newline="") as fh:
        yield from csv.DictReader(fh)


def development_rows(path: Path, years: Iterable[int] | None = None) -> Iterator[dict[str, str]]:
    """Rows of development water years only (optionally a subset). A held-out or live year requested is an error;
    held-out and live rows in the file are skipped, and a row whose holdout flag contradicts its year raises."""
    want = set(years) if years is not None else set(DEVELOPMENT_WY)
    bad = want - DEVELOPMENT_WY
    if bad:
        raise HeldOutRowError(f"not development water years: {sorted(bad)}")
    for r in rows(path):
        wy = int(r["wy"])
        if r.get("holdout") == "True" and wy in DEVELOPMENT_WY:
            raise HeldOutRowError(f"row {r.get('issue_time') or r.get('issue_date')} is flagged holdout in WY{wy}")
        if wy in want:
            yield r


def check_training_rows(rs: Iterable[dict[str, str]]) -> int:
    """Guard for any training or calibration input: raise on the first held-out or live row."""
    n = 0
    for r in rs:
        wy = int(r["wy"])
        if wy not in DEVELOPMENT_WY:
            raise HeldOutRowError(f"WY{wy} ({split_of(wy)}) row in a training/calibration set")
        n += 1
    return n


def final_training_rows(path: Path, fold: str) -> Iterator[dict[str, str]]:
    """F5 (Stage 4): rows for training one final model of amendment 1 (A2), and only those. `fold` is a key of
    `final_run_folds()`: 'heldout_wy2022' allows WY2005-2021; 'heldout_wy2026' and 'live' allow WY2005-2025, which
    includes WY2022, as a live system would have had the 2021 flood by Dec 2025. WY2026 and WY >= 2027 are never
    allowed. Only the final-run command may call this; development code uses `development_rows()`."""
    folds = final_run_folds()
    if fold not in folds:
        raise HeldOutRowError(f"unknown final-run fold {fold!r}; expected one of {sorted(folds)}")
    allowed = set(folds[fold])
    assert not allowed & ({2026} | set(range(LIVE_FROM_WY, LIVE_FROM_WY + 100))), "A2 never trains on WY2026+"
    for r in rows(path):
        wy = int(r["wy"])
        if wy in allowed:
            yield r


def check_final_rows(rs: Iterable[dict[str, str]], fold: str) -> int:
    """Guard for a final-run fit: raise on the first row outside the fold's A2 training years."""
    allowed = set(final_run_folds()[fold])
    n = 0
    for r in rs:
        wy = int(r["wy"])
        if wy not in allowed:
            raise HeldOutRowError(f"WY{wy} row in the final-run fit for {fold}")
        n += 1
    return n
