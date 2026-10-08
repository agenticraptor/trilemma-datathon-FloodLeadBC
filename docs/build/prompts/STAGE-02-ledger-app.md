# Stage 2 prompt — Forecast ledger, baselines, scoring and the first working app

You are the FloodLead BC build worker. Follow `CLAUDE.md` exactly (stage protocol, honesty rules, production safety, STAGE REPORT). Branch: `stage-02-ledger-app`. Stage doc: `docs/stages/STAGE-02-ledger-app.md`, created from `docs/stages/_TEMPLATE.md` **before you write code** and updated in every behaviour-changing commit.

## Mission

From this stage on, FloodLead makes promises in public and keeps score.

Every hour it issues a forecast for every live gauge, fixes it in an append-only, hash-chained ledger **before the truth exists**, publishes the chain head outside the VM, and scores every forecast against what the river actually did, next to persistence, trend and NOAA's official forecast. In the same stage the first user (Pranay) gets a working app that follows one real situation from problem to a useful result built from real data, because Build Session 2 requires it.

The supervisor will judge two things:

1. **Trust.** Nobody, including us, can quietly change a forecast after the fact without it showing.
2. **Visible value today.** The app answers a real question with real numbers, without leaning on future features.

## Deadlines

| When (UTC) | What |
|---|---|
| ~2 h after you start | First hourly issuance in production. Every hour without forecasts is live evidence lost before Demo Day (Oct 13). |
| Oct 9 00:00 (Oct 8 17:00 PT) | Next Datamart date rollover. F1 must be deployed before it. |
| Oct 8 ~20:00 (13:00 PT) at the latest | PR open with the app and the README section. Mentors review the repo about 24 h after Build Session 2 (≈ Oct 8 18:00 PT), and QA and merge must happen first. Aim for Oct 8 morning PT. |

## Read first

