"""Idempotent, set-based writes: observations (with revision capture), stations, runs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from floodlead import log

L = log.get(__name__)


@dataclass(frozen=True)
class Obs:
    station_id: str
    ts: datetime  # timezone-aware
    param: str  # 'level' | 'flow'
    value: float | None  # SI, None for sentinels
    raw_value: float | None
    raw_unit: str
    quality: dict[str, Any]
    is_sentinel: bool
    published_at: datetime | None


@dataclass
class UpsertResult:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    stale: int = 0

    def add(self, other: UpsertResult) -> None:
        self.inserted += other.inserted
        self.updated += other.updated
        self.unchanged += other.unchanged
        self.stale += other.stale


_STAGE_DDL = """
CREATE TEMP TABLE IF NOT EXISTS stg_obs (
    station_id text, ts timestamptz, param text, value double precision,
    raw_value double precision, raw_unit text, quality jsonb, is_sentinel boolean,
    published_at timestamptz
) ON COMMIT DELETE ROWS
"""

# A stored row "differs" from the incoming one when the published value, unit, quality fields or
# sentinel flag differ. The out-of-order guard: an incoming version published *before* the stored
# version is stale and is ignored (counted, not applied), so an older 30-day file can never
# "revise" a value back after a newer hourly file has updated it.
_DIFFERS = """(o.raw_value IS DISTINCT FROM s.raw_value OR o.raw_unit IS DISTINCT FROM s.raw_unit
     OR o.quality IS DISTINCT FROM s.quality OR o.is_sentinel IS DISTINCT FROM s.is_sentinel)"""
_NOT_STALE = "(o.published_at IS NULL OR s.published_at IS NULL OR s.published_at >= o.published_at)"


def upsert_observations(
    conn: psycopg.Connection,
    rows: list[Obs],
    raw_object_id: int | None,
    now: datetime | None = None,
) -> UpsertResult:
    """Insert new rows, revise changed rows (appending to observation_revisions), and bump
    last_seen_at on unchanged rows. Must be called inside a transaction."""
    res = UpsertResult()
    if not rows:
        return res
    now = now or datetime.now(UTC)
    # Deduplicate within the batch (keep the last occurrence of each key).
    dedup: dict[tuple[str, datetime, str], Obs] = {}
    for r in rows:
        dedup[(r.station_id, r.ts, r.param)] = r
    batch = list(dedup.values())
    tmin = min(r.ts for r in batch)
    tmax = max(r.ts for r in batch)
    stations = sorted({r.station_id for r in batch})

    # Serialise writers per station (live ingest and backfills can overlap).
    for sid in stations:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (sid,))

    conn.execute(_STAGE_DDL)
    with conn.cursor().copy(
        "COPY stg_obs (station_id, ts, param, value, raw_value, raw_unit, quality, is_sentinel, published_at)"
        " FROM STDIN"
    ) as cp:
        for r in batch:
            cp.write_row((r.station_id, r.ts, r.param, r.value, r.raw_value, r.raw_unit,
                          json.dumps(r.quality, sort_keys=True), r.is_sentinel, r.published_at))

    # Literal time bounds let TimescaleDB exclude chunks at plan time, and the literal station list
    # makes the planner range-scan the primary key instead of hash-joining whole chunks (measured:
    # 5.6 s -> milliseconds for a 30-day file, see D-01.13).
    join = (
        "o.station_id = s.station_id AND o.ts = s.ts AND o.param = s.param"
        " AND o.ts BETWEEN %(t0)s AND %(t1)s AND o.station_id = ANY(%(sids)s)"
    )
    p = {"t0": tmin, "t1": tmax, "now": now, "rid": raw_object_id, "sids": stations}

    conn.execute(
        f"""
        INSERT INTO observation_revisions (station_id, ts, param, old_value, new_value, old_raw_value,
            new_raw_value, old_quality, new_quality, old_is_sentinel, new_is_sentinel,
            old_raw_object_id, new_raw_object_id, revised_at)
        SELECT o.station_id, o.ts, o.param, o.value, s.value, o.raw_value, s.raw_value, o.quality,
               s.quality, o.is_sentinel, s.is_sentinel, o.raw_object_id, %(rid)s, %(now)s
        FROM stg_obs s JOIN observations o ON {join}
        WHERE {_DIFFERS} AND {_NOT_STALE}
        """,
        p,
    )
    # Order matters: classify against the pre-update state (unchanged, stale) before revising.
    cur = conn.execute(
        f"""
        UPDATE observations o SET last_seen_at = %(now)s,
               published_at = GREATEST(o.published_at, s.published_at)
        FROM stg_obs s WHERE {join} AND NOT {_DIFFERS}
        """,
        p,
    )
    res.unchanged = cur.rowcount
    cur = conn.execute(
        f"SELECT count(*) FROM stg_obs s JOIN observations o ON {join} WHERE {_DIFFERS} AND NOT {_NOT_STALE}",
        p,
    )
    res.stale = cur.fetchone()[0]  # type: ignore[index]
    cur = conn.execute(
        f"""
        UPDATE observations o SET value = s.value, raw_value = s.raw_value, raw_unit = s.raw_unit,
               quality = s.quality, is_sentinel = s.is_sentinel, published_at = s.published_at,
               last_seen_at = %(now)s, revised_at = %(now)s, revision_count = o.revision_count + 1,
               raw_object_id = %(rid)s
        FROM stg_obs s WHERE {join} AND {_DIFFERS} AND {_NOT_STALE}
        """,
        p,
    )
    res.updated = cur.rowcount
    cur = conn.execute(
        """
        INSERT INTO observations (station_id, ts, param, value, raw_value, raw_unit, quality, is_sentinel,
                                  published_at, first_seen_at, last_seen_at, raw_object_id)
        SELECT station_id, ts, param, value, raw_value, raw_unit, quality, is_sentinel, published_at,
               %(now)s, %(now)s, %(rid)s
        FROM stg_obs
        ON CONFLICT (station_id, ts, param) DO NOTHING
        """,
        p,
    )
    res.inserted = cur.rowcount
    conn.execute("TRUNCATE stg_obs")
    return res


def ensure_stations(conn: psycopg.Connection, stations: list[dict[str, Any]]) -> None:
    """Create minimal station rows for ids seen in data but not yet in metadata."""
    for s in stations:
        known = conn.execute("SELECT params FROM stations WHERE station_id = %s", (s["station_id"],)).fetchone()
        if known is not None:
            if not set(s.get("params", [])) <= set(known[0] or []):
                conn.execute(
                    "UPDATE stations SET params = (SELECT ARRAY(SELECT DISTINCT unnest(params || %s::text[])"
                    " ORDER BY 1)) WHERE station_id = %s",
                    (s.get("params", []), s["station_id"]),
                )
            continue
        conn.execute(
            """
            INSERT INTO stations (station_id, source, native_id, name, region, params)
            VALUES (%(station_id)s, %(source)s, %(native_id)s, %(name)s, %(region)s, %(params)s)
            ON CONFLICT (station_id) DO NOTHING
            """,
            {"name": None, "region": None, **s},
        )


def upsert_station_meta(conn: psycopg.Connection, s: dict[str, Any]) -> None:
    """Full metadata upsert. `params` are merged, never removed."""
    conn.execute(
        """
        INSERT INTO stations (station_id, source, native_id, name, lat, lon, region, drainage_area_km2,
                              params, official_thresholds, links, meta, updated_at)
        VALUES (%(station_id)s, %(source)s, %(native_id)s, %(name)s, %(lat)s, %(lon)s, %(region)s,
                %(drainage_area_km2)s, %(params)s, %(official_thresholds)s, %(links)s, %(meta)s, now())
        ON CONFLICT (station_id) DO UPDATE SET
            name = EXCLUDED.name, lat = EXCLUDED.lat, lon = EXCLUDED.lon, region = EXCLUDED.region,
            drainage_area_km2 = COALESCE(EXCLUDED.drainage_area_km2, stations.drainage_area_km2),
            params = (SELECT ARRAY(SELECT DISTINCT unnest(stations.params || EXCLUDED.params) ORDER BY 1)),
            official_thresholds = CASE WHEN EXCLUDED.official_thresholds = '{}'::jsonb
                                       THEN stations.official_thresholds ELSE EXCLUDED.official_thresholds END,
            links = stations.links || EXCLUDED.links,
            meta = stations.meta || EXCLUDED.meta,
            updated_at = now()
        """,
        {
            "lat": None, "lon": None, "region": None, "drainage_area_km2": None, "params": [],
            **s,
            "official_thresholds": Jsonb(s.get("official_thresholds") or {}),
            "links": Jsonb(s.get("links") or {}),
            "meta": Jsonb(s.get("meta") or {}),
        },
    )


@dataclass
class Run:
    conn: psycopg.Connection
    source: str
    job: str
    run_id: int = 0
    items_total: int = 0
    items_fetched: int = 0
    items_unchanged: int = 0
    items_failed: int = 0
    rows: UpsertResult = field(default_factory=UpsertResult)
    errors: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def __enter__(self) -> Run:
        if self.job.startswith("backfill"):
            # Backfills are resumable; a previous run of the same job still marked 'running' was
            # interrupted (container stopped). Record that honestly before starting again.
            self.conn.execute(
                "UPDATE ingest_runs SET status = 'error', finished_at = now(),"
                " error_text = 'abandoned: interrupted, resumed by a later run'"
                " WHERE source = %s AND job = %s AND status = 'running'",
                (self.source, self.job),
            )
        self.run_id = self.conn.execute(
            "INSERT INTO ingest_runs (source, job) VALUES (%s, %s) RETURNING run_id", (self.source, self.job)
        ).fetchone()[0]  # type: ignore[index]
        return self

    def fail(self, item: str, err: BaseException | str) -> None:
        self.items_failed += 1
        msg = f"{item}: {err!r}" if isinstance(err, BaseException) else f"{item}: {err}"
        self.errors.append(msg)
        L.error("ingest item failed", **log.kv(source=self.source, job=self.job, item=item, error=str(err)))

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        if exc is not None:
            self.errors.append(f"run aborted: {exc!r}")
        if exc is not None or (self.items_total and self.items_failed == self.items_total):
            status = "error"
        elif self.items_failed:
            status = "partial"
        else:
            status = "ok"
        self.conn.execute(
            """
            UPDATE ingest_runs SET finished_at = now(), status = %s, items_total = %s, items_fetched = %s,
                   items_unchanged = %s, items_failed = %s, rows_inserted = %s, rows_updated = %s,
                   rows_unchanged = %s, rows_stale = %s, error_text = %s, details = %s
             WHERE run_id = %s
            """,
            (status, self.items_total, self.items_fetched, self.items_unchanged, self.items_failed,
             self.rows.inserted, self.rows.updated, self.rows.unchanged, self.rows.stale,
             "\n".join(self.errors[:50]) or None, Jsonb(self.details), self.run_id),
        )
        L.info(
            "ingest run finished",
            **log.kv(source=self.source, job=self.job, run_id=self.run_id, status=status,
                     items_total=self.items_total, fetched=self.items_fetched,
                     unchanged=self.items_unchanged, failed=self.items_failed,
                     inserted=self.rows.inserted, updated=self.rows.updated,
                     rows_unchanged=self.rows.unchanged, stale=self.rows.stale),
        )
