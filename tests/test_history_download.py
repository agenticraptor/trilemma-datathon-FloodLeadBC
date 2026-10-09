"""History downloader: an HTTP 200 with an invalid body is an error to retry, not a finished task (Open-Meteo returned
'Unexpected error while streaming data: timeoutReached' with status 200 for 4 of 184 requests on Oct 9)."""

from datetime import UTC, datetime

from floodlead import db, http
from floodlead.config import get_settings
from floodlead.history import cli as hcli
from floodlead.history import download


def test_invalid_body_is_retried(conn, test_dsn: str, tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("ARCHIVE_DIR", str(tmp_path))
    get_settings.cache_clear()
    bodies = iter([b"Unexpected error while streaming data: timeoutReached", b'{"hourly": {"time": []}}'])

    def fake_fetch(c, url, params=None, **kw):  # noqa: ANN001, ANN202
        return http.Fetched(url=url, status=200, content=next(bodies), last_modified=None,
                            fetched_at=datetime.now(UTC), elapsed_s=0.01)

    monkeypatch.setattr(http, "fetch", fake_fetch)
    pool = db.pool(test_dsn, max_size=1)
    task = download.Task("p/2020", "https://example.test/archive")
    try:
        r1 = download.run(pool, "openmeteo-archive", [task], pace_s=0, is_valid=hcli._json_ok)
        st1 = conn.execute("SELECT status, error FROM history_downloads WHERE key = 'p/2020'").fetchone()
        r2 = download.run(pool, "openmeteo-archive", [task], pace_s=0, is_valid=hcli._json_ok)
        st2 = conn.execute("SELECT status FROM history_downloads WHERE key = 'p/2020'").fetchone()
    finally:
        pool.close()
        get_settings.cache_clear()
    assert r1.errors == 1 and st1[0] == "error" and "timeoutReached" in st1[1]
    assert r2.done == 1 and r2.skipped == 0 and st2[0] == "ok"  # retried on the next run, not skipped
