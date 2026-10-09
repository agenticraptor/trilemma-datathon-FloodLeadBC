# Stage 03 — Working in public, fair scoring, history and training sets

> Living document. Written while the stage is built, committed with the code. Newest work-log entries at the bottom.

| | |
|---|---|
| Branch | `stage-03-public` (PR 1), then `stage-03-history` from the merged `main` (PR 2) |
| Started | 2026-10-09 12:42 PT (19:42 UTC) |
| Finished | (fill at end) |
| Prompt | `docs/build/prompts/STAGE-03-public-history.md` |
| Status | in progress (part 1) |

## Goal

Tonight, people other than the author open FloodLead for the first time (Build Session 3, Oct 10 01:00 UTC). In 30 seconds they must be able to:
- find their gauge;
- see how close it is to a level that matters;
- see an honest track record;
- tell us what they think, without giving us personal data.

Honesty comes first. The current skill numbers are inflated by an approximate CRPS, so the fair CRPS is fixed before any skill number is shown again. Overnight (part 2), the data for the Stage 4 model is built:
- ECCC daily history;
- rainfall, observed and as-issued forecasts;
- the official NWS flood warnings that were actually issued;
- leakage-safe training sets with an event catalogue.

A pre-registered evaluation protocol is frozen before any model is trained. Stage 4 is then judged on held-out floods against persistence, the 3 h trend, the gauge-watch rule and the real NWS warnings, whatever the result.

## Inputs read

- `CLAUDE.md`, `AGENTS.md`:
  - every new source needs a usage-rights record before code depends on it;
  - no leakage: precipitation features use forecasts as issued;
  - personal data is encrypted and never in logs, the ledger or fixtures;
  - no performance claims without a run ID.
- `docs/build/prompts/STAGE-03-public-history.md`: two PRs (part 1 by ~23:30 UTC), F1–F5, part 1 items 1–7, part 2 items 1–7, 12 ACs. Start the part-2 downloads first. No reboot in this stage.
- `docs/build/PLAN.md`:
  - QA log: Stage 2 part 2 PASS (`a4b5b29`). The supervisor recomputed 19,677 entries and 12 USGS score groups.
  - Facts verified on Oct 9: IEM keeps the archived NRKW1 warnings for 2021 and 2025; the official lead was ≈ 6 h in Dec 2025 and ≈ 0 h in Nov 2021; live baselines do not beat pure persistence on median accuracy.
  - Human tasks: rainfall sources and the IEM archive were approved on Oct 9 ("approve all").
- `docs/stages/STAGE-02-ledger-app.md`:
  - D-02.13 (the quantile-score CRPS, its 19 % bias);
  - D-02.17 (`persistence-naive`);
  - D-02.18 (NOAA's 7-day cut);
  - open issues: no skill claim yet; step-change and tidal flags needed; DB memory (1,150 chunks in 2.5 GiB); scorer runtime growth.
- `evaluation.md` line 56 says the quantile score "ranks models". That is wrong for probabilistic-vs-point comparisons (the supervisor's F1): the score favours a spread forecast over a point forecast by ≈ 19 %.
- `data-contract.md`: record 2 (ECCC historical hydrometric, OGC API + HYDAT, OGL-Canada) already covers the daily history and annual peaks. No record yet for ECCC climate, NCEI, SNOTEL, Open-Meteo or IEM.
- **State at start (19:42 UTC):**
  - all 4 services up 16 h (since the 03:50Z reboot);
  - health green (issuer, scorer, anchor);
  - disk 21.7 % used.

## Plan

Part 1 (PR 1, `stage-03-public`, ready by ~23:30 UTC). Lean, in the prompt's priority order:

0. **Start the part-2 downloads first.**
   - Check each new source's terms; write their usage-rights records in `data-contract.md`.
   - Write one paced, resumable download command per source, as `floodlead history <source>`: every raw payload goes into the raw archive, with a manifest table recording what was fetched.
   - Run them as one-off `backfill` compose services (`restart: "no"`), recording start time, rate and finish time.
   - Parsing into tables happens in part 2.
1. **F1 fair CRPS.**
   - Rebuild a piecewise-linear CDF from the stored quantiles, with a documented tail rule, and integrate it exactly.
   - Bias table on synthetic forecasts (normal, log-normal, under- and over-dispersed).
   - Keep the quantile score as a secondary column; add MAE-of-median skill vs naive; add naive to `/v1/scores/official`.
   - Recompute all stored scores; correct `evaluation.md`; 19 quantiles for future models.
2. **Feedback.**
   - `POST /v1/feedback`, stored append-only with the text encrypted (key in `.env`), with a rate limit and size limits.
   - The in-app box, a GitHub issue template, and `floodlead feedback list`.
   - Health shows counts only.
3. **Fraser Valley gauges** on the home page: latest level, data age, and the position against the typical yearly peak.
4. **Typical yearly peak.**
   - Median annual instantaneous peak level, from ECCC `hydrometric-annual-peaks`, with datum checks.
   - Stored with provenance, and put in the ledger (a new model card) before first use.
5. **Help panel and `#/track-record`.** Fair skill vs pure persistence with n, stations, days and the run ID, plus honest framing.
6. **README** "Build Session 3 — working in public".
7. **F4 replay refresh-ahead, F3 `statement_timeout`, F2 reboot evidence.**

Then mark PR 1 ready and print the STAGE REPORT (part 1).

Part 2 (PR 2, `stage-03-history`, Oct 10 ~12:00 UTC):
- parse the downloads into new tables;
- NWS warning timelines;
- upstream links;
- the training sets (`honest` and `oracle`);
- the event catalogue;
- the frozen `docs/evaluation-protocol.md` (after the supervisor's addendum).

## Decisions

## Work log

- `12:42` — `git checkout main && git pull` → `bd3d092`. Branch `stage-03-public`. Read the prompt and the inputs above.
- `12:44` — **F2 reboot evidence** (the reboot was run at the end of Stage 2):
  ```
  $ uptime -s
  2026-10-09 03:50:03
  $ last -x reboot | head -3
  reboot   system boot  7.0.0-1013-gcp   Fri Oct  9 03:50   still running
  reboot   system boot  7.0.0-1013-gcp   Wed Oct  7 20:28 - 03:49 (1+07:21)
  reboot   system boot  7.0.0-1011-gcp   Mon Oct  5 23:59 - 20:27 (1+20:27)
  $ docker ps --format '{{.Names}} {{.Status}}'
  floodlead-api-1 Up 16 hours (healthy)
  floodlead-ingest-1 Up 16 hours
  floodlead-caddy-1 Up 16 hours
  floodlead-db-1 Up 16 hours (healthy)
  ```
  - The VM booted at 03:50:03Z, and all four containers came back on their own (`restart: unless-stopped`).
  - The supervisor's QA found 23 consecutive hourly issuances with 0 gaps across the reboot, so the 04:00Z base time was issued on time.

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

- (filled at end of each part)
