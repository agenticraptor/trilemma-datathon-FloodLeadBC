"""A small in-process scheduler: each job runs on a wall-clock-aligned interval in its own thread.

A job that is still running when it comes due again is skipped (never stacked). Failures are
logged and recorded by the job's own ingest_runs row; the loop itself never dies on a job error.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from floodlead import log

L = log.get(__name__)


@dataclass
class Job:
    name: str
    every_s: int
    offset_s: int  # seconds after each aligned boundary, e.g. ECCC at :03, :13, ... (files land at :31)
    fn: Callable[[], object]
    run_at_start: bool = True
    _thread: threading.Thread | None = field(default=None, repr=False)
    _next: float = 0.0

    def next_due(self, now: float) -> float:
        base = now - (now % self.every_s) + self.offset_s
        return base if base > now else base + self.every_s

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def launch(self) -> None:
        def target() -> None:
            t0 = time.monotonic()
            try:
                self.fn()
            except Exception:  # noqa: BLE001 - keep the scheduler alive
                L.exception("job failed", **log.kv(job=self.name))
            finally:
                L.info("job done", **log.kv(job=self.name, seconds=round(time.monotonic() - t0, 2)))

        self._thread = threading.Thread(target=target, name=self.name, daemon=True)
        self._thread.start()


def run_forever(jobs: list[Job], stop: threading.Event | None = None) -> None:
    stop = stop or threading.Event()
    now = time.time()
    for j in jobs:
        j._next = now if j.run_at_start else j.next_due(now)
    L.info("scheduler started", **log.kv(jobs=[(j.name, j.every_s, j.offset_s) for j in jobs]))
    while not stop.is_set():
        now = time.time()
        for j in jobs:
            if now >= j._next:
                if j.running():
                    L.warning("job still running; skipping this slot", **log.kv(job=j.name))
                else:
                    j.launch()
                j._next = j.next_due(now)
        stop.wait(2.0)