`CLAUDE.md`, `AGENTS.md`, `docs/build/PLAN.md` (updated by the supervisor for this stage), `docs/stages/STAGE-01-live-archive.md` (decisions D-01.5, D-01.6, D-01.13, D-01.18–D-01.20 and open issues 6–11), `evaluation.md` (you will update it), `architecture.md` (the planned `forecast` and `score` tables are a sketch; change them with a decision record), `data-contract.md` (attribution lines; NOAA's conditions: no implied endorsement, no modified data presented as official). Build Session 2 checklist: `https://github.com/TrilemmaFoundation/Datathon-Season-2026/blob/main/build%20session%20checklist/build-session-2.md` (summarised in Part F).

## Stage 1 QA (supervisor, Oct 8 00:00–00:20 UTC): PASS, merged as `fe8208f`

Independently confirmed: health green for all three sources; latest ECCC rows equal the live files (08MH001 at 23:20Z = 1.531 m); the NOAA NRKW1 issuance of 2026-10-07T15:36Z equals api.water.noaa.gov point for point (30 of 30; the 30th point arrived later under the same issuance and was correctly added); the Nov 2021 and Dec 2025 peaks are present; `ruff` clean; `pytest` 44 passed **including the 18 DB tests**, run against a local `timescale/timescaledb:2.30.2-pg16`; the stage doc grew in 11 of 11 commits; no secrets in the diff.

Fix these in this stage:

- **F1 — Datamart date rollover.** At 00:03:50Z on Oct 8 the ECCC run failed: `https://dd.weather.gc.ca/today/hydrometric/csv/BC/hourly/` returned 404 after the UTC date change and was back by about 00:06Z. (The Stage 1 prompt gave you the `today/` path; the defect is the supervisor's.) Measured at 00:08–00:15Z:
  - Dated paths work: `https://dd.weather.gc.ca/YYYYMMDD/WXO-DD/hydrometric/csv/BC/{hourly,daily}/`. At 00:08Z, `20261008/…/hourly/` held 429 files and its `BC_08MH001` file had the same `Last-Modified` (00:01:04Z) as `today/`, while `20261007/…/hourly/` still held the 23:31:20Z version. After midnight only the new date's directory receives rewrites.
  - `today/…/daily/` and `20261008/…/daily/` were 404, while `20261007/…/daily/` was 200 with files `Last-Modified` 2026-10-07 08:19Z. **The 30-day files are written once a day, around 08:00–08:30Z**, so for about 8 h after midnight only yesterday's dated `daily/` directory exists.
  - The hourly file's window starts at local-standard midnight two days back, so the first file after the rollover is shorter (08MH001: 749 rows ending 14:20−08:00 in the last Oct 7 file; 473 rows ending 15:20−08:00 in the first Oct 8 file). That is normal, not a truncation.

  Fix: on 404, fall back from `today/` to the dated directory for the current UTC date, then the previous date (or go dated-first; decide and record why). A 404 inside the rollover window is not an error: record which directory served the run in `ingest_runs.details`. Apply the same rule to anything that reads `daily/`. Unit-test with mocked 404s and check the dated path live.

- **F2 — Stop rewriting unchanged rows.** Each ECCC refresh rewrites about 566–577k unchanged observation rows (`last_seen_at`, and `published_at = GREATEST(...)`), measured as 290,665,936 B of WAL in one refresh window (≈ 14 GB/day of writes, mostly non-HOT updates). The issuer and scorer you are adding read these tables, so fix it now rather than in Stage 8. An identical re-fetch must write **0** observation rows. Keep the out-of-order guard working (an older payload must never overwrite a newer value) and write down what `last_seen_at` and `published_at` mean afterwards (stage doc and `architecture.md`). If a per-file or per-station "last seen" is still useful, keep it outside the hypertable. Measure WAL bytes and `n_tup_upd` / `n_dead_tup` over one refresh before and after. This should be a code-only change; if you decide `observations` needs a schema change after all, take the `pg_dump` to `/srv/floodlead/backups/` first (CLAUDE.md).

- **F3 — Publish the live URL.** Supervisor decision: put `https://<PUBLIC_HOSTNAME>/` at the top of `README.md`. It is the product's public address, and Build Session 3 requires a deployed product others can use. (The human may veto this when relaying the prompt.)

## Priorities and time boxes

| Priority | Deliverable | Target |
|---|---|---|
| P1 | Ledger core, plus `persistence-v1` and `trend3h-v1` issuing hourly in production | first issuance within ~2 h |
| P2 | NOAA issuances in the ledger; scorer; ledger and score API; external verifier; anchoring; F1 | next ~3 h (F1 before Oct 9 00:00 UTC) |
| P3 | First working app (demo path, replay, snapshot mode) and the README Build Session 2 section | by Oct 8 ~15:00 UTC |
| P4 | F2, health additions, tests, docs, contract sync, PR | before you stop |

If time runs out, keep P1 running and report the rest honestly as PARTIAL.

## Part A — The ledger

Design it so that a stranger can verify everything with a public spec, any SHA-256 implementation and the public API.

1. **Additive migration** (`002_…sql`): new tables only.
2. **One global append-only chain.** Entry types: `genesis` (chain spec, repo commit), `model_card` (method, parameters, code commit; any output-changing change means a new version), `issuance` (one per hourly run: base time, counts, stations skipped and why), `forecast` (one per station × model × base time), `official_forecast` (one per new NOAA issuance), `gap` (base times that were missed, written by the next run).
3. **Each entry** stores `seq` (gapless; genesis = 1), `entry_type`, `created_at`, the exact canonical JSON text that was hashed, `prev_hash` and `entry_hash`, plus whatever indexed columns queries need (station, model, base time).
   - `entry_hash = hex(sha256(prev_hash_hex + "\n" + canonical_utf8))`; the genesis `prev_hash` is 64 zeros. Put the exact rule in the spec and test it with a committed golden vector.
   - Canonical JSON: sorted keys, no insignificant whitespace, UTF-8, timestamps in RFC 3339 UTC with `Z`, numbers rounded to sensible precision (levels to 0.1 mm, probabilities to 1e-4). The canonical text includes `seq`, `entry_type` and `created_at`. Verifiers hash the stored text and never re-serialise numbers.
4. **Serialised appends.** A locked head row (or an advisory lock) so concurrent writers can never fork the chain or leave gaps. Each hourly run is one transaction.
5. **Immutability.** Triggers reject `UPDATE`, `DELETE` and `TRUNCATE` on the ledger tables. Be exact in the docs: this is *tamper-evident* (hash chain plus external anchors), not tamper-proof (a database superuser can disable triggers).
6. **No backdating, ever.** Forecasts are only issued live. A run that starts more than 30 min after its base time is skipped and recorded as a `gap`. Never fill gaps later. (Appending the NOAA issuances already held since Oct 7, with their true `fetched_at`, is allowed: it records facts at their real times; it is not a forecast.)
7. **Anchors.** Every hour, append `<anchored_at> <seq> <entry_hash>` to `ledger/heads.txt` on a **`ledger` branch** of this repository through the GitHub contents API, using `LEDGER_GITHUB_TOKEN` from `.env` (a fine-grained token for this repository only, Contents read/write; the human creates it). Record each anchor (seq, hash, time, commit SHA and URL) in a table. This job never touches `main` and never force-pushes. Until the token exists, the job reports `pending` (health amber) and you push anchors from your session at least every 3 h while you work, logging each one in the stage doc.
8. **Public spec**, `docs/ledger-spec.md`: hashing, canonicalisation, entry types and fields, anchors, and how to verify, written so someone could re-implement the verifier in another language.
9. **Verifiers.** `floodlead ledger verify` (direct from the database) and `scripts/verify_ledger.py` (Python standard library only). The script pages through `/v1/ledger`, recomputes every hash, checks seq continuity and prev links, checks every line of `ledger/heads.txt` (raw GitHub, branch `ledger`) against the chain, supports `--from-seq` starting at an anchored entry, prints counts and exits non-zero on any failure.

## Part B — Baseline forecasters

**Common rules**

- **Target:** water level (`param='level'`) in metres, for every station with a non-sentinel level observation newer than 3 h at issue time (expect ~430 ECCC and 10 USGS). Other stations are skipped and counted in the `issuance` entry.
- **Cadence:** `base_time` is the top of each UTC hour. The run starts at HH:15 (configurable), after the HH:01 Datamart rewrite has landed (files appear 2–6 min after `Last-Modified`, ECCC is polled every 5 min, and a refresh takes 54–103 s). `created_at` is the real creation time and is the forecast's issue time.
- **Horizons:** 1, 3, 6, 12, 18, 24, 36, 48 h, with `valid_at = base_time + h`. These land on the ECCC 5-min grid, the USGS 15-min grid and, for multiples of 6 h from 00/06/12/18Z, on NOAA's 6-hourly valid times. Drop a horizon if `valid_at − created_at < 30 min`.
- **Data age:** `data_as_of` is the time of the newest level observation used; input age is `created_at − data_as_of`. `stale_inputs = true` when the input age exceeds the source's green lag threshold from `/v1/health` (ECCC 150 min, USGS 120 min). Stale forecasts are still issued and recorded, and are scored separately (left out of the default summary). This replaces the "> 30 min" rule in `evaluation.md`, which assumed a far faster feed than ECCC's real 40–90 min.
- **Leakage:** only rows with `ts ≤ created_at` and `first_seen_at ≤ created_at` may be used. Each forecast records `input_hash` (SHA-256 of the canonical list of `(ts, value)` inputs) and the hash of the error library it used, so anyone can re-fetch the inputs from the public API and reproduce the forecast.
- **Outputs per horizon:** quantiles at 0.05, 0.10, 0.25, 0.50, 0.75, 0.90 and 0.95 of (a) the level at `valid_at` (`q`) and (b) the maximum level over `(data_as_of, valid_at]` (`qmax`); and `p_exceed` for each threshold = P(maximum over that window ≥ threshold), computed from the samples, not interpolated. `qmax` lets the app answer any personal level.
- **Thresholds in this stage:**
  - Official NWS categories where they exist: North Cedarville `usgs:12210700` action 144.8 / minor 146.5 / moderate 148 / major 150 ft; Ferndale `usgs:12213100` action 15 / minor 18 / moderate 20.5 / major 23 ft; Everson `usgs:12211200` action 83 ft; Overflow at SR 544 `usgs:12211195` action 3.6 / minor 4 ft.
  - Relative rises for every station: +0.25, +0.5 and +1.0 m above the level at `data_as_of`. They give real, scorable events even in a dry October.
  - BC station thresholds arrive in Stage 3.

**Method (both baselines).** A point path from the method, plus **empirical error paths of that same method** on the station's own history (data first seen before `created_at`), sampled across past origins: samples = point path + error path, and the quantiles and exceedances come from those samples. Index errors by lead from `data_as_of` (`valid_at − data_as_of`), not by `h`. Precompute the error libraries (for example daily), cache them under a params hash, and subsample origins to bound time and memory. The hourly run must finish within 10 min and stay inside the `ingest` memory limit; log runtime and peak memory.

- ECCC libraries: the station's trailing 30 days of 5-min data (all we hold until Stage 3).
- USGS libraries: the same season (±30 days of day-of-year) across all prior years of 15-min data, plus the trailing 30 days.

**`persistence-v1`:** the point path is the level at `data_as_of` for every lead.

**`trend3h-v1`:** what a person watching the chart does. Least-squares slope over the 3 h of observations ending at `data_as_of` (require at least 50 % coverage of that window; otherwise skip the trend forecast for that station and count it). Point path = last observed level + slope × min(lead, 6 h): the trend is applied for at most 6 h and then held, so the 48 h trend is not a strawman. Record this in a decision and in `evaluation.md`.

Each model is described by a `model_card` entry.

## Part C — Official forecasts in the ledger

- For every NOAA issuance first stored in `official_forecasts`, append one `official_forecast` entry with the values exactly as received (stage in ft, flow in kcfs, valid times, `generatedTime`), NOAA's `issuedTime`, our `fetched_at`, and the raw object's sha256. Never modify an official value. For points NOAA adds later under the same issuance, append a further entry for the added points (or record another rule in a decision).
- Mapping from the NWPS `usgsId`: `NRKW1` → `usgs:12210700` (North Cedarville), `NKSW1` → `usgs:12213100` (Ferndale). NWPS stage and USGS gage height share a datum. Converting feet to metres for scoring is a unit conversion, not a modification; wherever NOAA values are shown as official, show them in feet as published.

## Part D — Truth and scoring

- **Settling:** score a forecast horizon once `valid_at` is at least 3 h old (this covers feed latency). The scorer runs hourly.
- **Level truth:** the observation at exactly `valid_at`; otherwise the nearest within ±10 min; otherwise `no_truth` (counted, never imputed).
- **Event truth:** the maximum of observations over `(data_as_of, valid_at]` ≥ threshold. This is the same window as `qmax` and `p_exceed`, so forecast and truth mean the same thing; document that the window includes the feed-latency gap the forecaster could not see. If observations cover less than 80 % of the window, the event is `insufficient_truth`.
- Store with each score the truth values used, their `first_seen_at` and their `revision_count` at scoring time, and rescore when a truth row is revised later. Scores are derived data, not ledger entries, and must be reproducible from the ledger plus observations.
- **Metrics:** CRPS approximated by the quantile score (2 × mean pinball loss over the 7 levels; document this, and test that it equals the absolute error for a point forecast); absolute error of the median; coverage of the 25–75, 10–90 and 5–95 % intervals; PIT bin; Brier per threshold, with its outcome.
- **NOAA matched comparison:** for our base times at 00/06/12/18Z and horizons that are multiples of 6 h, take NOAA's latest issuance with `fetched_at ≤` our `created_at` and compare at the same `valid_at`: absolute error (the CRPS of a point forecast) and Brier with p ∈ {0, 1} for the official categories. Also report NOAA's own lead (`valid_at − issuedTime`), so readers can see that NOAA issues about once a day.
- **Summary** (materialised after every scorer run, carrying `scorer_run_id` and the time window): by model × horizon × source, and NRKW1/NKSW1 against NOAA: n, stations, days, mean CRPS, **CRPSS vs persistence on paired samples only** (same station, base time and horizon scored for both), MAE, interval coverage, and Brier and BSS per threshold family with event counts. When an event count is below 30, the summary says "too few events to judge" instead of a skill number. Add day-block bootstrap 90 % intervals for CRPSS if time allows.
- No performance number may appear in the docs or the UI except as output of this scorer, with its run ID.

## Part E — API additions

- `GET /v1/ledger?after_seq=&limit=` (≤ 1000, in seq order; each entry with seq, type, created_at, canonical text, prev_hash, entry_hash).
- `GET /v1/ledger/head` (seq, hash, created_at, the latest anchor with its commit URL, anchor status) and `GET /v1/ledger/{seq}`.
- `GET /v1/stations/{id}/forecast`: the latest forecast per model with its seq and hash, plus the linked NOAA official forecast's latest issuance, unmodified.
- `GET /v1/scores/summary?source=&model=&horizon=` (materialised) and `GET /v1/scores/official?lid=`.
- `/v1/health` gains `issuer`, `scorer` and `anchor` blocks (last run, status, lag) with documented green/amber/red rules.
- Same attribution, CORS and rate limits as Stage 1.

## Part F — The first working app (Build Session 2)

The Build Session 2 checklist asks for a demo path **Problem → Action in the app → Visible useful result**; value the app **already** creates (future features are not the story); claims backed by visible behaviour and the data; real, permitted data; and a repository that lets anyone reproduce the app locally. A static frontend with prepared data is enough. We also have a live API, so use it, with a static fallback.

**The demo path (one real situation)**

- *Situation:* an atmospheric river is coming. Will the Nooksack spill over toward Sumas Prairie (it did in November 2021 and December 2025, flooding farms and closing Highway 1), and how many hours would we have?
- *Action:* open the app → "Sumas Prairie overflow watch" → see North Cedarville now against the official flood stages, NOAA's official 7-day forecast, and FloodLead's baseline forecast with the chance of crossing each stage within 6, 12, 24 and 48 h → type a personal level and get the chance of reaching it within each horizon and the earliest hour with at least a 10 % and a 50 % chance → open the replay to see how the same gauge behaved before the overflow began in 2021 and 2025.
- *Visible result:* the live distance to each stage, with data time and age; the chances; and, from the replay, how many hours the gauge gave before the overflow started.

**Replay facts to reproduce** (supervisor's queries of the public API, Oct 8)

| Event | North Cedarville crossed minor (146.5 ft) | First record at Overflow SR 544 (`usgs:12211195`) | Gap | North Cedarville level then |
|---|---|---|---|---|
| Nov 2021 | 2021-11-14 21:30Z | 2021-11-15 02:25Z (3.81 ft) | 4 h 55 min | 147.56–147.63 ft |
| Dec 2025 | 2025-12-10 20:15Z | 2025-12-11 00:45Z | 4 h 30 min | 147.47–147.53 ft |

Other crossings: Nov 2021 action 2021-11-14 18:30Z, moderate 2021-11-15 04:00Z, major 2021-11-15 23:45Z, peak 150.76 ft at 2021-11-16 00:50Z, Everson action (83 ft) 2021-11-15 00:15Z; Dec 2025 action 2025-12-09 07:15Z, moderate 2025-12-11 03:30Z, major 2025-12-11 10:00Z, peak 150.44 ft at 11:00Z.

Recompute all of these from the database: the app computes them; nothing is hardcoded. Then find out when the `12211195` record begins and whether the gauge reports only while water is flowing (that is what makes "first record" mean "onset"), and compute the same table for **every** event in the record where North Cedarville crossed minor stage. Show the table in the app and in the README with its caveats (approved historical data, not what was visible in real time; a small number of events). If your numbers differ from the supervisor's, explain why. If the onset level holds up, offer it in the app as a suggested personal level ("the overflow began near X ft in N of N events"), labelled as an empirical observation, not an official threshold. Optional, only if time allows: run the two baselines at past base times during these events with the data available at those times, clearly labelled as after-the-fact replays (not ledger entries).

**Must-haves**

- Served at `https://<PUBLIC_HOSTNAME>/` by Caddy from a static directory (for example `web/`), calling the same-origin API. Serve it with a strict Content-Security-Policy (`default-src 'self'`), relaxed only with a recorded reason.
- **Snapshot mode:** `floodlead export-demo` writes `web/data/snapshot/*.json` (real data plus its timestamp and the attribution lines). When the API cannot be reached, the app loads the snapshot and shows a visible "Snapshot from <time>" banner. `python3 -m http.server -d web 8080` must run the app locally with no other setup; `docker compose up` is the full-stack path. Commit a snapshot.
- No build step. A pinned, permissively licensed chart library vendored under `web/vendor/` with its licence (for example uPlot, MIT). The page makes no third-party requests (no CDNs, web fonts or analytics).
- US gauges show ft and m; BC gauges show m. Every number shows its data time and age, and real-time data is labelled provisional.
- FloodLead forecasts are labelled **FloodLead baseline (persistence / trend), live skill being measured**, link to the scores, and are never styled like NOAA's forecast, which is labelled **NOAA NWS official forecast (unmodified)**.
- Personal levels stay on the device (the browser may remember them); they are never sent to or stored on the server.
- Footer: "Not a warning service. Follow EmergencyInfoBC, the BC River Forecast Centre, NWS Seattle and local authority orders", with links, plus the attribution lines from `data-contract.md`.
- A station picker for every gauge (search by name or ID) with a 7-day chart and the latest baseline forecast.
- A ledger panel: head hash, latest anchor link and, for the forecast on screen, its seq and hash, with a link to `docs/ledger-spec.md`.
- Works at 375 px width. Someone new should understand the overflow-watch screen in 30 seconds.
- Screenshots of the demo path (live view, personal-level result, replay; desktop and 375 px) taken with a headless browser and committed under `docs/stages/img/stage-02/`.

## Part G — README for Build Session 2

Add a "Build Session 2 — working app" section that covers what the checklist asks: the idea and the key choices you made (link the decisions); the data used and how it supports the result; how to run it locally (both paths, including `floodlead export-demo`); the demo path (situation → action → expected result, with the replay numbers you computed); and what works now versus what remains before Build Session 3. Put the live URL at the top of the README (F3).

**Do not write the author's brief.** The checklist requires Pranay to write his brief in his own words before asking an LLM. If `brief.md` exists on `main` when you finish, link it from the README; otherwise list it under "Needs human".

## Tests

- Golden-vector chain test; tamper detection (one changed byte, a swapped pair, a deleted entry → verification fails at the right seq), against both verifiers.
- Immutability triggers reject `UPDATE`, `DELETE` and `TRUNCATE`; concurrent appends stay gapless.
- Baseline maths on synthetic series: a constant series gives zero-width intervals; a random walk with a known step distribution gives quantiles and a rise exceedance within a stated tolerance of the analytic values; the trend handles gaps and insufficient coverage.
- Leakage: a row whose `first_seen_at` is after `created_at` is never used.
- Scoring: the quantile-score CRPS equals the absolute error for a point forecast and approximates the analytic CRPS of a normal distribution within a stated tolerance; Brier; truth matching within ±10 min; the window-coverage rule; the NOAA `fetched_at ≤ created_at` rule.
- F1 rollover fallback with mocked 404s; F2: an identical re-upsert writes 0 rows.
- API contract tests for the new endpoints; an app smoke test (the index loads; the snapshot JSON matches its schema).
- The DB tests must run, not skip. Say how you ran them.

## Documentation (while you build)

- Stage doc: at least 12 decisions (for example: one global chain vs per station; canonicalisation and rounding; serialised appends; tamper-evident wording; anchor channel and frequency; base time and the HH:15 run; horizons; the empirical error-path method; the trend cap; the stale rule; the event window; the CRPS approximation; paired skill; truth rules; static app with snapshot fallback; chart library; F1; F2). Record measured numbers: issuance runtime and peak memory, entries per hour, bytes per entry, ledger growth per day, scorer runtime, WAL before and after F2.
- `docs/ledger-spec.md` (new).
- `architecture.md`: ledger and score schema as built, scheduler jobs, API, web app, anchoring.
- `evaluation.md`: issuance cadence and horizons, baseline definitions (including the 6 h trend cap), the stale-input rule, scoring definitions (CRPS approximation, event window, paired skill), hourly anchoring to the `ledger` branch, the matched NOAA comparison.
- `README.md` (Part G and F3); `product.yaml` if outputs or status changed. Re-estimate disk growth and runway with the ledger included.

## Acceptance criteria

| AC | Criterion | Evidence to paste |
|---|---|---|
| AC-1 | Hourly issuance live: at least 6 consecutive base times by PR time, each with ≥ 400 stations × 2 models; every `created_at − base_time ≤ 30 min`; 0 backdated entries; a `gap` entry for any missed hour | SQL + `/v1/ledger/head` |
| AC-2 | The chain verifies from outside: `python3 scripts/verify_ledger.py --api https://<host>` → OK with counts; the tamper tests detect each change | output |
| AC-3 | `UPDATE`, `DELETE` and `TRUNCATE` on the production ledger fail (run each inside `BEGIN … ROLLBACK`) | psql output |
| AC-4 | At least 3 hourly anchors on the `ledger` branch match the chain (PARTIAL if the token is missing and anchors were pushed by hand) | verifier output + commit URLs |
| AC-5 | Every NOAA issuance held is in the ledger; the latest NRKW1 issuance matches api.water.noaa.gov point for point | side by side |
| AC-6 | For 3 random forecasts, `input_hash` and the persistence median recomputed from the public observations API match the ledger | script output |
| AC-7 | Leakage audit over all forecast entries: 0 inputs with `ts` or `first_seen_at` after `created_at`; 0 horizons with `valid_at − created_at < 30 min` | SQL |
| AC-8 | At least 5,000 settled scores; `/v1/scores/summary` gives paired CRPS, MAE and coverage for both models at ≥ 4 horizons, with n; NOAA matched pairs reported, or the time the first one settles | API output |
| AC-9 | The demo path works on the public URL (screenshots of the live view, personal level and replay, desktop and 375 px); replay numbers equal an independent SQL query; snapshot mode runs with `python3 -m http.server -d web 8080` | screenshots + output |
| AC-10 | F1: fallback test and live dated-path check. F2: WAL and rows written over one ECCC refresh, before vs after; an identical re-fetch writes 0 rows | measurements |
| AC-11 | `ruff check .` and `pytest` pass, with counts; the DB tests ran | output |
| AC-12 | At least 12 decisions; the stage doc in ≥ 5 commits spread across the stage; contract files and README updated; disk runway re-estimated with the ledger | `git log --stat` excerpt |

## Out of scope

Machine-learning models (Stage 4), BC station thresholds and return periods (Stage 3), precipitation inputs, messaging or alerts (Stage 7), accounts or server-side personal levels, the full map-based web app (Stage 6), CI (Stage 8). Do not reboot the VM: the human runs the reboot test after your PR.

## When done

Open the PR titled `Stage 02: Forecast ledger, baselines, scoring and first app` (do not merge) and print the STAGE REPORT. Under "Supervisor checks", list the app URL and `curl` or script commands with expected results: the ledger head, a ledger page, the verifier, the forecast for `usgs:12210700`, the scores summary and the official comparison.
