# Stage 3 prompt — Working in public (Build Session 3), fair scoring, history and training sets

You are the FloodLead BC build worker. Follow `CLAUDE.md` exactly. This stage has **two PRs**, like Stage 2:

| PR | Branch | Title | Target (UTC) |
|---|---|---|---|
| 1 | `stage-03-public` | `Stage 03 (part 1): working in public` | open by **Oct 9 ~23:30**, so the supervisor can QA and merge before Build Session 3 (Oct 10 01:00 UTC = Oct 9 18:00 PT) |
| 2 | `stage-03-history` (from the merged `main`) | `Stage 03 (part 2): history and training sets` | Oct 10 ~12:00 |

One stage doc for both parts: `docs/stages/STAGE-03-public-history.md`, created from the template **before you write code** and updated in every behaviour-changing commit. Open each PR as a **draft as soon as it has its first commit**, and deploy only from a branch with an open PR (addendum 2, item 7).

## Mission

Build Session 3 is "Working in Public: a deployed product that others can use, understand, and give feedback on". Tonight, people other than Pranay will open the app. They must be able to:

- find their gauge;
- understand in 30 seconds how close it is to a level that matters;
- see an honest track record;
- tell us what they think.

Then, overnight, prepare the data the Stage 4 model needs.

**The owner's standing instruction (Oct 9):** the product must be genuinely useful and the Demo Day numbers must be real; "we can't fool the judges". So the Stage 4 model will be judged on held-out floods it never saw, against four comparators:
- pure persistence;
- the 3 h trend;
- the gauge-watch rule (overflow follows minor stage);
- **the official NWS flood warnings that were actually issued for North Cedarville**.

Whatever the result, it gets reported. This stage builds the data and the pre-registered protocol that make that comparison possible and honest.

## Read first

`CLAUDE.md`, `AGENTS.md`, `docs/build/PLAN.md` (QA log and human tasks), `docs/stages/STAGE-02-ledger-app.md` (open issues at the end, D-02.13, D-02.17, D-02.18), `evaluation.md`, `data-contract.md` (records 2 and 3), `docs/ledger-spec.md`.

## Stage 2 QA (supervisor, Oct 9 ~19:00 UTC): PASS, PR #4 merged as `a4b5b29`

Verified independently:
- **Ledger:** all 19,677 entries recomputed from the API and rebuilt from the `ledger` branch alone, identical. All 23 anchors match. 23 consecutive hourly issuances with 0 gaps.
- **Scores:** all 12 USGS score groups (3 models × h1/h3/h6/h12) recomputed from the ledger plus the public observations API, equal to `/v1/scores/summary` (n, CRPS and MAE).
- **App fixes:** 375 px pages no longer scroll sideways, a POSIX-locale browser shows 0 console errors, tables are full width, and the suggested level is minor stage.
- **Tests:** `pytest` 96 passed with the DB tests run. `ruff` clean. No secrets in the diff.

Carried into this stage:

- **F1 — Fair CRPS (do this first; it decides the headline).** The quantile score equals the absolute error for a point forecast but is about 19 % below the exact CRPS for a calibrated probabilistic forecast. So every CRPSS of `persistence-v1` or `trend3h-v1` **against `persistence-naive`** is inflated. The live summary shows ECCC h1 CRPSS +0.30 vs naive, yet the median of `persistence-v1` is *worse* than naive at every ECCC horizon: MAE at h1 is 0.0279 against 0.0273 m, and at h12 0.0882 against 0.0852 m. `evaluation.md`'s sentence "it ranks models" is wrong for probabilistic-vs-point comparisons. Fix:
  1. Compute CRPS from a distribution rebuilt from the 7 stored quantiles: a piecewise-linear CDF between quantiles, with a documented tail rule beyond 0.05 and 0.95, integrated exactly.
  2. Measure its bias against exact CRPS on synthetic forecasts: calibrated normal, a skewed (log-normal) case, and an under- and an over-dispersed case. Target |bias| < 5 %. If you cannot reach it, report the residual and say what it does to the comparison.
  3. Keep the quantile score as a secondary column. Recompute all stored scores; they are derived data.
  4. Add **MAE-of-median skill** against naive (point vs point) to the summary.
  5. Add `persistence-naive` to `/v1/scores/official`.
  6. Correct `evaluation.md`.
  7. Future models store **19 quantiles** (0.05 … 0.95 in steps of 0.05) so the rebuild is tight. Existing models keep 7.
