"""F1: Datamart date rollover. `today/` and the new date's directory can 404 around 00:00 UTC; the 30-day
`daily/` directory only appears ~08:20Z. Mocked transports, no network."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from floodlead.sources import eccc
from tests.conftest import fixture_bytes

LISTING = fixture_bytes("eccc_listing_hourly.html")
NOW = datetime(2026, 10, 9, 0, 3, 50, tzinfo=UTC)  # the minute the Oct 8 run failed, one day later


def _client(ok_urls: set[str]) -> tuple[httpx.Client, list[str]]:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if str(request.url) in ok_urls:
            return httpx.Response(200, content=LISTING)
        return httpx.Response(404, content=b"Not Found")

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_candidates_are_dated_first() -> None:
    c = eccc.candidate_bases("hourly", NOW)
    assert c[0].endswith("/20261009/WXO-DD/hydrometric/csv/BC/hourly/")
    assert c[1].endswith("/20261008/WXO-DD/hydrometric/csv/BC/hourly/")
    assert c[2].endswith("/today/hydrometric/csv/BC/hourly/")


def test_new_date_404_falls_back_to_previous_date() -> None:
    prev = eccc.dated_base("hourly", datetime(2026, 10, 8, tzinfo=UTC).date())
    c, seen = _client({prev})
    base, files, tried = eccc.fetch_listing(c, "hourly", NOW)
    assert base == prev and len(files) == 6
    assert tried == [{"url": eccc.candidate_bases("hourly", NOW)[0], "status": 404}]
    assert len(seen) == 2  # a 404 is not retried


def test_daily_before_0820z_uses_previous_date() -> None:
    prev = eccc.dated_base("daily", datetime(2026, 10, 8, tzinfo=UTC).date())
    c, _ = _client({prev})
    base, _, tried = eccc.fetch_listing(c, "daily", datetime(2026, 10, 9, 5, 0, tzinfo=UTC))
    assert base == prev and tried[0]["status"] == 404


def test_today_alias_is_last_resort_and_all_404_raises() -> None:
    today = eccc.candidate_bases("hourly", NOW)[2]
    c, _ = _client({today})
    base, _, tried = eccc.fetch_listing(c, "hourly", NOW)
    assert base == today and [t["status"] for t in tried] == [404, 404]
    c2, _ = _client(set())
    with pytest.raises(RuntimeError, match="no ECCC hourly listing"):
        eccc.fetch_listing(c2, "hourly", NOW)


def test_current_date_ok_needs_one_request() -> None:
    cur = eccc.candidate_bases("hourly", NOW)[0]
    c, seen = _client({cur})
    base, _, tried = eccc.fetch_listing(c, "hourly", NOW)
    assert base == cur and tried == [] and len(seen) == 1
