"""Hourly anchors: publish the chain head and the new ledger entries to the `ledger` branch on GitHub.

One commit per anchor, made with the Git Data API (blobs -> tree -> commit -> fast-forward ref update), containing
- `ledger/entries/YYYY/MM/DD/HH.jsonl.gz`: every entry since the previous anchor, one JSON object per line with
  seq, entry_type, created_at, canonical, prev_hash and entry_hash exactly as stored (gzip, mtime 0);
- `ledger/heads.txt` with one appended line `<anchored_at> <seq> <entry_hash>`.
The job never touches `main` and never force-pushes; the token is LEDGER_GITHUB_TOKEN (fine-grained, this repository,
Contents read/write). Every attempt is recorded in `ledger_anchors`.
"""

from __future__ import annotations

import base64
import gzip
import io
import json
import os
from datetime import UTC, datetime
from typing import Any

import httpx
import psycopg
from psycopg_pool import ConnectionPool

from floodlead import ledger, log
from floodlead.config import USER_AGENT

L = log.get(__name__)

OWNER_REPO = "agenticraptor/trilemma-datathon-FloodLeadBC"
BRANCH = "ledger"
API = "https://api.github.com"
README = """# FloodLead ledger branch

This branch holds only the public FloodLead forecast ledger, written hourly by the anchor job:

- `ledger/heads.txt`: one line per anchor, `<anchored_at> <seq> <entry_hash>`.
- `ledger/entries/YYYY/MM/DD/HH.jsonl.gz`: the entries added since the previous anchor, one JSON object per line
  (seq, entry_type, created_at, canonical, prev_hash, entry_hash) exactly as stored.

Verify with `python3 scripts/verify_ledger.py --source github` (on `main`) or by the rules in `docs/ledger-spec.md`.
This branch is append-only by convention: commits only add lines and files, never rewrite them.
"""


class GitHub:
    def __init__(self, token: str) -> None:
        self.c = httpx.Client(base_url=API, timeout=60, headers={
            "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": USER_AGENT})

    def _req(self, method: str, path: str, **kw: Any) -> httpx.Response:
        r = self.c.request(method, f"/repos/{OWNER_REPO}{path}", **kw)
        if r.status_code >= 400 and r.status_code != 404:
            raise RuntimeError(f"GitHub {method} {path} -> {r.status_code}: {r.text[:300]}")
        return r

    def ref_sha(self) -> str | None:
        r = self._req("GET", f"/git/ref/heads/{BRANCH}")
        return None if r.status_code == 404 else r.json()["object"]["sha"]

    def blob(self, data: bytes) -> str:
        return self._req("POST", "/git/blobs", json={"content": base64.b64encode(data).decode(),
                                                      "encoding": "base64"}).json()["sha"]

    def tree(self, entries: list[dict[str, Any]], base: str | None) -> str:
        body: dict[str, Any] = {"tree": entries}
        if base:
            body["base_tree"] = base
        return self._req("POST", "/git/trees", json=body).json()["sha"]

    def commit(self, message: str, tree: str, parent: str | None) -> dict[str, Any]:
        return self._req("POST", "/git/commits", json={"message": message, "tree": tree,
                                                        "parents": [parent] if parent else []}).json()

    def commit_tree(self, sha: str) -> str:
        return self._req("GET", f"/git/commits/{sha}").json()["tree"]["sha"]

    def file(self, path: str, ref: str) -> bytes | None:
        r = self._req("GET", f"/contents/{path}", params={"ref": ref})
        if r.status_code == 404:
            return None
        j = r.json()
        if j.get("content"):
            return base64.b64decode(j["content"])
        return self.c.get(j["download_url"]).content  # > 1 MB files come without inline content

    def create_ref(self, sha: str) -> None:
        self._req("POST", "/git/refs", json={"ref": f"refs/heads/{BRANCH}", "sha": sha})

    def update_ref(self, sha: str) -> None:
        self._req("PATCH", f"/git/refs/heads/{BRANCH}", json={"sha": sha, "force": False})