- **F2 — Reboot evidence.** The supervisor could not see the reboot from outside: no gap was expected, and none appeared. Paste `uptime -s`, `last -x reboot | head -3` and `docker ps --format '{{.Names}} {{.Status}}'` into the stage doc.
- **F3 — Database safety (from the 01:38Z OOM).** Add a `statement_timeout` for ad-hoc and maintenance sessions. History data goes into **new tables**, never into the 15-min `observations` hypertable (it already has ~1,150 weekly chunks). Raising `timescaledb.max_background_workers` and compressing old chunks are allowed only with a `pg_dump` to `/srv/floodlead/backups/` first and a decision record. Skip them if time is short.
- **F4 — Replay cold start.** `/v1/replay/overflow` costs ~9 s when its 1 h cache expires (one supervisor page load took 16.5 s). Refresh it in the background before it expires, so no visitor pays that.
- **F5 — Correction.** NOAA does not append points to an issuance; our old endpoint cut it at +7 days (D-02.18). The supervisor fixed PLAN.md. Nothing for you to do.

## Part 1 — Working in public (PR 1, before Build Session 3)

Priorities, in order. If time runs out, ship 1–5 and report the rest as PARTIAL.

1. **F1 fair CRPS** (above), deployed and recomputed. No other skill number may appear anywhere until this is done.
2. **Feedback that reaches us.**
   - **In the app:** a "Was this useful?" box on every page: yes/no plus optional free text (≤ 1,000 characters).
     - It has no name, email or phone fields, and tells people not to type personal information.
     - `POST /v1/feedback` takes: page or route, station shown, the yes/no, the text, the app version. It is rate-limited per IP in memory, with size limits; it never renders HTML and is never echoed publicly.
     - It is stored append-only in a new `feedback` table, with the free text **encrypted at rest** (key in `.env`, never logged). It is kept out of logs, the ledger, snapshots and test fixtures (AGENTS.md privacy rule; the VM is in Canada).
     - Health shows counts only.
   - **On GitHub:** an issue template `.github/ISSUE_TEMPLATE/feedback.yml`, linked from the app ("Prefer GitHub? Open an issue") for people who want a reply.
   - **A reading tool:** `floodlead feedback list` in the CLI, so the human can read the feedback on the VM.
3. **Find your gauge.** On the home page, under the overflow watch, add a "Fraser Valley gauges" list. Each gauge shows its latest level, data age, and its position against its typical yearly peak (item 4) when that exists.
   - Include at least Sumas R. near Huntingdon (08MH029), Chilliwack R. at Vedder Crossing (08MH001), Chilliwack R. above Slesse Ck (08MH103), Fraser R. at Hope (08MF005), Fraser R. at Mission (08MH024, tidal: say so), Nicomekl R. at 203 St (08MH155) and Coquihalla R. below Needle Ck (08MF062).
   - The search on `#/stations` stays.
