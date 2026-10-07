# Stage 01 — Foundation and live archive

> Living document. Written while the stage is built, committed with the code. Newest work-log entries at the bottom.

| | |
|---|---|
| Branch | `stage-01-live-archive` |
| Started | 2026-10-07 13:34 PT |
| Finished | (fill at end) |
| Prompt | `docs/build/prompts/STAGE-01-live-archive.md` |
| Status | in progress |

## Goal

Start keeping the river data that would otherwise disappear, and make it checkable from outside. ECCC's Datamart only holds 30 days of real-time BC gauge data. This stage ingests three public sources continuously on the VM:

- ECCC Datamart hourly CSVs for every BC gauge;
- USGS 15-min stage and flow for the Nooksack/Sumas gauges that flood Sumas Prairie;
- NOAA NWPS official forecasts and flood categories.

Every raw payload is archived immutably on local disk with its sha256. The ECCC 30-day files and the USGS history are backfilled. A read-only HTTPS API lets anyone see what we hold and how fresh it is. The user value: the forecasts and ledger in later stages need this data underneath them, and every hour without archiving is history that cannot be recovered.

## Inputs read

- `CLAUDE.md` (updated on `main`): the raw archive is `ARCHIVE_DIR` (default `/srv/floodlead/archive`), never deleted or overwritten. `pg_dump` goes to `/srv/floodlead/backups/` before any migration that touches existing tables.
- `AGENTS.md`: licensed sources only (records 1, 6, 7 in `data-contract.md` cover ECCC, USGS and NWPS), no leakage, attribution on every response.
- `docs/build/PLAN.md`, "Facts the supervisor verified". ECCC OGC real-time is ~4 h behind, so it is used for station metadata only. Datamart hourly files are ~1 h behind and rewritten at :31. USGS North Cedarville stage dates from 2007-10-01. Everson's 2021 peak was 52,300 cfs. NRKW1 flood stages are given.
- `docs/build/prompts/STAGE-01-live-archive.md`: priorities P1–P4, data model, schedules, archive layout, API, 12 acceptance criteria.
- `docs/stages/STAGE-00-environment.md` (QA passed): e2-standard-2 (2 vCPU, 7.7 GiB, no swap), 92 GB free, ports 80/443/5432/8000 free. Datamart uses a fixed `-08:00` offset. Git identity is unset on the VM.
- `data-contract.md`, `architecture.md`, `README.md`, `evidence/` (`pull_gauges.py` uses the OGC API; `station_summary.csv` reports 1 sentinel row at 08MH001 and ±99999 sentinels in the real-time feed).
- **Re-checked at start (13:33 PT, VM rebooted 4 min earlier onto kernel 7.0.0-1013-gcp):**
  - `docker run --rm hello-world` works **without sudo** (user in group `docker`; Docker 29.1.3, Compose 2.40.3).
  - `gcloud compute addresses list` shows `floodlead-ip` reserved and `IN_USE`, so the external IP is now static. `PUBLIC_HOSTNAME` resolves to it.
  - `ACME_EMAIL` is still **absent** from `.env`.
  - **No snapshot schedule** is attached to the boot disk yet (`disks describe … --format='value(resourcePolicies)'` → empty).
  - Swap is still 0 B. Ports 80/443/5432/8000 are still free.

## Plan

1. Branch, open this doc, commit and push (first).
2. Create a 4 GiB swapfile and add it to `/etc/fstab` (prompt requirement; decision record).
3. Probe each source once to confirm its live payload shapes and commit trimmed real fixtures. USGS OGC `continuous` items (paging, limits, rate-limit headers, deprecation notices), NWPS `gauges/{lid}` (flood categories, `usgsId`), and the ECCC hourly and daily CSVs.
4. Scaffold `src/floodlead/` with `uv`: settings, DB helpers, SQL migrations and runner, raw-archive writer (gzip, atomic, `0444`, sha256 dedupe), set-based upserts with revision capture, `ingest_runs`, JSON logs, CLI `floodlead`.
5. **P1:** ECCC Datamart live ingestion (listing every 10 min, conditional GETs, only changed files). Compose `db` (pinned TimescaleDB/PG16 image, memory-limited) and `ingest` with `restart: unless-stopped`. Bring them up and verify rows plus archive files.
6. **P2:** ECCC 30-day backfill as a one-off compose service. USGS live (15 min, rolling 6 h) and NWPS live (30 min, store every `issuedTime`). USGS history backfill (chunked, resumable cursor, ≤ 4 parallel requests). Station metadata daily from the ECCC OGC API, USGS and NWPS.
7. **P3:** FastAPI read-only API (`/v1/health`, stations, observations, official forecasts, `/docs`, attribution, CORS, rate limit) behind Caddy with automatic HTTPS for `PUBLIC_HOSTNAME`. Report certificate issuance as the inbound proof.
8. **P4:** tests on real fixtures (parsers, conversions, sentinels, `-08:00`, upsert idempotency and revisions against a disposable DB, API contract) plus `@pytest.mark.live`. Run `ruff` and `pytest`. Update `architecture.md`, `README.md` and `data-contract.md`. Run the restart/reboot check, collect AC evidence, open the PR and write the STAGE REPORT.

## Decisions

(added as they are made)

## Work log

- `13:33` — `git remote set-url origin https://github.com/agenticraptor/trilemma-datathon-FloodLeadBC.git` (the new URL the human gave), `git checkout main && git pull origin main` → fast-forward `b7b263e..939495f` ("Fold Stage 0 findings into Stage 1; fix repo name and archive wording"). `docker run --rm hello-world` → `Hello from Docker!` without sudo. `git checkout -b stage-01-live-archive`.

## Measurements

| What | Value | How measured | When |
|---|---|---|---|

## Acceptance criteria

| AC | Result | Evidence |
|---|---|---|

## Contract files changed

| File | What changed | Why |
|---|---|---|

## Open issues and handoff to next stage

- (filled at end)