def entries_jsonl_gz(rows: list[tuple[int, str, datetime, str, str, str]]) -> bytes:
    lines = [json.dumps({"seq": s, "entry_type": t, "created_at": ledger.ts(c, ms=True), "canonical": can,
                         "prev_hash": p, "entry_hash": h}, ensure_ascii=False, separators=(",", ":"))
             for s, t, c, can, p, h in rows]
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0) as gz:
        gz.write(("\n".join(lines) + "\n").encode("utf-8"))
    return buf.getvalue()


def _record(conn: psycopg.Connection, seq: int, h: str, at: datetime, status: str, sha: str | None = None,
            url: str | None = None, path: str | None = None, nbytes: int | None = None, err: str | None = None) -> None:
    conn.execute("INSERT INTO ledger_anchors (seq, entry_hash, anchored_at, commit_sha, commit_url, entries_path,"
                 " entries_bytes, status, error_text) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                 (seq, h, at, sha, url, path, nbytes, status, err))


def run(pool: ConnectionPool, token: str | None = None) -> dict[str, Any]:
    token = token or os.environ.get("LEDGER_GITHUB_TOKEN", "")
    if not token:
        L.warning("anchor pending: LEDGER_GITHUB_TOKEN is not set")
        return {"status": "pending"}
    now = datetime.now(UTC)
    with pool.connection() as conn:
        conn.autocommit = True
        head = ledger.head(conn)
        if head is None:
            return {"status": "empty"}
        seq, h = head
        last = conn.execute("SELECT max(seq) FROM ledger_anchors WHERE status = 'ok'").fetchone()[0] or 0
        if last >= seq:
            return {"status": "up-to-date", "seq": seq}
        rows = conn.execute("SELECT seq, entry_type, created_at, canonical, prev_hash, entry_hash FROM ledger_entries"
                            " WHERE seq > %s AND seq <= %s ORDER BY seq", (last, seq)).fetchall()
        gh = GitHub(token)
        try:
            parent = gh.ref_sha()
            base_tree = gh.commit_tree(parent) if parent else None
            heads = (gh.file("ledger/heads.txt", BRANCH) or b"") if parent else b""
            day = f"ledger/entries/{now:%Y/%m/%d}"
            path = f"{day}/{now:%H}.jsonl.gz"
            if parent and gh.file(path, BRANCH) is not None:  # a second anchor in the same hour
                path = f"{day}/{now:%H}.{rows[0][0]}.jsonl.gz"
            data = entries_jsonl_gz(rows)
            line = f"{ledger.ts(now)} {seq} {h}\n".encode()
            tree_entries = [
                {"path": path, "mode": "100644", "type": "blob", "sha": gh.blob(data)},
                {"path": "ledger/heads.txt", "mode": "100644", "type": "blob", "sha": gh.blob(heads + line)},
            ]
            if not parent:
                tree_entries.append({"path": "README.md", "mode": "100644", "type": "blob",
                                     "sha": gh.blob(README.encode())})
            tree = gh.tree(tree_entries, base_tree)
            msg = (f"ledger: anchor seq {seq} ({h[:12]}), entries {rows[0][0]}-{rows[-1][0]}\n\n"
                   f"{len(rows)} entries, {len(data)} bytes gzip. Written by the FloodLead anchor job.")
            c = gh.commit(msg, tree, parent)
            if parent:
                gh.update_ref(c["sha"])
            else:
                gh.create_ref(c["sha"])
            url = f"https://github.com/{OWNER_REPO}/commit/{c['sha']}"
            _record(conn, seq, h, now, "ok", c["sha"], url, path, len(data))
            L.info("anchored", **log.kv(seq=seq, entries=len(rows), bytes=len(data), commit=c["sha"], path=path))
            return {"status": "ok", "seq": seq, "entries": len(rows), "bytes": len(data), "commit_url": url,
                    "path": path}
        except Exception as e:  # noqa: BLE001 - recorded, retried next hour
            _record(conn, seq, h, now, "error", err=repr(e)[:500])
            L.exception("anchor failed", **log.kv(seq=seq))
            return {"status": "error", "error": repr(e)}
