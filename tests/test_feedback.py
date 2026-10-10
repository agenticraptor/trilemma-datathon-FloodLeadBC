"""Feedback (Stage 3): rate limit, size limit, no HTML, encryption round trip, never logged or echoed."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import psycopg
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from floodlead import feedback
from tests.test_api import client  # noqa: F401 - the API client fixture on the disposable database

SECRET = "my field floods near the 0 Avenue culvert <b>bold</b><script>x()</script>"


def test_validate_rules() -> None:
    ok = feedback.validate({"route": "#/", "station_id": "eccc:08MH029", "useful": True, "text": " hi\x07 ",
                            "app_version": "stage-03"})
    assert ok.text == "hi" and ok.station_id == "eccc:08MH029"
    for bad in ({"useful": None, "text": ""}, {"useful": "yes"}, {"text": "x" * 1001}, {"station_id": "<x>"},
                {"useful": True, "name": "Ann"}, {"useful": True, "email": "a@b.c"}, [1, 2],
                {"useful": True, "app_version": "<script>"}):
        with pytest.raises(feedback.FeedbackError):
            feedback.validate(bad)
    assert feedback.validate({"text": "x" * 1000}).text == "x" * 1000


def test_encryption_round_trip_and_wrong_key() -> None:
    k1, k2 = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    tok = feedback.encrypt(k1, SECRET)
    assert SECRET.encode() not in tok
    assert feedback.decrypt(k1, tok) == SECRET
    with pytest.raises(Exception):  # noqa: B017 - InvalidToken
        feedback.decrypt(k2, tok)


def test_limiter_per_ip_and_global() -> None:
    lim = feedback.Limiter()
    assert all(lim.allow("1.2.3.4", now=100.0 + i) for i in range(5))
    assert not lim.allow("1.2.3.4", now=106.0)  # 6th within 10 minutes
    assert lim.allow("5.6.7.8", now=106.0)  # another client is unaffected
    assert lim.allow("1.2.3.4", now=100.0 + 601)  # the 10-minute window has passed
    g = feedback.Limiter()
    assert all(g.allow(f"10.0.{i // 250}.{i % 250}", now=1.0) for i in range(feedback.GLOBAL_PER_HOUR))
    assert not g.allow("9.9.9.9", now=2.0)


@pytest.fixture
def fclient(client: TestClient, conn: psycopg.Connection,  # noqa: F811 - `client` is the imported fixture
            monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    from floodlead import api
    from floodlead.config import get_settings

    monkeypatch.setattr(get_settings(), "feedback_key", Fernet.generate_key().decode())
    monkeypatch.setattr(api, "_feedback_limiter", feedback.Limiter())
    monkeypatch.setattr(api, "_PRIVATE", api._PRIVATE + ("testclient",))  # the test client stands in for Caddy
    yield client
    conn.execute("SET session_replication_role = replica")  # the append-only guard is a trigger
    conn.execute("TRUNCATE feedback")
    conn.execute("SET session_replication_role = DEFAULT")


def test_post_feedback_end_to_end(fclient: TestClient, conn: psycopg.Connection, caplog: pytest.LogCaptureFixture,
                                  capsys: pytest.CaptureFixture[str]) -> None:
    from floodlead.config import get_settings

    caplog.set_level(logging.DEBUG)
    body = {"route": "#/station/eccc:08MH029", "station_id": "eccc:08MH029", "useful": False, "text": SECRET,
            "app_version": "stage-03"}
    r = fclient.post("/v1/feedback", json=body, headers={"X-Forwarded-For": "203.0.113.7"})
    assert r.status_code == 202 and r.json()["status"] == "received"
    assert "0 Avenue" not in r.text  # never echoed
    row = conn.execute("SELECT route, station_id, useful, text_enc, text_chars FROM feedback").fetchone()
    assert row[:3] == ("#/station/eccc:08MH029", "eccc:08MH029", False) and row[4] == len(SECRET)
    assert b"0 Avenue" not in bytes(row[3])  # encrypted at rest
    items = feedback.read_all(conn, get_settings().feedback_key)
    assert items[-1]["text"] == SECRET  # decrypted only by the reader
    # never in logs (application logs or anything printed)
    out = capsys.readouterr()
    assert "0 Avenue" not in caplog.text and "0 Avenue" not in out.out and "0 Avenue" not in out.err
    # health shows counts only
    h = fclient.get("/v1/health").json()["feedback"]
    assert h["total"] == 1 and h["no"] == 1 and "text" not in h
    # append-only
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("UPDATE feedback SET useful = true")
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("DELETE FROM feedback")


def test_post_feedback_limits(fclient: TestClient) -> None:
    assert fclient.post("/v1/feedback", content=b"{" + b" " * 5000 + b"}",
                        headers={"Content-Type": "application/json"}).status_code == 413
    assert fclient.post("/v1/feedback", json={"text": "x" * 1001}).status_code == 400
    assert fclient.post("/v1/feedback", content=b"not json").status_code == 400
    h = {"X-Forwarded-For": "198.51.100.9"}
    codes = [fclient.post("/v1/feedback", json={"useful": True}, headers=h).status_code for _ in range(6)]
    assert codes == [202] * 5 + [429]
    # a different client behind the same proxy is not blocked
    assert fclient.post("/v1/feedback", json={"useful": True},
                        headers={"X-Forwarded-For": "198.51.100.10"}).status_code == 202
