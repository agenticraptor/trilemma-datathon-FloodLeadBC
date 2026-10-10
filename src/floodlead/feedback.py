"""Anonymous in-app feedback (Stage 3; D-03.6).

What is stored: the page (route), the station shown, yes/no, the free text **encrypted** (Fernet, key FEEDBACK_KEY
in .env), its length, and the app version. Never stored: names, emails, phone numbers, IP addresses. The text is never
logged, never returned by the API, never put in the ledger, snapshots or fixtures; `floodlead feedback list` on the VM
is the only reader. Rate limits are per client IP, in memory only.
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg
from cryptography.fernet import Fernet, InvalidToken

MAX_BODY_BYTES = 4096
MAX_TEXT_CHARS = 1000
MAX_ROUTE = 200
STATION_RE = re.compile(r"^[a-z]{2,8}:[A-Za-z0-9_.-]{1,40}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")  # control characters except tab and newline

# Per client IP: at most 5 per 10 minutes and 20 per day; and at most 300 per hour from everyone together.
LIMITS = ((5, 600.0), (20, 86400.0))
GLOBAL_PER_HOUR = 300


class FeedbackError(ValueError):
    pass


@dataclass(frozen=True)
class Item:
    route: str
    station_id: str | None
    useful: bool | None
    text: str
    app_version: str | None


def validate(body: Any) -> Item:
    if not isinstance(body, dict):
        raise FeedbackError("expected a JSON object")
    extra = set(body) - {"route", "station_id", "useful", "text", "app_version"}
    if extra:
        raise FeedbackError(f"unexpected fields: {sorted(extra)}")
    route = body.get("route") or "#/"
    if not isinstance(route, str) or len(route) > MAX_ROUTE:
        raise FeedbackError(f"route must be a string of at most {MAX_ROUTE} characters")
    sid = body.get("station_id")
    if sid is not None and (not isinstance(sid, str) or not STATION_RE.match(sid)):
        raise FeedbackError("station_id must look like 'eccc:08MH029' or be null")
    useful = body.get("useful")
    if useful is not None and not isinstance(useful, bool):
        raise FeedbackError("useful must be true, false or null")
    text = body.get("text") or ""
    if not isinstance(text, str):
        raise FeedbackError("text must be a string")
    text = _CTRL.sub("", text).strip()
    if len(text) > MAX_TEXT_CHARS:
        raise FeedbackError(f"text is longer than {MAX_TEXT_CHARS} characters")
    ver = body.get("app_version")
    if ver is not None and (not isinstance(ver, str) or not VERSION_RE.match(ver)):
        raise FeedbackError("app_version must be a short version label")
    if useful is None and not text:
        raise FeedbackError("give a yes/no or some text")
    return Item(_CTRL.sub("", route), sid, useful, text, ver)


def key_id(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:8]


def encrypt(key: str, text: str) -> bytes:
    return Fernet(key.encode()).encrypt(text.encode("utf-8"))


def decrypt(key: str, token: bytes) -> str:
    return Fernet(key.encode()).decrypt(bytes(token)).decode("utf-8")


def store(conn: psycopg.Connection, key: str, item: Item) -> int:
    if not key:
        raise RuntimeError("FEEDBACK_KEY is not set")
    enc = encrypt(key, item.text) if item.text else None
    row = conn.execute(
        "INSERT INTO feedback (route, station_id, useful, text_enc, text_chars, key_id, app_version)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING feedback_id",
        (item.route, item.station_id, item.useful, enc, len(item.text), key_id(key), item.app_version)).fetchone()
    return int(row[0])


def read_all(conn: psycopg.Connection, key: str, since: datetime | None = None) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT feedback_id, received_at, route, station_id, useful, text_enc, key_id, app_version FROM feedback"
        " WHERE %s::timestamptz IS NULL OR received_at >= %s ORDER BY feedback_id", (since, since)).fetchall()
    out = []
    for fid, at, route, sid, useful, enc, kid, ver in rows:
        if enc is None:
            text = ""
        else:
            try:
                text = decrypt(key, enc)
            except InvalidToken:
                text = f"<cannot decrypt: key {kid} is not the current key>"
        out.append({"id": fid, "received_at": at, "route": route, "station_id": sid, "useful": useful,
                    "text": text, "app_version": ver})
    return out


class Limiter:
    """Sliding-window limits per client IP plus one global hourly cap. Memory only; IPs are never stored."""

    def __init__(self) -> None:
        self.hits: dict[str, list[float]] = {}
        self.all: list[float] = []
        self.lock = threading.Lock()

    def allow(self, ip: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self.lock:
            self.all = [t for t in self.all if now - t < 3600]
            h = [t for t in self.hits.get(ip, []) if now - t < max(w for _, w in LIMITS)]
            if len(self.all) >= GLOBAL_PER_HOUR or any(sum(1 for t in h if now - t < w) >= n for n, w in LIMITS):
                self.hits[ip] = h
                return False
            h.append(now)
            self.hits[ip] = h
            self.all.append(now)
            if len(self.hits) > 50_000:
                self.hits.clear()
            return True