4. **A meaningful level for BC gauges: "typical yearly peak".**
   - **Data:** from ECCC annual instantaneous peaks (OGC API `hydrometric-annual-peaks`; data-contract record 2 covers ECCC historical extremes), compute per BC station the median annual instantaneous peak *level* over a recent, consistent period. For example the last 20 years, with ≥ 10 years of data required.
   - **Datum checks:** before using a level, compare the peaks with this station's current 30-day levels and its daily history. Reject or flag stations where a datum change is likely, and record the rule and the counts.
   - **Storage:** keep them per station with provenance (years used, n, method), separate from the NOAA official thresholds.
   - **Labels:** in the app, "Typical yearly peak (reached in about half of years): FloodLead-derived from ECCC records, not an official flood level".
   - **Ledger:** forecasts that include this threshold must be verifiable. Put the threshold values and their provenance into the ledger (in a new model card's params, or another entry you justify) **before** the first forecast that uses them. Record the versioning choice as a decision. Do not alter existing model cards or entries.
5. **"How to read this" and a track-record page.**
   - **Help panel:** short and collapsible, covering stage and gauge datum, data age and provisional data, "chance of reaching", FloodLead baseline vs NOAA official, and what the ledger proves.
   - **Track record:** a page `#/track-record` showing, from the scorer with its run ID:
     - forecasts issued;
     - the chain head and latest anchor, with "verify it yourself" instructions;
     - skill against **pure persistence** per horizon (fair CRPS and MAE), with n, stations and days;
     - the NOAA matched-pair count.
   - **Honest framing:**
     - If the baselines are not better than pure persistence, say so plainly; that is the bar the Stage 4 model must clear.
     - State what the live window contains: for example, "no gauge reached a flood stage since Oct 8, so these numbers describe quiet rivers, not floods".
     - No number without its n and its scorer run ID.
6. **README "Build Session 3 — working in public".**
   - Who it is for and how to use it in 3 steps.
   - How to give feedback.
   - What is measured live (link the track record).
   - Known limits: baselines only, dry October, provisional data, not a warning service.
   - How FloodLead will be judged: held-out floods, the four comparators including the official NWS warnings, and a protocol written before training.
   - What changed since Build Session 2.
7. **F4 replay refresh-ahead; F2 reboot evidence.**

## Part 2 — History and training sets (PR 2, overnight)

The goal is leakage-safe datasets that let Stage 4 train and walk-forward test a model on the Nooksack system and on the Fraser Valley gauges.

1. **ECCC daily history.** Daily mean level and flow, plus annual peaks, for all BC stations with real-time data (record 2), into new tables. Record row counts, years per station and size on disk.
2. **Rainfall: approved by the human on Oct 9 ("approve all").** Write each source's usage-rights record in `data-contract.md` **before** code depends on it, after checking its current terms yourself; record the terms URL and the date you checked.
   - (a) ECCC hourly climate observations (OGL-Canada), for stations in and near the Fraser Valley and Nooksack basins.
   - (b) NOAA NCEI hourly station observations and NRCS SNOTEL hourly precipitation (US public domain), for the Nooksack basin.
   - (c) Open-Meteo historical weather (reanalysis) and historical forecast (archived *as-issued* model runs) APIs, for basin-average rainfall. The terms are CC BY 4.0 and free for non-commercial use; record that a commercial FloodLead would need a paid plan or a swap.
   - Find out and record **from which date as-issued forecasts exist** for our basins. That date decides which floods can be replayed with forecast rainfall (fair) and which only with observed rainfall (an "oracle" upper bound that `evaluation.md` requires to be labelled).
   - Measure each source's publication latency (when an hour's value becomes available).
   - Basin averages: define each basin's polygon or point set, and save it with its source.
3. **The official NWS flood warnings that were actually issued.** NWS text products are US public domain. The Iowa Environmental Mesonet (Iowa State University) keeps a free public archive of them. **This source needs the human's approval:** use it only if the relay message that delivered this prompt says "IEM approved"; otherwise skip it and record that. If approved, add its usage-rights record first.
   - **Access:** `https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py?pil=FLWSEW&sdate=…&edate=…&fmt=text` (also `FLSSEW`).
   - **Parse:** each product's issuance time, its P-VTEC (action, event number) and the H-VTEC for `NRKW1` (also `NKSW1`, `NREW1`, `NOEW1`): severity, and forecast flood begin, crest and end times.
   - **Build:** an "official warning timeline" for every event in the history.
   - **Supervisor's spot check (approximate; verify it):**
     - **Dec 2025:** the first North Cedarville flood warning came about 05:40–06:10 PST on Dec 10 (≈ 13:40–14:10Z) and forecast flooding from ≈ 20:28Z. The river actually crossed minor stage at 20:15Z, so official lead ≈ 6 h.
     - **Nov 2021:** the first warning came about 13:28 PST on Nov 14 (≈ 21:28Z) and forecast flooding from 22:18Z. The river crossed minor stage at 21:30Z, so official lead ≈ 0 h. The "major" upgrade came about 02:07 PST on Nov 15 (≈ 10:07Z), against a major crossing at 23:45Z.
   - These official times are the comparator FloodLead has to beat or complement. Report them as found.
4. **Upstream links.** For North Cedarville and each Fraser Valley target gauge, list the upstream gauges with typical travel times measured from the history (lagged cross-correlation of rises) and the source of each link.
5. **Leakage-safe training sets.**
   - **Nooksack**, 15-min data, 2004 → now.
     - Targets: North Cedarville level at 1–48 h, and crossing of the official stages within 6/12/24/48 h.
     - Features: North Cedarville and upstream gauges; observed rainfall up to issue time; as-issued forecast rainfall only where it exists; season; antecedent conditions.
     - Every feature is lagged by its source's **measured publication latency** (USGS ~15–60 min, ECCC 40–90 min, rainfall as measured in item 2), so a training row sees only what a live forecast would have seen.
     - Two variants, never mixed:
       - `honest`: past observations, plus as-issued forecasts where they exist;
       - `oracle`: future *observed* rainfall standing in for a forecast. It is an upper bound only, and is always labelled.
   - **Fraser Valley BC gauges:** a daily dataset from the history, plus the 5-min data since Sep 2026.
   - **Splits:** by water year. The Nov 2021 and Dec 2025 floods are held out untouched until the single final run in Stage 4 (`evaluation.md`).
   - **Features table:** for each feature, its source, its latency, and why it is available at issue time.
   - **Revisions:** say how revisions are handled. Approved history is not what was visible in real time; label it so.
