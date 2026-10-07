"""HTTP fetching with a descriptive User-Agent, timeouts, retries and conditional GETs."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import format_datetime, parsedate_to_datetime

import httpx

from floodlead import log
from floodlead.config import USER_AGENT, get_settings

L = log.get(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}


class RateLimited(Exception):
    """HTTP 429 with a long Retry-After: give up now instead of spending more of the quota."""

    def __init__(self, url: str, retry_after_s: int) -> None:
        super().__init__(f"HTTP 429 rate limited; retry after {retry_after_s} s ({url})")
        self.retry_after_s = retry_after_s


@dataclass
class Fetched:
    url: str
    status: int
    content: bytes
    last_modified: datetime | None
    fetched_at: datetime
    elapsed_s: float

    @property
    def not_modified(self) -> bool:
        return self.status == 304


def client() -> httpx.Client:
    s = get_settings()
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
        timeout=httpx.Timeout(s.http_timeout_s, connect=15.0),
        follow_redirects=True,
        limits=httpx.Limits(max_connections=s.http_max_parallel + 2),
    )


def http_date(dt: datetime) -> str:
    return format_datetime(dt.astimezone(UTC), usegmt=True)


def parse_http_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(UTC)
    except (TypeError, ValueError):
        return None


def fetch(
    c: httpx.Client,
    url: str,
    *,
    params: dict[str, str] | None = None,
    if_modified_since: datetime | None = None,
    attempts: int = 4,
    headers: dict[str, str] | None = None,
) -> Fetched:
    """GET with retries on timeouts, connection errors, 429 and 5xx (exponential backoff + jitter).
    A 429 asking to wait more than 60 s raises RateLimited immediately."""
    headers = dict(headers or {})
    if if_modified_since is not None:
        headers["If-Modified-Since"] = http_date(if_modified_since)
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        t0 = time.monotonic()
        try:
            r = c.get(url, params=params, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last_exc = e
            L.warning("http error", **log.kv(url=url, attempt=attempt, error=repr(e)))
        else:
            if r.status_code not in RETRY_STATUS:
                if r.status_code >= 400 and r.status_code != 304:
                    r.raise_for_status()
                return Fetched(
                    url=str(r.url),
                    status=r.status_code,
                    content=r.content if r.status_code != 304 else b"",
                    last_modified=parse_http_date(r.headers.get("Last-Modified")),
                    fetched_at=datetime.now(UTC),
                    elapsed_s=time.monotonic() - t0,
                )
            last_exc = httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
            L.warning("http retryable status", **log.kv(url=url, attempt=attempt, status=r.status_code))
            retry_after = r.headers.get("Retry-After")
            if r.status_code == 429 and retry_after and retry_after.isdigit() and int(retry_after) > 60:
                raise RateLimited(url, int(retry_after))
            if retry_after and retry_after.isdigit() and attempt < attempts:
                time.sleep(min(int(retry_after), 120))
                continue
        if attempt < attempts:
            time.sleep(min(2 ** attempt, 30) + random.uniform(0, 1))
    assert last_exc is not None
    raise last_exc
