"""NWIS IV re-fetch with a request margin (Stage 4 F1, D-04.2): NWIS answered a winter `startDT=...Z` one hour late,
so re-fetches ask from start - margin and keep only [start, end)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from floodlead import http
from floodlead.sources import usgs

FIX = Path(__file__).parent / "fixtures" / "nwis_iv_12211200_2021-11.json"


class _Run:
    items_fetched = 0


def test_margin_is_requested_and_rows_are_filtered(monkeypatch) -> None:  # noqa: ANN001
    seen: dict[str, str] = {}

    def fake_fetch(c, url, params=None, **kw):  # noqa: ANN001, ANN202
        seen.update(params or {})
        return http.Fetched(url=url, status=200, content=FIX.read_bytes(), last_modified=None,
                            fetched_at=datetime.now(UTC), elapsed_s=0.0)

    got: list = []

    def fake_process(conn, run, source, name, f, parse):  # noqa: ANN001, ANN202
        got.extend(parse(f))

    monkeypatch.setattr(http, "fetch", fake_fetch)
    monkeypatch.setattr(usgs.ingest, "process_payload", fake_process)
    # the fixture holds 2021-11-01 00:00/00:15Z and 2021-11-15 21:40/21:45Z; keep only the last two
    start, end = datetime(2021, 11, 15, 21, 0, tzinfo=UTC), datetime(2021, 11, 16, 0, 0, tzinfo=UTC)
    n = usgs.fetch_nwis_window(None, None, _Run(), "12211200", start, end, [], None,  # type: ignore[arg-type]
                               request_margin=timedelta(days=1))
    assert seen["startDT"] == "2021-11-14T21:00Z" and seen["endDT"] == "2021-11-16T00:00Z"
    assert n == len(got) == 4 and all(start <= r.ts < end for r in got)  # 2 times x (level, flow)
