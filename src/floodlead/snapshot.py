"""`floodlead export-demo`: record real API responses for the app's snapshot mode.

The app fetches canonical same-origin paths; when the API cannot be reached it loads
`data/snapshot/<slug>.json`, where slug = path without the leading "/" and every run of characters outside
[A-Za-z0-9._-] replaced by "_" (the same rule as `slug()` in web/app.js). Each file is the API response plus
`snapshot_at`. Responses are produced in-process by the real API code against the real database."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from floodlead import log
from floodlead.config import ATTRIBUTION

L = log.get(__name__)

DEMO_STATIONS = ["usgs:12210700", "usgs:12211195", "usgs:12211200", "usgs:12213100", "eccc:08MH001", "eccc:08MH029"]


def slug(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", re.sub(r"^/", "", path))


def canonical_paths(replay_events: list[str]) -> list[str]:
    paths = ["/v1/health", "/v1/stations?limit=2000", "/v1/official-forecasts/NRKW1", "/v1/replay/overflow",
             "/v1/ledger/head", "/v1/gauges/fraser-valley", "/v1/track-record"]
    for sid in DEMO_STATIONS:
        paths += [f"/v1/stations/{sid}", f"/v1/stations/{sid}/observations?param=level&days=7",
                  f"/v1/stations/{sid}/forecast"]
    paths += [f"/v1/replay/overflow/{e}/series" for e in replay_events]
    return paths


def export(out_dir: str) -> list[str]:
    from fastapi.testclient import TestClient

    from floodlead.api import app

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    snapshot_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with TestClient(app) as c:
        events = [e["event_id"] for e in c.get("/v1/replay/overflow").json().get("events", [])]
        for path in canonical_paths(events):
            r = c.get(path)
            if r.status_code != 200:
                L.warning("snapshot path skipped", **log.kv(path=path, status=r.status_code))
                continue
            body = r.json()
            body["snapshot_at"] = snapshot_at
            f = out / f"{slug(path)}.json"
            f.write_text(json.dumps(body, separators=(",", ":"), default=str))
            written.append(f.name)
    (out / "index.json").write_text(json.dumps({"snapshot_at": snapshot_at, "files": sorted(written),
                                                "attribution": ATTRIBUTION}, indent=1))
    L.info("snapshot written", **log.kv(files=len(written), out=str(out)))
    return written
