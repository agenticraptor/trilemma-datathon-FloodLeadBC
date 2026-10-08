# Stage 02 — Forecast ledger, baselines, scoring and the first working app

> Living document. Written while the stage is built, committed with the code. Newest work-log entries at the bottom.

| | |
|---|---|
| Branch | `stage-02-ledger-app` (PR 1), then `stage-02-part2` (PR 2) per addendum 1 |
| Started | 2026-10-08 12:41 PT (19:41 UTC) |
| Finished | (fill at end) |
| Prompt | `docs/build/prompts/STAGE-02-ledger-app.md` + `docs/build/prompts/STAGE-02-addendum-1.md` (the addendum wins where they conflict) |
| Status | in progress |

## Goal

From this stage on, FloodLead makes promises in public and keeps score. Every hour it issues baseline forecasts (`persistence-v1`, `trend3h-v1`) for every live gauge and fixes them in an append-only, hash-chained ledger before the truth exists. It publishes the ledger entries and chain head off the VM on a `ledger` branch, and scores every forecast against what the river did, next to NOAA's official forecast.

In the same stage, the first user gets a working app that follows one real situation from problem to result, using real data: **will the Nooksack spill toward Sumas Prairie, and how many hours would we have?** The app shows North Cedarville against the official flood stages, NOAA's official forecast, FloodLead's baseline chances of crossing, a personal level, and a replay of the 2021 and 2025 overflows. Build Session 2 mentors look at `main` at about Oct 9 01:00 UTC, so the app and the ledger core ship first, in PR 1.

## Inputs read

- `CLAUDE.md`, `AGENTS.md` (append-only ledger, no leakage, no performance claims without a run ID, NOAA conditions).
- `docs/build/prompts/STAGE-02-ledger-app.md`: Parts A–G, F1–F3, 12 ACs.
- `docs/build/prompts/STAGE-02-addendum-1.md`, which overrides the prompt:
  - two PRs and a new order (F1 → app → ledger core → PR 1 by ~23:30 UTC → the rest in PR 2);
  - credentials are set;
  - **no disk snapshots** (accepted risk);
  - publish the ledger entries hourly, not just the head;
  - link `brief.md` as AI-drafted;
  - the worker runs the reboot test as the very last step.
- `docs/build/PLAN.md`: Stage 1 QA log (PASS, `fe8208f`) and the facts it verified: the `today/` 404 after midnight, 30-day files written ~08:19Z, ~570k unchanged rows rewritten per refresh, and the overflow onset at North Cedarville ≈ 147.5 ft in 2021 and 2025. Also the human-task table: snapshots declined; the reboot moved to me.
- `brief.md` (on `main`, AI-drafted by the supervisor). It will be linked, never edited.
- `docs/stages/STAGE-01-live-archive.md`: D-01.5, D-01.6, D-01.13, D-01.18–D-01.20 and open issues 6–11.
- `evaluation.md`: its "> 30 min stale" rule assumed a far faster feed than ECCC's 40–90 min, and will be replaced.
- **State at start (19:41 UTC):**
  - `.env` keys: `PUBLIC_HOSTNAME, POSTGRES_PASSWORD, ARCHIVE_DIR, LEDGER_GITHUB_TOKEN, USGS_API_KEY` (values not printed);
  - health green for all three sources; disk 18.2 %;
  - all 4 services up for 21–22 h.

## Plan

Order from addendum 1 (targets in UTC):

1. Open this doc, commit, push (first).
2. **F1** (before 00:00): dated-directory fallback for ECCC `today/` 404s, for both `hourly/` and `daily/`, recorded in `ingest_runs.details`. Mocked-404 tests plus a live check of the dated path. Deploy.
3. Credentials: recreate `ingest`; confirm the USGS keyed rate limit without printing the key.
4. **App, part 1 (~21:30):**
   - static `web/` served by Caddy under a strict CSP: the overflow-watch view on Stage 1 data, NOAA's forecast, data age, the station picker with a 7-day chart;
   - the 2021/2025 replay computed from the DB for every minor-stage event, via a new API endpoint;
   - snapshot mode (`floodlead export-demo`);
   - the README Build Session 2 section;
   - **F3**: live URL at the top of the README; `brief.md` link; snapshot claims removed from the contract files.
5. **Ledger core (~23:15):**
   - migration `002` (ledger tables, immutability triggers, serialised appends);
   - canonical JSON and hashing with a golden vector; genesis and model cards;
   - `persistence-v1` and `trend3h-v1` with empirical error-path libraries;
   - an hourly issuer at HH:15 with gap entries;
   - `/v1/ledger`, `/v1/ledger/head`, `/v1/stations/{id}/forecast`;
   - the app's forecast panel (chances, personal level) and ledger panel.
6. **PR 1** `Stage 02 (part 1): first app and forecast ledger` with a STAGE REPORT of what is done and what is not.
7. **Part 2** on `stage-02-part2` from the merged `main`:
   - official forecasts in the ledger, scorer and summaries, remaining API;
   - hourly anchors and entries published to the `ledger` branch via `LEDGER_GITHUB_TOKEN`;
   - both verifiers (`--source github`);
   - **F2** (0 rows written on identical re-fetch; WAL before and after);
   - health blocks, tests, docs, screenshots;
   - **PR 2**, then the STAGE REPORT, then `sudo reboot` as the last action.

## Decisions

(added as they are made)

## Work log

- `12:41` — `git checkout main && git pull` → `9e414f1` ("Stage 2 addendum: timeline reset, app first, two PRs before the mentor review"). PR #2 shows as `MERGED`. Read the prompt, addendum 1, PLAN.md and `brief.md`. `git checkout -b stage-02-ledger-app`.

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
