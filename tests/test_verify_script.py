"""scripts/verify_ledger.py (standard library only): tamper detection on published-style files."""

from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path

import pytest

from floodlead import ledger

_spec = importlib.util.spec_from_file_location("verify_ledger", Path(__file__).parents[1] / "scripts/verify_ledger.py")
vl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vl)  # type: ignore[union-attr]


def _chain(n: int) -> list[dict]:
    out, prev = [], ledger.ZERO_HASH
    for seq in range(1, n + 1):
        t = "genesis" if seq == 1 else "forecast"
        c = ledger.canonical_json({"seq": seq, "entry_type": t, "created_at": "2026-10-08T20:00:00.000Z",
                                   "data": {"v": seq / 10}})
        h = ledger.entry_hash(prev, c)
        out.append({"seq": seq, "entry_type": t, "created_at": "2026-10-08T20:00:00.000Z", "canonical": c,
                    "prev_hash": prev, "entry_hash": h})
        prev = h
    return out


def _write(tmp: Path, entries: list[dict], heads: list[tuple[int, str]]) -> Path:
    d = tmp / "ledger" / "entries" / "2026" / "10" / "08"
    d.mkdir(parents=True)
    for i, part in enumerate((entries[:5], entries[5:])):
        (d / f"{20 + i}.jsonl.gz").write_bytes(gzip.compress("\n".join(json.dumps(e) for e in part).encode()))
    (tmp / "ledger" / "heads.txt").write_text("".join(f"2026-10-08T20:30:00Z {s} {h}\n" for s, h in heads))
    return tmp


def _run(path: Path, *extra: str) -> int:
    return vl.main(["--source", "files", "--path", str(path), *extra])


def test_clean_chain_verifies_with_anchors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    e = _chain(8)
    assert _run(_write(tmp_path, e, [(5, e[4]["entry_hash"]), (8, e[7]["entry_hash"])])) == 0
    assert '"anchors_checked": 2' in capsys.readouterr().out
    assert _run(tmp_path, "--from-seq", "5") == 0


def test_changed_byte_is_caught_at_its_seq(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    e = _chain(8)
    e[3]["canonical"] = e[3]["canonical"].replace('"v":0.4', '"v":0.5')
    assert _run(_write(tmp_path, e, [])) == 1
    assert "FAIL seq 4" in capsys.readouterr().out


def test_swapped_pair_and_deleted_entry_are_caught(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    e = _chain(8)
    # A swap with consistent seq numbers re-labelled still breaks the prev links.
    e[2], e[3] = {**e[3], "seq": 3}, {**e[2], "seq": 4}
    assert _run(_write(tmp_path / "a", e, [])) == 1
    assert "FAIL seq 3" in capsys.readouterr().out
    e = _chain(8)
    del e[5]
    assert _run(_write(tmp_path / "b", e, [])) == 1
    assert "FAIL seq 7" in capsys.readouterr().out


def test_rewritten_history_is_caught_by_the_anchor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A self-consistent rewritten chain (all hashes recomputed) still fails against the published anchor."""
    honest = _chain(8)
    forged = _chain(8)
    forged[6]["canonical"] = forged[6]["canonical"].replace('"v":0.7', '"v":0.9')
    prev = forged[5]["entry_hash"]
    for e in forged[6:]:
        e["prev_hash"] = prev
        e["entry_hash"] = ledger.entry_hash(prev, e["canonical"])
        prev = e["entry_hash"]
    assert _run(_write(tmp_path, forged, [(8, honest[7]["entry_hash"])])) == 1
    assert "anchor" in capsys.readouterr().out


def test_script_requires_genesis_with_zero_prev_hash(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    e = _chain(3)
    # Re-label entry 1 as a forecast and rehash the whole chain consistently: it must still fail.
    prev = ledger.ZERO_HASH
    for x in e:
        if x["seq"] == 1:
            x["entry_type"] = "forecast"
            x["canonical"] = x["canonical"].replace('"entry_type":"genesis"', '"entry_type":"forecast"')
        x["prev_hash"], x["entry_hash"] = prev, ledger.entry_hash(prev, x["canonical"])
        prev = x["entry_hash"]
    assert _run(_write(tmp_path, e, [])) == 1
    assert "FAIL seq 1" in capsys.readouterr().out