6. **Event catalogue.** Every crossing of the official stages (Nooksack) and of the typical yearly peak (BC) in the history, with times. For the Nooksack events, also give:
   - the overflow onset at SR 544, where the gauge existed;
   - the first official NWS warning for that gauge, and its forecast begin and crest times (item 3).

   These are the labels and comparators Stage 4 is judged on.
7. **Pre-registered evaluation protocol: write it before any model is trained.** `docs/evaluation-protocol.md` fixes, in advance:
   - **Data:** the training, validation and held-out periods; the two held-out floods; which variant (`honest` or `oracle`) each result uses.
   - **Metrics:**
     - level skill against pure persistence (fair CRPS and MAE at 6/12/24 h, overall and on rising limbs);
     - crossing probabilities (Brier, reliability);
     - **hours of warning** at minor/moderate/major stage and at overflow onset;
     - false alarms per season over all test years.
   - **Alert rule:** how it is chosen (probability threshold and persistence of the alert), on validation years only.
   - **Comparators:** persistence, 3 h trend, the gauge-watch rule and the official NWS warnings.
   - **Uncertainty:** bootstrap by event or by water year.
   - **The kill criteria** from `evaluation.md`.
   - **Reporting:** the exact table that will be published, whatever it shows, including events where FloodLead does worse.

   Commit it, record its git commit and sha256 in the stage doc, and mark it **frozen**. The supervisor reviews it before Stage 4 starts. Stage 4 may not change it without a dated, logged amendment.

## Tests

- Fair CRPS: exactness for point forecasts; the bias table on synthetic distributions.
- Feedback: rate limit, size limit, no HTML, encryption round trip, never in logs.
- Typical yearly peak: computation on a fixture, and the datum-check rule.
- Datasets: a leakage test (no feature timestamp after `issue_time − latency`); split integrity (no held-out event in training).
- API contract tests for every new endpoint; the app smoke test, plus the 375 px scroll-width check in `scripts/screenshots.cjs`.

## Acceptance criteria

| AC | Criterion | Evidence |
|---|---|---|
| AC-1 | Fair CRPS live: bias table; all scores recomputed; the summary shows fair CRPSS and MAE skill against naive, with n | test output + API |
| AC-2 | Feedback works end to end: submitted from the app on the public URL, read back with `floodlead feedback list` (text decrypted only there); GitHub template live | screenshots + CLI output (no real personal data) |
| AC-3 | Fraser Valley list and BC typical yearly peaks: ≥ 5 Fraser Valley gauges with a level, or a stated reason; counts of stations computed, flagged and rejected | API + screenshot |
| AC-4 | Ledger records the new thresholds before first use; chain still verifies from the API and from GitHub alone | verifier output |
| AC-5 | Track-record page and help panel on the public URL, desktop and 375 px, 0 console errors, no horizontal scroll | screenshots + scroll width |
| AC-6 | README Build Session 3 section; PR 1 merged before 01:00 UTC (supervisor) | link |
| AC-7 | Reboot evidence (F2), replay refresh-ahead (F4), `statement_timeout` (F3) | outputs |
| AC-8 | ECCC daily history and annual peaks loaded into new tables (counts, size) | SQL |
| AC-9 | Rainfall: the approved sources ingested with licence records, latencies and as-issued forecast start dates; the NWS warning archive parsed (if "IEM approved") with the official warning timeline per event | data-contract diff + SQL + table |
| AC-10 | Training sets (`honest` and `oracle`, labelled) and features table; leakage and split tests pass; event catalogue with official warning times; frozen `docs/evaluation-protocol.md` (commit and sha256) | files + test output |
| AC-11 | `ruff` and `pytest` pass, with the DB tests run | output |
| AC-12 | ≥ 10 decisions; stage doc in most commits, spread across the stage; contract files updated | `git log --stat` |

## Out of scope

Training models (Stage 4), live model issuance (Stage 5), alerts or messaging of any kind (Stage 7), accounts. Do not reboot the VM in this stage.

## When done (each PR)

Mark the PR ready and print the STAGE REPORT for that part. "Supervisor checks" lists the URLs and commands that verify it from outside.
