"""Static checks for the web app in web/ (no database, no network).

- index.html loads only same-origin relative assets and has nothing that a strict
  Content-Security-Policy (default-src 'self') would block: no inline <script> bodies,
  no <style> blocks, no style= or on*= attributes.
- The vendored chart library ships with its licence.
- The snapshot file-name rule in app.js (between the BEGIN/END snapshotSlug markers) matches
  the documented rule, so `floodlead export-demo` writes the files the app looks for.
- Any committed snapshot files parse and carry snapshot_at and attribution.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "web"
INDEX = WEB / "index.html"
APP_JS = WEB / "app.js"
SNAPSHOT_DIR = WEB / "data" / "snapshot"


def documented_slug(path: str) -> str:
    """The rule from web/README.md: drop one leading '/', then replace every run of characters
    outside [A-Za-z0-9._-] with a single '_'."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", re.sub(r"^/", "", path))


SLUG_CASES = {
    "/v1/health": "v1_health",
    "/v1/stations?limit=2000": "v1_stations_limit_2000",
    "/v1/stations/usgs:12210700": "v1_stations_usgs_12210700",
    "/v1/stations/usgs:12210700/observations?param=level&days=7": (
        "v1_stations_usgs_12210700_observations_param_level_days_7"
    ),
    "/v1/stations/eccc:08MH024/observations?param=level&days=7": (
        "v1_stations_eccc_08MH024_observations_param_level_days_7"
    ),
    "/v1/official-forecasts/NRKW1": "v1_official-forecasts_NRKW1",
    "/v1/stations/usgs:12210700/forecast": "v1_stations_usgs_12210700_forecast",
    "/v1/replay/overflow": "v1_replay_overflow",
    "/v1/replay/overflow/2021-11-14/series": "v1_replay_overflow_2021-11-14_series",
    "/v1/ledger/head": "v1_ledger_head",
    "/v1/gauges/fraser-valley": "v1_gauges_fraser-valley",
    "/v1/track-record": "v1_track-record",
    "/v1/official-scorecard": "v1_official-scorecard",
}


class _TagCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.script_bodies: list[str] = []
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))
        if tag == "script":
            self._in_script = True
            self.script_bodies.append("")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script = False

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self.script_bodies[-1] += data


@pytest.fixture(scope="module")
def index_tags() -> _TagCollector:
    assert INDEX.is_file(), "web/index.html is missing"
    parser = _TagCollector()
    parser.feed(INDEX.read_text(encoding="utf-8"))
    return parser


def test_index_assets_are_same_origin_and_relative(index_tags: _TagCollector) -> None:
    refs = []
    for tag, attrs in index_tags.tags:
        if tag == "script" and attrs.get("src"):
            refs.append(attrs["src"])
        if tag == "link" and attrs.get("href"):
            refs.append(attrs["href"])
    assert refs, "expected script/link tags"
    for ref in refs:
        assert ref is not None
        assert not re.match(r"^(https?:)?//", ref, re.IGNORECASE), f"third-party or absolute asset: {ref}"
        assert not ref.lower().startswith("data:"), f"data: URI asset (blocked by CSP): {ref}"
        assert (WEB / ref).is_file(), f"referenced asset does not exist: {ref}"


def test_index_has_nothing_csp_would_block(index_tags: _TagCollector) -> None:
    raw = INDEX.read_text(encoding="utf-8")
    assert "<style" not in raw.lower(), "inline <style> block"
    for tag, attrs in index_tags.tags:
        assert tag != "style", "inline <style> block"
        for name in attrs:
            assert name.lower() != "style", f"inline style= attribute on <{tag}>"
            assert not name.lower().startswith("on"), f"inline event handler {name}= on <{tag}>"
        if tag == "a":
            href = (attrs.get("href") or "").strip().lower()
            assert not href.startswith("javascript:"), "javascript: URL"
    for body in index_tags.script_bodies:
        assert body.strip() == "", "inline <script> body"


def test_app_js_and_css_are_csp_safe() -> None:
    js = APP_JS.read_text(encoding="utf-8")
    assert not re.search(r"\beval\(", js), "eval() is blocked by CSP"
    assert "new Function" not in js, "new Function() is blocked by CSP"
    assert "innerHTML" not in js, "build DOM with textContent, not innerHTML"
    assert "setAttribute('style'" not in js and 'setAttribute("style"' not in js
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert not re.search(r"url\(\s*['\"]?(https?:)?//", css, re.IGNORECASE), "external url() in CSS"
    assert "@import" not in css, "@import in CSS"


def test_vendored_uplot_with_licence() -> None:
    vendor = WEB / "vendor" / "uplot"
    assert (vendor / "LICENSE").is_file()
    assert "MIT" in (vendor / "LICENSE").read_text(encoding="utf-8")
    assert (vendor / "uPlot.iife.min.js").is_file()
    assert (vendor / "uPlot.min.css").is_file()
    assert (vendor / "README.md").is_file()


def _slug_from_app_js() -> list[tuple[str, int, str]]:
    js = APP_JS.read_text(encoding="utf-8")
    m = re.search(r"// BEGIN snapshotSlug(.*?)// END snapshotSlug", js, re.DOTALL)
    assert m, "snapshotSlug markers not found in app.js"
    steps = re.findall(r"\.replace\(/(.+?)/([a-z]*),\s*'([^']*)'\)", m.group(1))
    assert len(steps) == 2, f"expected two replace() steps, found {steps}"
    return [(pattern, 0 if "g" in flags else 1, repl) for pattern, flags, repl in steps]


def _apply_js_slug(path: str) -> str:
    out = path
    for pattern, count, repl in _slug_from_app_js():
        out = re.sub(pattern, repl, out, count=count)
    return out


@pytest.mark.parametrize(("path", "expected"), sorted(SLUG_CASES.items()))
def test_snapshot_slug_rule(path: str, expected: str) -> None:
    assert documented_slug(path) == expected
    assert _apply_js_slug(path) == expected


def test_app_uses_canonical_paths() -> None:
    js = APP_JS.read_text(encoding="utf-8")
    for fragment in (
        "/observations?param=level&days=7",
        "'/v1/stations?limit=2000'",
        "'/v1/replay/overflow'",
        "'/v1/ledger/head'",
        "'/v1/health'",
        "/forecast`",
        "/v1/official-forecasts/",
    ):
        assert fragment in js, f"canonical path fragment missing from app.js: {fragment}"


def test_snapshot_files_if_present() -> None:
    if not SNAPSHOT_DIR.is_dir():
        pytest.skip("no web/data/snapshot directory")
    files = sorted(SNAPSHOT_DIR.glob("*.json"))
    if not files:
        pytest.skip("no snapshot files yet (floodlead export-demo writes them)")
    for f in files:
        assert re.fullmatch(r"[A-Za-z0-9._-]+\.json", f.name), f"not a valid slug file name: {f.name}"
        body = json.loads(f.read_text(encoding="utf-8"))
        assert isinstance(body, dict), f"{f.name}: top level must be an object"
        assert body.get("snapshot_at"), f"{f.name}: missing snapshot_at"
        assert isinstance(body.get("attribution"), list) and body["attribution"], f"{f.name}: missing attribution"
