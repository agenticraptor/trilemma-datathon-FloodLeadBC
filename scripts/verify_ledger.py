#!/usr/bin/env python3
"""Verify the FloodLead forecast ledger from outside the VM. Python standard library only.

Sources (see docs/ledger-spec.md):
  --source api     page through https://<host>/v1/ledger (default; needs --api)
  --source github  rebuild the chain from the published files on the `ledger` branch alone
                   (ledger/entries/YYYY/MM/DD/HH.jsonl.gz), without the VM
  --source files   a local directory holding the same *.jsonl.gz files (e.g. a clone of the ledger branch)

Checks: seq continuity from 1 (or from an anchored --from-seq), prev_hash links, sha256(prev_hash + "\\n" + canonical)
== entry_hash for every entry, seq/entry_type inside the canonical text, and every line of ledger/heads.txt
(`<anchored_at> <seq> <entry_hash>`) against the chain. Prints counts; exits 1 on any failure.

Examples:
  python3 scripts/verify_ledger.py --api https://34-130-109-216.sslip.io
  python3 scripts/verify_ledger.py --source github
  python3 scripts/verify_ledger.py --api https://34-130-109-216.sslip.io --from-seq 856
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import urllib.request
from collections.abc import Iterable, Iterator
from pathlib import Path

ZERO = "0" * 64
REPO = "agenticraptor/trilemma-datathon-FloodLeadBC"
BRANCH = "ledger"
UA = {"User-Agent": "floodlead-verify-ledger/1"}


class Fail(Exception):
    def __init__(self, seq: int | None, msg: str) -> None:
        super().__init__(f"seq {seq}: {msg}" if seq is not None else msg)
        self.seq = seq


def _get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def entry_hash(prev: str, canonical: str) -> str:
    return hashlib.sha256((prev + "\n" + canonical).encode("utf-8")).hexdigest()


def verify(entries: Iterable[dict], start_seq: int = 1, start_prev: str | None = None) -> dict:
    """Verify entries in order. With start_seq == 1 the first entry must be genesis with a zero prev_hash; otherwise
    start_prev (the trusted hash of entry start_seq - 1) may be None, in which case the first entry's own prev_hash
    is taken as given (its hash is still checked against an anchor by the caller)."""
    expect_seq, prev = start_seq, (ZERO if start_seq == 1 else start_prev)
    n, by_type, hashes = 0, {}, {}
    last = None
    for e in entries:
        seq = e["seq"]
        if seq != expect_seq:
            raise Fail(seq, f"expected seq {expect_seq} (missing, reordered or duplicated entry)")
        if prev is not None and e["prev_hash"] != prev:
            raise Fail(seq, "prev_hash does not link to the previous entry")
        if entry_hash(e["prev_hash"], e["canonical"]) != e["entry_hash"]:
            raise Fail(seq, "entry_hash != sha256(prev_hash + '\\n' + canonical): content was changed")
        body = json.loads(e["canonical"])
        if body.get("seq") != seq or body.get("entry_type") != e["entry_type"]:
            raise Fail(seq, "seq/entry_type differ from the canonical text")
        if seq == 1 and (e["entry_type"] != "genesis" or e["prev_hash"] != ZERO):
            raise Fail(seq, "entry 1 must be genesis with a zero prev_hash")
        by_type[e["entry_type"]] = by_type.get(e["entry_type"], 0) + 1
        hashes[seq] = e["entry_hash"]
        prev, expect_seq, last, n = e["entry_hash"], seq + 1, seq, n + 1
    if n == 0:
        raise Fail(None, "no entries")
    return {"entries": n, "first_seq": start_seq, "last_seq": last, "head_hash": prev, "by_type": by_type,
            "hashes": hashes}


def check_heads(lines: list[str], hashes: dict[int, str], first: int, last: int) -> dict:
    checked = skipped = 0
    for ln in lines:
        if not ln.strip():
            continue
        at, seq_s, h = ln.split()
        seq = int(seq_s)
        if first <= seq <= last:
            if hashes.get(seq) != h:
                raise Fail(seq, f"anchor {at} says {h}, chain has {hashes.get(seq)}")
            checked += 1
        else:
            skipped += 1
    return {"anchors_checked": checked, "anchors_outside_range": skipped}


def from_api(base: str, after: int) -> Iterator[dict]:
    while True:
        page = json.loads(_get(f"{base.rstrip('/')}/v1/ledger?after_seq={after}&limit=1000"))
        yield from page["entries"]
        if page.get("next_after_seq") is None:
            return
        after = page["next_after_seq"]


def _jsonl_gz(data: bytes) -> list[dict]:
    return [json.loads(x) for x in gzip.decompress(data).decode("utf-8").splitlines() if x.strip()]


def from_github(repo: str, branch: str) -> tuple[list[dict], list[str], int]:
    tree = json.loads(_get(f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"))
    paths = sorted(t["path"] for t in tree["tree"] if t["path"].startswith("ledger/entries/")
                   and t["path"].endswith(".jsonl.gz"))
    raw = f"https://raw.githubusercontent.com/{repo}/{branch}/"
    entries: list[dict] = []
    for p in paths:
        entries += _jsonl_gz(_get(raw + p))
    heads = _get(raw + "ledger/heads.txt").decode().splitlines()
    return sorted(entries, key=lambda e: e["seq"]), heads, len(paths)


def from_files(root: Path) -> tuple[list[dict], list[str], int]:
    files = sorted(root.rglob("*.jsonl.gz"))
    entries = [e for f in files for e in _jsonl_gz(f.read_bytes())]
    hp = next(root.rglob("heads.txt"), None)
    return sorted(entries, key=lambda e: e["seq"]), (hp.read_text().splitlines() if hp else []), len(files)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["api", "github", "files"], default="api")
    ap.add_argument("--api", help="https://<host> of the FloodLead API (for --source api)")
    ap.add_argument("--path", help="directory with *.jsonl.gz and heads.txt (for --source files)")
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--branch", default=BRANCH)
    ap.add_argument("--from-seq", type=int, default=1,
                    help="start at this seq; it must be an anchored entry (its hash is checked against heads.txt)")
    ap.add_argument("--no-heads", action="store_true", help="skip the heads.txt check")
    a = ap.parse_args(argv)
    try:
        heads: list[str] = []
        if a.source == "api":
            if not a.api:
                ap.error("--api is required for --source api")
            entries: Iterable[dict] = from_api(a.api, a.from_seq - 1)
            if not a.no_heads:
                heads = _get(f"https://raw.githubusercontent.com/{a.repo}/{a.branch}/ledger/heads.txt"
                             ).decode().splitlines()
            files = None
        else:
            all_e, heads, files = (from_github(a.repo, a.branch) if a.source == "github"
                                   else from_files(Path(a.path or ".")))
            entries = [e for e in all_e if e["seq"] >= a.from_seq]
        if a.from_seq > 1 and not a.no_heads:
            anchored = {int(ln.split()[1]): ln.split()[2] for ln in heads if ln.strip()}
            if a.from_seq not in anchored:
                raise Fail(a.from_seq, "--from-seq must be an anchored seq (listed in ledger/heads.txt)")
        res = verify(entries, start_seq=a.from_seq)
        if a.from_seq > 1 and not a.no_heads and res["hashes"][a.from_seq] != anchored[a.from_seq]:
            raise Fail(a.from_seq, "starting entry does not match its anchor")
        hc = {} if a.no_heads else check_heads(heads, res["hashes"], res["first_seq"], res["last_seq"])
    except Fail as e:
        print(f"FAIL {e}")
        return 1
    res.pop("hashes")
    print("OK", json.dumps({**res, **hc, "source": a.source, **({"files": files} if files is not None else {})}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
