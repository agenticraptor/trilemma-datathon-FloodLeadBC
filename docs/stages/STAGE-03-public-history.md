# Stage 03 — Working in public, fair scoring, history and training sets

> Living document. Written while the stage is built, committed with the code. Newest work-log entries at the bottom.

| | |
|---|---|
| Branch | `stage-03-public` (PR 1), then `stage-03-history` from the merged `main` (PR 2) |
| Started | 2026-10-09 12:42 PT (19:42 UTC) |
| Finished | (fill at end) |
| Prompt | `docs/build/prompts/STAGE-03-public-history.md` |
| Status | part 1 passed QA (PR #5, `fa0b2a7`); part 2 ready for QA (PR #6) |

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

### Part 2 progress log (branch `stage-03-history`; merged with part 1's doc when PR 1 is in `main`)

- `13:33–13:39` — In a separate worktree (`../trilemma-part2`), so part-1 deploys never build part-2 code:
  - **NWS VTEC parser** (`src/floodlead/history/nws.py`, migration 011): products split on `\x01`, segments on `$$`, P-VTEC paired with the following H-VTEC, issuance from the local time line cross-checked against the WMO DDHHMM.
    - Tests on real Nov 2021 products (`tests/fixtures/iem_FLWSEW_2021_excerpt.txt`).
    - **The first North Cedarville flood warning of Nov 2021 (ETN 78, NEW) was issued at "1150 AM PST Sun Nov 14 2021" = 19:50Z**, WMO `141950`. Its H-VTEC: severity 2 (moderate), forecast flood begin 22:18Z, crest Nov 15 18:00Z. The supervisor's approximate ≈ 21:28Z is corrected here; the full timeline comes in part 2. The "major" upgrade (EXT, severity 3, record `NR`) was at 10:07Z Nov 15, as the supervisor said.
  - **Rainfall parsers** (`src/floodlead/history/rain.py`, migration 012): ECCC climate, NCEI FM-15 AA1, SNOTEL accumulation → hourly (PST → UTC), and Open-Meteo, all with UTC hour-ending timestamps.
    - Tests: `tests/test_rain.py`.
  - Not deployed; production loads wait for PR 2.
- `13:40` — **From which date as-issued forecast rainfall exists (part 2 item 2).** Binary search with one-day requests at the `nooksack-nf` point (48.90, −121.80), Open-Meteo `best_match`, 27 calls in all; "data" means at least 12 non-null hours that day:

  | Series | First day with data | Probes | What it is |
  |---|---|---|---|
  | historical-forecast API `precipitation` | **2018-01-01** | 11 | Stitched from the first hours of each archived model run, so it is close to an analysis. It is **not** a forecast issued before our issue time for hours ahead |
  | previous-runs API `precipitation_previous_day1` | **2024-01-19** | 8 | What was forecast for that hour **one day earlier**: as-issued, lead ≈ 24 h |
  | previous-runs API `precipitation_previous_day2` | **2024-01-20** | 8 | As forecast two days earlier, lead ≈ 48 h |

  **Consequence for fair replays:**
  - Dec 2025 can be replayed with rainfall forecasts as they were issued 1–2 days ahead.
  - Nov 2021 and earlier floods can only use observed rainfall up to the issue time (`honest`). Future observed rainfall stands in only in the labelled `oracle` variant.
  - The historical-forecast series is not used as an "as-issued" input for lead times beyond its own run age. Decided in part 2.
- `13:42–13:45` — **Upstream links (part 2 item 4)**, `src/floodlead/history/links.py`, read-only on production (hourly means per water year, constant bounds, 86.7 s + 21.3 s). Results in `docs/data/upstream_links.json`. Synthetic known-delay test: `tests/test_links.py` recovers a 5 h lag.

  | Pair (hourly, 2004–2026) | Rise correlation: best lag, r, n hours | Peak-to-peak: median (IQR), n events |
  |---|---|---|
  | NF Nooksack near Glacier → North Cedarville | 4 h, 0.703, 82,632 | 4 h (2–6), 237 |
  | MF Nooksack near Deming → North Cedarville | 4 h, 0.759, 81,372 | 5 h (4–6), 234 |
  | SF Nooksack at Saxon Bridge → North Cedarville | 4 h, 0.816, 77,997 | 4 h (3–5), 216 |
  | North Cedarville → Everson | 2 h, 0.930, 43,577 | 1 h (1–2), 116 |
  | North Cedarville → Ferndale | 6 h, 0.834, 82,140 | 7 h (6–9), 215 |

  **The upstream Nooksack gauges lead North Cedarville by only about 4–5 h.** Warnings longer than that have to come from rainfall (observed and forecast), not from routing.

  | Pair (daily means; lags under a day not resolvable) | Overlap (days) | Rise corr. (lag, r) | Peak-to-peak median (IQR), n |
  |---|---|---|---|
  | Chilliwack above Slesse Ck → Vedder Crossing | 5,079 | 0 d, 0.939 | 0 d (0–0), 71 |
  | Slesse Ck → Chilliwack at Vedder Crossing | 4,863 | 0 d, 0.905 | 0 d (0–1), 72 |
  | Chilliwack Lake outlet → Vedder Crossing | 5,055 | 0 d, 0.497 | 0 d (0–0), 72 |
  | Sumas near Sumas, WA (USGS) → Sumas near Huntingdon | 427 | 0 d, 0.906 | 0 d (0–0), 14 |
  | North Cedarville → Sumas near Huntingdon | 4,925 | 0 d, 0.639 | 0.5 d (0–1), 80 |
  | Fraser above Texas Ck → Fraser at Hope | 5,016 | 0 d, 0.692 | 1 d (0–1), 64 |
  | Thompson near Spences Bridge → Fraser at Hope | 4,964 | 0 d, 0.611 | 1 d (0–2), 65 |
  | Fraser at Hope → Fraser at Mission (tidal) | 10,885 | 0 d, 0.706 | 1 d (0–2), 102 |
  | Coquihalla above Alexander Ck → below Needle Ck | 4,990 | 0 d, 0.857 | 0 d (0–0), 57 |

- `13:45–13:46` — **Official NWS warnings for North Cedarville (part 2 item 3), first read of the whole archive** (read-only, in memory).
  - 5,181 products parsed; 1 unparsed (to inspect); 156 VTEC records with H-VTEC `NRKW1`, in 36 FL.W events from 2006 to 2026.
  - **The supervisor's spot checks, verified against the raw products:**

    | Flood | First NRKW1 flood warning (VTEC NEW) | Its forecast flood begin | Supervisor's estimate | What the estimate was |
    |---|---|---|---|---|
    | Dec 2025 (ETN 47) | **06:17Z Dec 10** ("1017 PM PST Tue Dec 9 2025", FLWSEW `WGUS46 KSEW 100617`), moderate | 20:28Z Dec 10 | ≈ 13:40–14:10Z | an EXT statement (FLSSEW `101340`, "540 AM PST Wed Dec 10") |
    | Nov 2021 (ETN 78) | **19:50Z Nov 14** ("1150 AM PST Sun Nov 14 2021"), moderate | 22:18Z Nov 14 | ≈ 21:28Z | to be matched in the full timeline |

  - If the observed minor-stage crossings are 20:15Z Dec 10 and 21:30Z Nov 14 (to be verified from our own 15-min data in the event catalogue), **the official lead is ≈ 14.0 h in Dec 2025 and ≈ 1.7 h in Nov 2021**, against the supervisor's ≈ 6 h and ≈ 0 h. The bar FloodLead has to beat in Dec 2025 is much higher than assumed.
  - The "major" upgrade in 2021 (EXT, severity 3) at 10:07Z Nov 15 matches the supervisor.
  - Parser fixes found on the way, each with a test:
    - older products write months in capitals ("DEC");
    - correction products carry a BBB indicator (`CCA`) on the WMO line, which had been read as the product id;
    - severity is now ranked 3 > 2 > 1 > N/0/U, not compared as text.

- `13:49–13:52` — Part-2 code for addendum 1:
  - the forecast crest, observed crest and stage from each segment's text (`FC_CREST` skips "a previous crest of"). The 2021 first warning gives **148.9 ft**, as the supervisor found. In 156 NRKW1 segments, 57 say "crest near", 14 "crest of", 14 "crested at" (observed), 6 "previous crest of" (history); 49 have no crest phrase (mostly CAN/EXP);
  - `src/floodlead/scorecard.py` and migration 013, with tests on a synthetic event.
- `13:52–13:54` — **Which archived products carry values (addendum item 3.1).** One request each to IEM for Dec 1–15 (or 9–11), 2025:

  | PIL | Products | Use |
  |---|---|---|
  | FFASEW | 17 | Flood watches → the "heads-up" relay tier. Added to the downloads |
  | ESFSEW | 5 | Hydrologic outlooks. Added to the downloads |
  | RVFSEW, HYDSEW, RVSSEW, RRSSEW | 0 | — |
  | RVFPTR, RVFSEA, RVFNRK, RVDPTR, RVFSTR | 0 | — |
  | HYDPTR | 2, no NRKW1 line | — |

  No archived RVF/HYD product with NRKW1 values was found under these PILs. The scorecard's forecast values are therefore the crest and timing stated in the FLW/FLS products: text crests, plus H-VTEC begin, crest and end times. NOAA's 6-hourly forecast series is archived by FloodLead only since Oct 7, 2026 (Stage 1).

- `14:00` — **ECCC hourly precipitation completeness** (archived climate-hourly pages, 2004–2026; temperature is 99–100 % complete everywhere):

  | Climate ID | Station | Hours | Precip non-null |
  |---|---|---|---|
  | 1100030 | Abbotsford A (to 2012) | 74,260 | **0.0 %** |
  | 1100031 | Abbotsford A (2011–) | 125,309 | **0.0 %** |
  | 1100032 | Abbotsford A (2016–) | 93,842 | 12.4 % |
  | 1106178 | Pitt Meadows CS | 199,241 | 73.2 % |
  | 1108910 | White Rock CS | 198,884 | 50.7 % |
  | 1113541 | Hope (AUT), to 2012 | 61,897 | 0.0 % |
  | 1113542 | Hope A | 130,595 | 81.2 % |
  | 1113543 | Hope Airport | 123,859 | 95.4 % |

  **Abbotsford has essentially no hourly precipitation in ECCC's climate archive.** The live probe also found its newest hour about 14 h old with no precipitation. So the Fraser Valley rain features cannot rest on the airport next to Sumas Prairie: Hope and Pitt Meadows bracket the valley, with KBLI and SNOTEL on the US side. Open-Meteo reanalysis serves as the oracle and the basin average.

- `14:01–14:08` — **Draft PR #6 opened** (`stage-03-history`, base `main`). Until PR #5 merges it also shows part 1; the PR body says so. It was opened so that part-2 code runs only from an open PR.
  - Part-2 code runs from its own image tag, `floodlead-app:part2` (built from this worktree), in one-off `docker run --rm` containers. The live services keep `floodlead-app:latest` (part 1), so no part-2 code reaches them.
  - `floodlead migrate` → `011_nws_products.sql`, `012_rain.sql`, `013_official_scorecard.sql` (new tables only).
  - `history download iem-nws` → 46 new requests (FFASEW and ESFSEW, 2004–2026), 3,865,352 B; 46 skipped.
  - `history load nws` → **7,278 + 15 products, 11,018 VTEC records** in 22.8 s. 28 unparsed: 27 spring/summer water-supply outlooks (ESFSEW) with irregular date lines ("June 20 2017", "Thu July 8, 2021") and 1 empty correction (FLSSEW 2006). None is a flood product.
  - Parser fix: full month names ("JULY"); test added.
- `14:08` — **Official-forecast scorecard built** (`floodlead history build scorecard`, 2.3 s; `official_scorecards` row 1. The final build at 23:02Z is row 2, the one served). The addendum's corrected numbers are reproduced from the archive and our gauge record:

  | | Nov 2021 (ETN 78) | Dec 2025 (ETN 47) |
  |---|---|---|
  | First North Cedarville warning | 19:50Z Nov 14, forecast crest **148.9 ft** | 06:17Z Dec 10, forecast crest **148.4 ft** |
  | Observed crest (our USGS record) | **150.76 ft** (major) | **150.44 ft** (major); the review cites ≈ 150.49–150.5 |
  | Observed minor crossing | **21:30Z Nov 14** | **20:15Z Dec 10** |
  | First warning's lead before minor | **1.67 h** | **13.97 h** |
  | First "major" product | 10:07Z Nov 15 | 01:32Z Dec 11 (5:32 PM PST Dec 10) |
  | SR 544 overflow onset (replay definition) | 02:25Z Nov 15 | 00:45Z Dec 11 |
  | "Major" relative to the onset | **7.7 h after** | **0.8 h after** (the review: ~3 h after the Emerson Rd rise at 2:30 PM) |

  North Cedarville, all archived warnings: 36 events, of which 32 are scored and 4 (2006-11 to 2007-03) predate our level record. Crest error of the official forecast crest by lead before the observed crest:

  | Lead | Products | Events | Bias (ft) | MAE (ft) | Category right | Crest-time MAE (h) |
  |---|---|---|---|---|---|---|
  | 0–6 h | 31 | 24 | +0.50 | 0.82 | 38.7 % | 3.6 |
  | 6–12 h | 12 | 12 | +0.87 | 1.05 | 25.0 % | 4.4 |
  | 12–24 h | 11 | 7 | **−0.59** | 1.09 | 27.3 % | 5.2 |
  | 24–48 h | 4 | 3 | **−1.48** | 1.49 | 25.0 % | 4.4 |

  - First warning before minor stage: median **1.67 h**, range −1.52 to 23.7 h, n = 19 events that reached minor.
  - Small n at the longer leads (7 and 3 events). The pattern matches the review: low a day out, slightly high in the last hours.
  - Ferndale (NKSW1): 16 events. Everson (NREW1) and the overflow (NOEW1) have no point warnings; the Everson overflow warnings are areal (FA) products and feed the relay tiers.
  - The "after the crest" bin (crest-time MAE 288 h) is not a forecast. It is shown only for completeness, and dropped from the README table.

- `14:09–14:19` — **Relay replay** (`floodlead history build relay`, 27 s) and the **rain load** (`history load rain`).
  - The rain load's first run failed after 2.9 s, with nothing written: `relation "_stage" already exists`. The same transaction bug as the CRPS recompute: without autocommit, the per-payload `ON COMMIT DROP` temp table outlived each payload.
    - Fixed with autocommit per payload. `test_load_two_overlapping_payloads` **fails without the fix and passes with it**.
    - Rerun: `{'eccc-climate': 1007776, 'ncei': 188757, 'openmeteo-archive': 660264, 'openmeteo-histfc': 475008, 'openmeteo-prevruns': 264576, 'snotel': 587425}` rows in 450.5 s. The Open-Meteo reanalysis download was still running, so it is reloaded at the end.
  - **Superseded: addendum 1 examples, kept for the record (relay v1, counted by minor-stage event; see D-03.23 for relay v2, counted by alert).** Relay tiers, 13 North Cedarville minor-stage events since the SR 544 gauge began (7 with overflow). The prepare window was first 7 days, which let in a warning from an earlier event (a 106.8 h "lead"). It is now 72 h before the minor crossing, as in the catalogue:

    | Tier | Fired | Hits / overflow events | False alarms | POD | FAR | Lead before overflow onset (h) | Daylight share |
    |---|---|---|---|---|---|---|---|
    | Heads-up (NWS flood watch naming Whatcom) | 12 | 7 / 7 | 5 | 1.00 | 0.42 | 68.9, 69.1, 84.0, 101.2, 101.5, 120.6, 151.9 | 0.75 |
    | Prepare (NRKW1 warning ≥ minor, or Everson-overflow warning) | 13 | 7 / 7 | 6 | 1.00 | 0.46 | 2.2, 6.6, 7.1, 9.3, 12.0, 13.4, 18.5 | 0.46 |
    | Move (SR 544 onset, or North Cedarville ≥ minor and rising) | 13 | 7 / 7 | 6 | 1.00 | 0.46 | 0.1, 3.8, 4.5, 4.9, 5.2, 6.0, 6.4 | 0.62 |

    These are relay value, with no model. With 7 overflow events, the exact 95 % interval on POD 7/7 is 0.59–1.00. Comparisons with Abbotsford's times and the 7-hour rule are in the relay output (`/srv/floodlead/datasets/relay.json`) and go into the part-2 report.
- `14:19` — **`#/official-scorecard` page** ("How accurate were the official forecasts?", background frontend agent).
  - **My mistake:** a `git commit -a` for the NWS month-name fix (`638d6d3`, pushed) also swept in the agent's unfinished draft of this page. Pushed history is not rewritten; the final page is committed separately.
  - `/v1/official-scorecard` was added to the snapshot export; slug test 19 passed.

- `14:20` — **Event catalogue** (`floodlead history build catalogue`, 30.7 s → `/srv/floodlead/datasets/catalogue.json`):
  - **Nooksack:** 20 North Cedarville minor-stage events since 2007, 8 of them with an SR 544 overflow onset (where the gauge existed), and a first NWS North Cedarville warning found for all 20.
    - Each event carries its crossings, crest, onset, and the first warning's issuance, forecast begin, crest time, crest value and lead before minor.
    - Examples: Dec 2025 — minor 20:15Z Dec 10, crest 150.44 ft, major 10:00Z Dec 11, onset 00:45Z Dec 11, first warning 06:17Z (148.4 ft forecast), lead 13.97 h. Nov 28, 2021 — first warning 09:29Z, lead 13.27 h.
  - **BC:** typical-peak crossings at 310 stations with an `ok` or flagged value. 2,576 station-years had an annual instantaneous maximum at or above the station's typical yearly peak (about half the years, by construction), and 274 stations had daily means at or above it on at least one day.

- `15:05` — Open-Meteo downloads finished, 22:04:56Z; `hist-openmeteo` exit 0. 272 requests, 0 errors:
  - prevruns 32 (12.6 MB, 19:50–20:05Z);
  - histfc 56 (22.0 MB, 20:05–20:33Z);
  - archive 184 (77.5 MB, 20:33–22:04Z), at 1 request / 30 s.
- **Rainfall publication latency (part 2 item 2).** Hourly probes (`scratchpad/latency_probe.py`, 16 runs scheduled), the first two at 20:40Z and 21:40Z:
  - SNOTEL Wells Creek: newest hour-ending value **40 and 41 min old**;
  - ECCC Abbotsford A: newest hour 07:00Z, **about 14 h old, with no precipitation value**;
  - NCEI KBLI: **no records in the last 7 days**, so it is a history source only;
  - Open-Meteo "archive": values up to 23:00Z today, so its recent hours are model-filled, not reanalysis.
  - `data-contract.md` latency fields updated.
- **AC-8 numbers** (new tables):
  - `eccc_daily`: 7,825,554 rows, 448 stations, 1903-04-01 → 2026-06-09, median 53 years per station (1–123), **665 MB**;
  - `eccc_annual_peaks`: 37,789 rows, 962 BC stations, 1923–2025 (7,285 annual level maxima), 4.9 MB;
  - `typical_peaks`: 256 kB;
  - `nws_products` 14 MB, `nws_vtec` 9.1 MB.

- **Superseded: addendum 1 examples, kept for the record.** **Relay tiers against Abbotsford and the 7-hour rule** (`relay.json`). Abbotsford's times come from the status-quo review: reconstructed, with ranges, PST shown as UTC.

  | | Nov 2021 | Dec 2025 |
  |---|---|---|
  | Heads-up: NWS flood watch naming Whatcom (FA.A NEW) | 20:56Z Nov 10 (12:56 PM PST, day); 101.5 h before the onset | 00:10Z Dec 6 (4:10 PM PST Dec 5, day); 120.6 h before the onset |
  | Prepare: first NRKW1 warning ≥ minor | 19:50Z Nov 14 (11:50 AM PST, **day**); 6.6 h before the onset | 06:17Z Dec 10 (10:17 PM PST Dec 9, **night**); 18.5 h before the onset |
  | … before Abbotsford's first alert | **12.7 h** (alert ~12:30 AM Nov 15) | **17.7–19.1 h** (alerts ~4:00–5:20 PM Dec 10) |
  | … before Abbotsford's first order | 29.2–32.2 h | 24.7 h (order ~11 PM Dec 10) |
  | Move: North Cedarville ≥ minor and rising | 21:30Z Nov 14 (day); 4.9 h before the onset; 11.0 h before the alert | 20:15Z Dec 10 (day); 4.5 h before the onset; 3.8–5.1 h before the alert |
  | SR 544 onset (our gauge record) / 7-hour-rule arrival | 02:25Z / 09:25Z Nov 15 | 00:45Z / 07:45Z Dec 11 (the review bounds the actual crossing at ~10–20 h after the onset) |

  - The prepare tier fired at night in 2025. Held to the next sunrise (15:51Z Dec 10), it would still have come about 8–9 h before the City's alert.
  - All of this is relay value, with no model, as addendum 1 requires. It is replayed from archived products, with today's rules applied to the past.

- `15:05–15:35` — **A data defect found and fixed before the datasets were trusted.**
  - The rain reload at 22:05Z exited 1 after 234 s (`json.decoder.JSONDecodeError`). My `tail` hid the error, so the first dataset build (22:09–22:26Z) ran on partly reloaded rain tables. That build is discarded.
  - Cause: **4 of 184 Open-Meteo reanalysis requests returned HTTP 200 with the body `Unexpected error while streaming data: timeoutReached` (53 B)**. They were recorded as `ok`: nooksack-lower 2020 and 2021, coquihalla-hope 2022 and 2023.
  - Fixes:
    - the downloader now validates JSON bodies for JSON sources, and an invalid body is recorded as `error` and retried on the next run (`tests/test_history_download.py`);
    - the rain loader skips invalid payloads and reports them instead of failing;
    - the 4 manifest rows were set to `error`; the refetch gave 4 × ~435 kB, 0 errors (22:32–22:34Z).
  - Rain reload and dataset rebuild rerun (results below).

- `16:01–16:10` — **Training sets rebuilt and checked; protocol frozen.**
  - The rain reload is complete: Open-Meteo reanalysis 1,597,056 rows.
  - Datasets, image commit `f502b49`: Nooksack hourly honest and oracle, 193,007 rows each; Fraser Valley daily 93,805 rows each. The sha256 values are in the protocol.
  - `python3 scripts/check_datasets.py /srv/floodlead/datasets` → **0 violations on every row** of both variants (leakage cut-offs, NWS issuance ≤ t, held-out flags), `RESULT OK`.
  - **Finding:** North Cedarville never reached 150 ft outside the two held-out floods (0 development events; 5 at ≥ 148 ft; 3 development overflow events). The protocol fixes how this is handled: P(≥ 150 ft) comes only from the level distribution, and is reported descriptively on n = 2.
  - **`docs/evaluation-protocol.md` FROZEN at commit `45367d1171b781656c2d859a8155fac254d79ed4`, sha256 `ecdefe0bcdb27ff00508c58da9d2819b13ad14b2c9e2febfe86a2741e230abad`.**

  The Sumas USGS–ECCC overlap is only 427 days. The USGS hourly level at Sumas, WA needs at least 18 hours a day to make a daily mean, and its level record is short. As found.

## Decisions

### D-03.1 — History downloads: archive raw first, parse later; one paced, resumable task list per source

- **Context:** Part 2 needs decades of ECCC daily data, rainfall and the NWS warning archive. The prompt asks to start the downloads at the very beginning, while part 1 is built, as one-off compose services that are paced and resumable.
- **Options considered:**
  - (a) download and parse in one step into tables;
  - (b) download every payload unchanged into the raw archive, with a manifest table, and parse later from the archive.
- **Choice:** (b).
  - `floodlead history download <source…>` runs a fixed task list per source. Tasks are one station-year, one product-year, or one OGC page; follow-up pages are queued from each page's `numberReturned`.
  - Each response goes through `archive.store` (gzip, sha256, `raw_objects`) and a row in a new `history_downloads` table, keyed by `(source, key)`. Tasks already `ok` or `empty` are skipped, so a run can stop and restart at any time.
  - Pacing per source, well under the published limits:
    - ECCC OGC API: 1 request/s;
    - IEM: 1 request / 2 s;
    - SNOTEL: 1 request / 2 s;
    - NCEI: 1 request / 3 s;
    - Open-Meteo: 1 request / 30 s, ≈ 52 calls/min against a limit of 600 (each point-year counts as ≈ 26 calls).
  - Runs as `docker compose run -d --name hist-… backfill floodlead history download …`. The `backfill` service has `restart: "no"`.
- **Why:**
  - The downloads start within the first hour and need no parser decisions yet.
  - Parsing bugs can be fixed and re-run without refetching.
  - The raw payloads stay as the evidence for every parsed number, as in Stage 1.
- **Reversibility / cost:**
  - Downloads are additive and idempotent.
  - Archive cost: about 2 MB per OGC page or station-year (uncompressed), compressed on disk.
- **Follow-ups:** part 2 writes the parsers into new history tables (never `observations`, F3).

### D-03.2 — Usage-rights records for the new sources, checked the same day

- **Context:** AGENTS.md requires a record before code depends on a source. The prompt adds: check the current terms yourself, and record the URL and the date.
- **Choice:** five records in `data-contract.md`, each naming the page fetched on 2026-10-09:
  - ECCC climate-hourly: ECCC Data Servers End-use Licence v2.1.1 on this route; OGL-Canada on open.canada.ca.
  - NCEI Global Hourly: **US stations only**. The readme states that non-US ISD data fall under WMO Resolution 40, so Canadian stations come from ECCC directly.
  - NRCS SNOTEL: a US Government work. The NRCS policy pages returned 404 that day; the record says so.
  - Open-Meteo: CC BY 4.0, and the free API is **non-commercial**. A commercial FloodLead needs a paid plan or a swap. Marked 🟡.
  - IEM: "in the public domain and may be used freely by anyone for any lawful purpose".
- **Why:** each record shows exactly what was checked, and what could not be checked.
- **Reversibility / cost:** the Open-Meteo dependency is the only non-commercial one. It stays a training input, and its replacement path is written down.
- **Follow-ups:** measure each source's publication latency (part 2, item 2).

### D-03.3 — Which stations and points the downloads cover

- **Context:** the task lists need concrete stations and points.
- **Probes (19:55–20:05Z):**
  - **ECCC annual peaks, BC:** 37,806 rows (level and flow, maximum and minimum).
  - **ECCC daily means:** for example 08MH029 has 30,367 days, ending 2024-12-31 (approved HYDAT).
  - **ECCC hourly climate stations** in the bbox −122.8 … −121.2, 48.9 … 49.5:
    - Abbotsford A (3 IDs, 1953 → now);
    - Hope (4 IDs);
    - Pitt Meadows CS;
    - White Rock CS.
  - **ISD stations** within 48.6–49.1N, −122.8 … −121.3: KBLI is the only US one with long history.
  - **SNOTEL in the Nooksack:**
    - Wells Creek 909 (NF, 1995);
    - MF Nooksack 1011 (2002);
    - Elbow Lake 910 (SF, 1995).
    - Hourly data were present on 2021-11-13.
  - **Open-Meteo:**
    - reanalysis returned data;
    - historical forecast: no data on 2016-01-10, data on 2021-03-20 and 2022-06-01;
    - previous runs: `previous_day1/2` empty on 2023-06-01, present on 2024-02-01.
- **Choice:**
  - all BC real-time ECCC stations for daily means; all BC annual peaks;
  - the 8 climate IDs listed;
  - KBLI;
  - the 3 SNOTEL sites;
  - 8 basin points (4 Nooksack, 4 Fraser Valley; `history/tasks.py`):
    - Open-Meteo reanalysis from 2004;
    - historical forecast from 2020;
    - previous runs from 2023.
  - The years before each start date are requested anyway and recorded as found (empty or null), which also measures the start dates.
- **Reversibility / cost:** adding a point or station later is one more task; nothing is lost.

### D-03.4 — Fair CRPS: rebuild the CDF from the quantiles, exponential tails, exact integral (F1)

- **Context:** the quantile score is exact for a point forecast, but about 19 % low for a spread forecast. So every CRPSS against `persistence-naive` was inflated (the supervisor's F1). The live ECCC h1 CRPSS of +0.30 sat next to a median that was worse than naive.
- **Options considered:**
  - (a) a piecewise-linear CDF between quantiles, with these tail rules:
    - point masses at the 0.05/0.95 quantiles;
    - linear extension of the edge slope down to F = 0 and up to 1;
    - exponential tails with the edge segment's density;
  - (b) fit a parametric distribution (normal or skew-normal) to the quantiles;
  - (c) keep the quantile score and rescale it.
- **Measured** (prototype, 3,000 truth draws per case, 7 levels; bias against the exact CRPS of the true forecast distribution):

  | Case | exp tails | linear tails | point masses | quantile score |
  |---|---|---|---|---|
  | calibrated normal | +0.0 % | +0.1 % | +0.2 % | −19.4 % |
  | log-normal (s = 0.5) | +0.1 % | +0.2 % | +0.3 % | −18.0 % |
  | under-dispersed (sd 0.5 vs 1) | −0.2 % | +0.2 % | +0.7 % | −14.5 % |
  | over-dispersed (sd 2 vs 1) | +1.2 % | +1.2 % | +1.0 % | −12.6 % |

  With 19 levels, all three tail rules are within ±0.4 %.
- **Choice:** (a) with **exponential tails**:
  - `F(x) = τ₁·exp(λ(x − q₁))` below q₁, with `λ = f₁/τ₁`, and symmetrically above q_K;
  - every piece is integrated in closed form (`src/floodlead/crps.py`);
  - a zero-width edge segment becomes a point mass, so a point forecast gives exactly |y − q|.
- **Why:**
  - the smallest bias in the skewed and under-dispersed cases;
  - exact and deterministic: no sampling, and no distribution family assumed (b would favour models whose shape matches the family);
  - (c) cannot fix the point-vs-spread asymmetry, which is the actual problem.
- **Kept:**
  - `crps_qs` (the quantile score) as a secondary column, in `/v1/scores/summary` as `mean_crps_qs_m`;
  - MAE-of-median skill against both references (`mae_skill`, `paired_mae`);
  - `persistence-naive` in `/v1/scores/official` (naive rows now carry their persistence-v1 row's NOAA point).
- **Reversibility / cost:** scores are derived. `floodlead score --recompute-crps` rebuilds `crps` and `crps_qs` from the ledger and the stored truth, idempotently (tested).
- **Follow-ups:** future model versions store 19 quantiles (evaluation.md).

### D-03.5 — Migration 007 (`crps_qs` column) after a dump of the score tables

- **Context:** F1 adds a column to two existing tables and recreates the `all_scores` view. CLAUDE.md requires a `pg_dump` before any migration that touches existing tables.
- **Choice:**
  - `pg_dump -Fc` of the 4 score tables (`forecast_scores`, `forecast_scores_naive`, `score_summaries`, `scorer_runs`) to `/srv/floodlead/backups/pre-007-score-tables-20261009T1955Z.dump`: 2,501,219 B, mode 0440, `pg_restore --list` shows 4 TABLE DATA entries.
  - Not the whole database (4.8 GB): the migration touches only these tables, and they are derived data.
  - Then `ALTER TABLE … ADD COLUMN crps_qs`, and `CREATE OR REPLACE VIEW all_scores`. The view was created with `SELECT *` and would otherwise miss the new column.
- **Reversibility / cost:**
  - Adding a nullable column is instant.
  - The values are recomputed from the ledger, so the dump is the belt-and-braces copy.

### D-03.6 — Feedback: anonymous, text encrypted at rest, append-only; rate limits keyed on the real client IP

- **Context:** part 1 item 2. Build Session 3 visitors must be able to tell us what they think. AGENTS.md says personal data is encrypted, kept in Canada, and never in the ledger, logs or fixtures.
- **Choice:**
  - `POST /v1/feedback` takes `{route, station_id, useful, text ≤ 1,000 chars, app_version}`. Any other field is rejected, including names and emails.
    - Body ≤ 4,096 B, else 413. Control characters are stripped.
    - Response `202 {"status":"received"}`: the text is never echoed or rendered.
  - Table `feedback` (migration 008):
    - the text is a **Fernet token** (AES-128-CBC + HMAC-SHA256), with the key `FEEDBACK_KEY` in `.env`, generated on the VM and never printed;
    - `key_id` = the first 8 hex of sha256(key), for rotation;
    - **no IP address, name, email or phone is stored**;
    - UPDATE, DELETE and TRUNCATE are rejected by triggers.
  - Rate limits, in memory only:
    - per client IP: 5 per 10 min and 20 per day;
    - 300 per hour from everyone together.
  - Health shows counts only (`feedback.total`, `last_24h`, `yes`, `no`).
  - `floodlead feedback list` on the VM is the only reader. It escapes control characters, so no terminal sequences reach the output.
  - A GitHub issue form (`.github/ISSUE_TEMPLATE/feedback.yml`) for people who want a reply. It warns that issues are public.
- **Found and fixed on the way:** the general API rate limiter (Stage 1, 120/min) keyed on `request.client.host`. Behind Caddy that is Caddy's address, so **every visitor shared one bucket**. A dozen people at Build Session 3 could have exhausted it.
  - Both limiters now use `client_ip()`: X-Forwarded-For from a private-network peer. Caddy sets that header to the client address and ignores one sent by untrusted clients.
  - The test client stands in for Caddy in `tests/test_feedback.py`.
- **Why:** the minimum data that makes feedback useful, with no personal data by design. Encryption covers a visitor who types personal details anyway.
- **Reversibility / cost:**
  - `cryptography` is a new dependency (50.0.2).
  - Losing `FEEDBACK_KEY` makes the stored text unreadable (stated in the open issues). It lives only in `.env`, as the other secrets do.
- **Follow-ups:** retention period for feedback text (Stage 7, with the privacy policy).

### D-03.7 — Typical yearly peak: median annual instantaneous maximum level over 2005–2024, with a datum check

- **Context:** part 1 item 4. BC gauges have no official flood stages in our data. People need a level that matters, and it must be honest about what it is.
- **Choice (`src/floodlead/typical_peaks.py`, method `typical-peak-v1`):**
  - **Value:** the median of the annual instantaneous maximum *water level* (ECCC `hydrometric-annual-peaks`, HYDAT) over 2005–2024. Approved HYDAT ends in 2024, so this is the last 20 years.
    - At least 10 years are required.
    - Years marked "Ice Conditions" are left out.
    - The median is reached or exceeded in about half of years. That is the label's claim, and nothing stronger.
  - **Datum check:** a datum change makes old peaks meaningless against today's levels. Today's 30-day median live level (constant time bounds on `observations`) is compared with the daily mean levels (`eccc_daily`) for the same calendar days (Sep 10 – Oct 9) in the last 5 years that have them.
    - **Rejected** if the live median lies outside that range by more than max(0.5 m, half the range).
    - **Flagged** if there is no live level or no same-season history to check against, or if the level already reached the value in the last 30 days.
  - **Stored** in `typical_peaks` with status, n, years, the reason and the checks (`jsonb`). This is apart from NOAA's official thresholds.
- **Result (20:20Z):** 433 BC stations with level → **302 ok, 8 flagged, 1 rejected, 122 insufficient** (fewer than 10 years).
  - Flag reasons:
    - 6 reached the value in the last 30 days;
    - 1 had no same-season daily history;
    - 1 had no live level.
  - Rejected: one station, whose 30-day median of 1.274 m lies outside its same-season range.
  - All 7 Fraser Valley gauges are `ok` (table in the work log).
- **Why the median of annual maxima:** a number that is directly verifiable from public ECCC data, needs no distribution fit, and fits "reached in about half of years" exactly.
  - A 2-year return level from a fitted GEV would be close, but adds a model to explain.
  - A percentile of daily means would understate instantaneous peaks.
- **Reversibility / cost:**
  - A new method version can be added next to `typical-peak-v1`; the table is keyed by method.
  - The datum rule can miss a small datum change (under 0.5 m) and can flag a real but unusual season. Both are stated in the app.
- **Follow-ups:** part 2 uses the same table for the BC event catalogue ("crossings of the typical yearly peak").

### D-03.8 — The thresholds enter the ledger through new model cards, in the same issuance, before first use

- **Context:** forecasts that include the typical-peak threshold must be verifiable. Its values and provenance must be in the ledger before the first forecast that uses them, without changing any existing card or entry.
- **Options considered:**
  - (a) new model cards for `persistence-v1` and `trend3h-v1` whose `params.typical_peak` holds the method, source, period, rules and every `ok` value;
  - (b) a new entry type (for example `threshold_set`), which needs a schema change to the ledger's `entry_type` CHECK and verifier updates;
  - (c) new model names (v2), which would break the continuity of the live scores.
- **Choice:** (a). The issuer already appends a superseding card whenever a model's `params_hash` changes, in the same transaction and at lower seq than that issuance's forecasts.
  - Each card says `change: "typical yearly peak thresholds added or updated (params.typical_peak); forecast method and other parameters unchanged"` and `supersedes_seq`.
  - Each forecast for a station with an `ok` value gets a threshold `{"key": "typical:peak", "kind": "typical", "level_m", "label", "source": "typical-peak-v1 in the model card params (typical_peak)"}`, plus `p_exceed["typical:peak"]` at every horizon.
  - `flagged` and `rejected` values are shown in the app with their reason, but not used in forecasts.
- **Why:**
  - no ledger schema change and no verifier change;
  - the old cards are untouched (tested: the earlier cards are byte-identical after the new ones are appended);
  - "before first use" holds by construction, and is tested (card seq < every forecast seq of that issuance).
- **Reversibility / cost:**
  - Each card carries all ~300 values, about 20 kB of canonical text. It is written only when the values change.
  - Recomputing the table with different values would append new cards, which is visible and dated.
- **Follow-ups:** the scorer already scores any threshold, so Brier for `typical:peak` appears once events settle.

### D-03.9 — F4: the replay is refreshed in the background before its cache expires

- **Context:** `/v1/replay/overflow` takes ~9 s cold. When its 1 h cache expired, one visitor paid that cost (one supervisor page load took 16.5 s).
- **Choice:** the API's warm-up thread now loops. It recomputes the replay at start and every 50 min (`_REPLAY_REFRESH_S = 3000`), 10 min before the 1 h TTL, and swaps the cached copy in place. A failed refresh is logged, and the previous copy keeps serving until its TTL.
- **Why:** the simplest change that removes the cold path for visitors.
- **Reversibility / cost:** one computation every 50 min (about 9 s of database time).

### D-03.10 — F3: statement timeouts as a database default, and a guarded shell for ad-hoc work

- **Context:** the 01:38Z OOM was an unbounded ad-hoc query.
- **Choice:**
  - Migration 010 sets, for the current database (by name, so the disposable test database never touches production), `statement_timeout = 15min` and `idle_in_transaction_session_timeout = 30min` for every new session that does not set its own.
  - `scripts/dbshell` runs psql with `statement_timeout = 5min` and `work_mem = 8MB`; checked with `SHOW` → `5min`, `8MB`.
  - Long jobs set their own: the recompute 15 min, the typical-peak computation 10 min. `pg_dump` sets 0 itself.
  - History data went into new tables (`eccc_annual_peaks`, `eccc_daily`, `typical_peaks`), never into `observations`.
  - Raising `timescaledb.max_background_workers` and compressing old chunks were **skipped** in part 1 (time). They stay open issues, to be done with a dump first if they are done at all.
- **Reversibility / cost:** one `ALTER DATABASE … RESET` undoes it. The 15-min backstop is well above every scheduled job (the longest is the issuance at about 77 s).

### D-03.11 — The static app is deployed into a stable directory, not bind-mounted from the git working tree

- **Context (an outage).** At 20:26Z the public app answered **404 for `/` and every static file**. The API was fine. Inside the Caddy container, `/srv/web` was empty.
  - Caddy bind-mounted `./web` from the repository, and the host `web/` directory had been replaced: its files have mtime 19:41Z, when I ran `git checkout main && git pull` to start this stage. Caddy kept serving the deleted, empty directory.
  - **Probable outage: ~19:41Z to 20:26:43Z (~45 min), caused by the worker.** Caddy's logs went with the recreated container, so the start time rests on the file mtimes, not on logs.
  - The same mount also meant that **any edit to `web/` went live before it was committed**. That happened with the frontend agent's edits (work log `13:23`).
- **Choice:**
  - Caddy serves `${WEB_DIR:-/srv/floodlead/web}`.
  - `scripts/deploy_web.sh` deploys `web/` there with `rsync -a --delete`, which updates files in place and keeps the directory, and writes `.deployed-commit`. The file is public and shows which commit the site runs.
  - Web changes now go live only by an explicit deploy from a branch with an open PR, like the code.
- **Why:** it fixes the root cause (a directory bind mount on a path that git may replace), and it brings the static app under the deploy-only-from-an-open-PR rule.
- **Reversibility / cost:** one extra command per web deploy. Reverting is one line in `compose.yaml`.
- **Follow-ups:** the check that would have caught this is a public `GET /` in health monitoring. Proposed for Stage 5 (open issues).

### D-03.12 — Addendum 1 (supervisor, Oct 9 ~20:35Z) applied: corrected claims now; scorecard, relay replay and the review's bar in part 2

- **Context:** the supervisor's status-quo review (`docs/research/fraser-valley-flood-warning-status-quo.md`) finds that the weak link is the last mile from the Everson overflow to the barn, not the upstream forecast. The addendum overrides the prompt where they conflict.
- **Part 1, done before Build Session 3:**
  - **README, The Cascade claim:** checked against the article itself (fetched on Oct 9).
    - The owner is of Seasons Farm Market. The article does not say Sumas Way.
    - "This time we heard the sirens, but we still had lots of time" is the owner's direct quote.
    - "barely had any time to prepare" (2021) and "uncertainty of when and from where…" are the reporter's paraphrase and summary, and are now attributed that way.
    - "over 20 hours of preparation time" is the reporter's description of a siren system; it is no longer stated as a fact.
    - The README now says the only documented siren is the City of Sumas, Washington one.
  - **README, BC forecasts:** wherever it described official BC tools, it now also names the RFC's deterministic station forecasts (COFFEE 5-day and CLEVER 10-day, daily steps; COFFEE only in rain events) for Sumas at Huntingdon and Chilliwack at Vedder, and NWS's 6-hourly North Cedarville forecasts.
  - "Evacuation orders after the fact" is now "in 2021 after the water; in 2025 about 12–18 h before it".
  - **The review is linked** from the README header, the "pain" paragraph, the Build Session 3 section and the help panel. The help panel says BC gauges have official RFC station forecasts that FloodLead does not show yet.
  - `brief.md` is untouched.
- **Part 2, before the training sets:**
  1. the official-forecast scorecard (`GET /v1/official-scorecard`, an app page, a README table);
  2. the relay and trigger replay with daylight flags;
  3. arrival-at-the-border estimates only as labelled analogue ranges;
  4. the protocol adopts the review's bar as fixed targets, with ablations and exact binomial CIs;
  5. no BC RFC archiving (licence still yellow).
- **Corrections confirmed by my parser before the addendum arrived** (part-2 log `13:45–13:46`):
  - first NRKW1 warnings: 19:50Z Nov 14, 2021 and 06:17Z Dec 10, 2025;
  - the 2021 "major" upgrade at 10:07Z Nov 15.
  - The forecast crests (148.9 and 148.4 ft) and the observed crossings and crests are reproduced in the scorecard.
- **Reversibility / cost:** documentation and text only in part 1.

### D-03.13 — NWS text products: VTEC and H-VTEC per segment, text crest values, WMO time authoritative

- **Context:** part 2 item 3 and addendum item 3.1 need every official warning's times, category and forecast crest.
- **Choice (`src/floodlead/history/nws.py`):**
  - products split on `\x01`, segments on `$$`;
  - each P-VTEC is paired with the H-VTEC line that follows it;
  - issuance comes from the local time line, but the WMO heading's DDHHMM (UTC) wins when they differ: a correction keeps the original's text time;
  - the forecast crest, observed crest and stage come from the segment text by explicit patterns ("crest near/of/at/around/to", not "a previous crest of"; "crested at"; "the stage was");
  - PILs: FLWSEW, FLSSEW, FFASEW (watches) and ESFSEW (outlooks).
- **Why:**
  - VTEC gives machine-readable events, actions and times; the crest value exists only in the text;
  - no archived RVF/HYD product with NRKW1 values was found (8 PILs probed).
- **Limits:**
  - 49 of 156 NRKW1 segments state no crest (mostly CAN/EXP);
  - 27 spring/summer outlooks and 1 empty correction stay unparsed;
  - categories use today's NWS stages.

### D-03.14 — Rainfall history: one time convention, and only sources a live forecast could have used as inputs

- **Convention:** every rain row's `ts` is the end of its hour, in UTC.
  - SNOTEL timestamps are local standard time (UTC−8 all year). PREC is a water-year accumulation in inches, so hourly amounts are its increases; a negative step becomes 0 and is flagged.
  - NCEI uses routine METARs only (FM-15, AA1 period 1 h).
- **Which sources are honest inputs (measured):**

  | Source | Status | Why |
  |---|---|---|
  | SNOTEL | Yes | newest hour about 40 min old |
  | KBLI | Yes, as a stand-in for the live METAR feed | the same observations |
  | NCEI's archive itself | Not a live source | nothing from the last 7 days |
  | ECCC Abbotsford hourly | Not usable | 0 % precipitation; about 14 h behind |
  | Open-Meteo reanalysis | **Oracle only** | — |
  | Open-Meteo previous runs | The only as-issued forecast rain | from 2024-01-19 |
  | Open-Meteo historical-forecast series | Not used as an as-issued forecast | stitched from each run's first hours |
- **Reversibility:** all of these are derived tables, reloadable from the archive.

### D-03.15 — Upstream links: rise correlation and peak-to-peak lags from the history

- **Method:**
  - hourly means per water year (constant bounds);
  - lagged Pearson correlation of 1-h rises in Oct–Mar, at lags 0–36 h;
  - for target events above the 95th percentile, at least 72 h apart: the lag of the upstream maximum in the 48 h before each.
  - BC pairs use daily means and say that lags under a day are not resolvable.
- **Result:** the Nooksack forks lead North Cedarville by about 4–5 h (n 216–237 events), so longer warnings must come from rain.

### D-03.16 — Official-forecast scorecard definitions

- **Units:**
  - an event is one VTEC FL.W series (ETN, water year) at one point;
  - the observed crest is the maximum 15-min stage in [first product − 12 h, last product or forecast flood end + 48 h].
- **Per product:**
  - lead = observed crest time − issuance;
  - crest error = forecast − observed;
  - crest-time error, from the H-VTEC crest time;
  - category right;
  - flood-begin error against the observed minor crossing.
- **Per event:**
  - the first warning's lead before minor;
  - the first severity-3 product against the SR 544 onset (the replay definition).
- **Published:** `/v1/official-scorecard`, `#/official-scorecard`, and a README table with n and the period.
- **Why:** it reproduces the review's figures from the raw archive, and lets farmers calibrate trust in a "moderate" call. No agency publishes one.

### D-03.17 — Training sets: hourly Nooksack (honest/oracle) and daily Fraser Valley

- **Cut-offs:** every feature is cut at its own latency (`LATENCY`, D-03.14), and records the newest timestamp used (`asof_*`).
- **As-issued forecast rain:** day 1 only for valid hours ≤ t + 18 h, day 2 ≤ t + 42 h (about 24/48 h issue lag plus 6 h for run availability); NaN before 2024-01-19.
- **NWS-derived probabilities:** taken from the product in force at t.
- **Targets:** levels at 1–48 h, and crossings at 6/12/24/48 h. Overflow targets only where the gauge existed, and not when water was already flowing.
- **Splits:** by water year. WY2022 and WY2026 are flagged `holdout`.
- **Tests (`tests/test_datasets.py`):**
  - poisoning every value after each source's cut-off leaves every honest feature unchanged;
  - targets do change;
  - the NWS comparator switches on and off with the products;
  - the held-out water years are flagged;
  - the oracle columns appear only in `oracle`.
  - The first version of the lookup had a bug the test caught: a 10-min window on a 15-min grid looked at no cell, so every level target would have been empty.
- **Features table:** `docs/data/features-nooksack-v1.md`.

### D-03.18 — Event catalogue and relay replay (relay value kept apart from model value)

- **Catalogue:** for North Cedarville, the replay's minor events, each with its crossings, crest, SR 544 onset and first NWS warning. For BC, typical-peak crossings, from the annual instantaneous maxima and the daily means (the latter undercount).
- **Relay replay:** three pre-registered tiers built only from archived products and gauges:
  - heads-up: a flood watch naming Whatcom, 7 days before the minor crossing up to its end;
  - prepare: an NRKW1 warning ≥ minor or an Everson-overflow warning, 72 h before to the end;
  - move: the SR 544 onset, or North Cedarville ≥ minor and rising.
  - Every event since the SR 544 gauge began is counted, and a minor event without overflow is a false alarm.
  - Each fire is flagged daylight or night at Abbotsford (NOAA solar approximation, within 4 min of api.sunrise-sunset.org).
  - BC River Forecast Centre watches cannot be replayed (not archived; licence yellow).

### D-03.19 — Part 2 runs early, from draft PR #6, under its own image tag

- **Context:** part 2 is due Oct 10 ~12:00Z, and PR #5 is in QA until Build Session 3. Waiting would idle the night.
- **Choice:**
  - part 2 is built in a separate git worktree (`../trilemma-part2`), so a part-1 build never picks up part-2 code;
  - draft PR #6 (base `main`) was opened before any part-2 code touched production;
  - part-2 code runs only as one-off `docker run --rm` containers of `floodlead-app:part2` into new tables;
  - `floodlead-app:latest` and the live services stay on part 1.
- **Cost:** PR #6's diff shows part 1 until #5 merges, then `main` is merged in.
- **Slip:** one `git commit -a` swept a frontend draft into a parser-fix commit (`638d6d3`). It is recorded, not rewritten.

### D-03.20 — Protocol amendment 1 (review A1–A3, A5, A7, A8) and the Stage 4 loader that enforces A1 (Oct 10, 01:57 UTC)

- **Context:** the supervisor reviewed the frozen protocol (sound; eight amendments). It was frozen before addenda 2 and 3 arrived, so they enter it as dated amendments, and the frozen text is never edited.
- **Choice:** amendment 1, appended under `## Amendments`. The diff touches only the "(none)" line below that heading.
  - **A1:** development years are WY2005–WY2025 except WY2022; WY2027 onward is the live period.
    - `src/floodlead/train_data.py` enforces this, because the frozen files flag the 167 Oct 1–7, 2026 rows `holdout = false` and must not be rebuilt.
    - `tests/test_train_data.py`: 4 tests, including rejection of WY2022, WY2026 and WY ≥ 2027.
  - **A2:** final-run folds (`final_run_folds()`).
  - **A3:** T5 renamed crossing-probability skill; T6 level skill added.
  - **A5:** the model's tiers are unchanged; Prepare-M = §5.
  - **A7:** the SR 544 onset definition differs before and after Oct 1, 2026; relay v2 is in-sample.
  - **A8:** T3's bias wording; T1 rests on 2 events.
- **sha256 of `docs/evaluation-protocol.md` after amendment 1: `45fd36a3f87852b2eb6ae7ac0a913877512c98eaf614b326aacf44bc208d8214`** (frozen version `ecdefe0b…abad`).

### D-03.21 — Protocol amendment 2: relay v2, counted by alert, with its counting rules fixed before computing (Oct 10, 01:58 UTC)

- **Context:** addendum 3 sets tiers by action cost and asks for a trust table; review A4 asks for them as a second relay comparator, labelled in-sample.
- **Choice:** amendment 2 adds:
  - the tiers: Watch, Heads-up, Prepare, Move now at 5.0 ft with the 4.0 ft variant, and the Everson FA.W row as descriptive;
  - **the counting rules, written before any number was computed:**
    - the record period starts at the first SR 544 record;
    - overflow episodes are SR 544 records grouped by gaps of more than 48 h;
    - an alert's window is its event − 12 h to + 24 h;
    - leads are listed per alert;
    - misses are counted;
    - precision carries a Clopper–Pearson interval;
  - the labels: in-sample; 5.0 ft chosen after seeing the data; never held-out results.
  - Relay v1 stays as built.
- **Episode rule, written after one look at the SR 544 episode list** (8 episodes; the first is 2 h, 3.84 ft, at the start of the record, in an event warned 13 h before the gauge existed): an episode whose warning began before the record start is excluded. Disclosed here, so the reader can judge it.
- **sha256 of the protocol after amendment 2: `39355efe22a0d6b0e0c2898c4693ea1db6d6b08be85bfeb662240d545bb2cbe4`.**

### D-03.22 — Protocol amendment 3: the AI-rainfall case study R0–R3, fixed before any of its data is pulled (Oct 10, 01:59 UTC)

- **Context:** addendum 2 decides against satellite imagery as a forecast input and adds a one-event AI-rainfall case study. Review A6 asks for it as its own amendment, with T0–T3 renamed R0–R3.
- **Choice:** amendment 3 fixes, before any R0 request:
  - the 5 models;
  - the sample points: the 3 Nooksack SNOTEL sites' grid cells, i.e. the upper-basin gauges;
  - the 24 and 48 h windows ending at the 2025-12-10 20:15Z minor crossing;
  - the truth: SNOTEL hourly totals, never IMERG;
  - the outputs: totals, ratio, and the timing of the heaviest 6 h;
  - the reporting rules: every model; "one event, descriptive"; AIFS as 6-hourly; no product change before Demo Day;
  - the Open-Meteo quota rule.
  - R1 and R2 are Stage 4 work; R3 is optional.
- **sha256 of the protocol after amendment 3: `c78bed9fc7af5b04ef8df0c0f273f4ed31776c2ab8bb532d353a62f1bc46ec7c`.**

### D-03.23 — Relay v2 and the trust table, counted by alert; the supervisor's count reproduced (Oct 10, 02:00–02:03 UTC)

- **Code:**
  - `src/floodlead/trust.py` (`floodlead history build trust`) implements amendment 2's rules, written before any number was computed.
  - Tests in `tests/test_trust.py` (8): Clopper–Pearson against published intervals (7/18, 6/8, 4/8, 4/4, 5/5 → 0.48, 3/3 → 0.29), episode splitting, alert scoring.
  - Output `docs/data/trust-v2.json` (sha256 `4d10b858…7202`); `run_id = trust-<generated_at>`.
- **Record:** SR 544 from 2015-11-14 09:15Z, 10.9 years; 18 NRKW1 warning events.
  - Overflow episodes: 7, of which 4 are ≥ 5 ft:

    | Onset | Peak (ft) |
    |---|---|
    | 2015-11-18 | 4.91 |
    | 2017-11-23 | 4.76 |
    | 2020-02-01 | 5.55 |
    | 2021-11-15 | 7.75 |
    | 2021-11-28 | 5.51 |
    | 2025-12-11 | 6.91 |
    | 2026-03-21 | 4.06 |

  - Excluded, per amendment 2: the 2015-11-14 episode (3.84 ft), whose warning (ETN 55) began 13 h before the record.

  | Tier | Alerts | Followed by any overflow (precision, 95 % CI) | By a ≥ 5 ft overflow | Overflows missed | Leads before onset of the large ones (h) |
  |---|---|---|---|---|---|
| Watch (NWS flood watch naming Whatcom) | 47 (4.31/yr) | 8 (17 %, 8–31 %) | 4 (8 %, 2–20 %) | 0 | +68.9, +84.0, +101.5, +120.6 |
| Heads-up (NRKW1 warning, NEW) | 18 (1.65/yr) | 7 (39 %, 17–64 %) | 4 (22 %, 6–48 %) | 0 | +6.6, +12.0, +13.3, +18.5 |
| Prepare (first NRKW1 product, severity ≥ 2) | 8 (0.73/yr) | 6 (75 %, 35–97 %) | 4 (50 %, 16–84 %) | 1 | +4.0, +6.6, +13.3, +18.5 |
| Move now, SR 544 ≥ 5.0 ft (chosen after seeing the data) | 4 (0.37/yr) | 4 (100 %, 40–100 %) | 4 (100 %, 40–100 %) | 3 | -3.5, -1.6, -1.3, -0.8 |
| Move now, SR 544 ≥ 4.0 ft (NWS minor stage; not chosen from the data) | 7 (0.64/yr) | 7 (100 %, 59–100 %) | 4 (57 %, 18–90 %) | 0 | -0.5, -0.3, -0.1, +0.0 |
| Everson-overflow areal warning (FA.W), descriptive | 7 (0.64/yr) | 4 (57 %, 18–90 %) | 3 (43 %, 10–82 %) | 3 | -0.0, +2.8, +6.3 |

  - **Relay v2 is descriptive and in-sample.** The Prepare tier and the 5.0 ft level were chosen after seeing every year (amendment 2).
  - A negative Move-now lead means the reading came after the onset, by construction.
  - Every alert, with its outcome (✔ followed by an overflow, ✘ not; lead before onset; night at Abbotsford):
    - **Heads-up (NRKW1 warning, NEW):** 2015-11-17 23:40Z ✔ (+7.1 h); 2015-12-08 18:45Z ✘; 2016-01-28 17:23Z ✘; 2017-10-19 04:23Z ✘ night; 2017-11-23 10:09Z ✔ (+9.3 h) night; 2018-02-05 00:28Z ✘; 2018-11-02 14:29Z ✘ night; 2018-11-27 06:03Z ✘ night; 2020-02-01 04:55Z ✔ large (+12.0 h) night; 2021-10-29 07:14Z ✘ night; 2021-11-14 19:50Z ✔ large (+6.6 h); 2021-11-28 09:29Z ✔ large (+13.3 h) night; 2022-11-05 06:57Z ✘ night; 2022-12-26 19:58Z ✘; 2023-12-05 19:04Z ✘; 2024-01-28 15:49Z ✘; 2025-12-10 06:17Z ✔ large (+18.5 h) night; 2026-03-20 23:16Z ✔ (+2.2 h)
    - **Prepare (first NRKW1 product, severity ≥ 2):** 2015-11-17 23:40Z ✔ (+7.1 h); 2015-12-08 18:45Z ✘; 2017-11-23 16:22Z ✔ (+3.0 h); 2018-11-27 06:03Z ✘ night; 2020-02-01 12:54Z ✔ large (+4.0 h) night; 2021-11-14 19:50Z ✔ large (+6.6 h); 2021-11-28 09:29Z ✔ large (+13.3 h) night; 2025-12-10 06:17Z ✔ large (+18.5 h) night
    - **Move now, SR 544 ≥ 5.0 ft (chosen after seeing the data):** 2020-02-01 17:45Z ✔ large (-0.8 h); 2021-11-15 04:00Z ✔ large (-1.6 h) night; 2021-11-29 00:10Z ✔ large (-1.3 h); 2025-12-11 04:15Z ✔ large (-3.5 h) night
    - **Move now, SR 544 ≥ 4.0 ft (NWS minor stage; not chosen from the data):** 2015-11-18 06:45Z ✔ (+0.0 h) night; 2017-11-23 19:30Z ✔ (-0.1 h); 2020-02-01 16:55Z ✔ large (+0.0 h); 2021-11-15 02:30Z ✔ large (-0.1 h) night; 2021-11-28 23:10Z ✔ large (-0.3 h); 2025-12-11 01:15Z ✔ large (-0.5 h) night; 2026-03-21 02:45Z ✔ (-1.2 h) night
    - **Everson-overflow areal warning (FA.W), descriptive:** 2021-11-14 23:40Z ✔ large (+2.8 h); 2021-11-16 03:20Z ✘ night; 2021-11-28 22:51Z ✔ large (-0.0 h); 2024-01-28 20:17Z ✘; 2024-01-29 00:03Z ✘; 2025-12-10 18:26Z ✔ large (+6.3 h); 2026-03-21 00:12Z ✔ (+1.3 h)
  - **Rule artefact (reported, not adjusted):** a warning re-issued while an overflow is under way counts ✘, because the onset precedes its window. Example: FA.W ETN 3, 03:20Z Nov 16, 2021, issued while the Nov 15 overflow was still flowing.
  - The FA.W row matches on the product text. The first segment-head match missed the 10:26 AM PST Dec 10, 2025 warning; it was fixed and rerun. In 2021 (twice) and 2025, the Everson-overflow warning came after Prepare, as addendum 3 says.
- **Reproduction of the supervisor's count (addendum 3, section 2):**

  | Item | Supervisor | Worker (`trust-v2.json`) |
  |---|---|---|
  | NRKW1 warning events, Nov 14, 2015 → Oct 9, 2026 | 18 (10.9 years) | 18 (10.9 years) |
  | Overflows at SR 544 / ≥ 5 ft | 7 / 4 | 7 / 4 (plus 1 record-start episode excluded by rule) |
  | Heads-up: alerts; followed by overflow; by ≥ 5 ft | 18; 7 (39 %, 17–64 %); 4 (22 %) | 18; 7 (39 %, 17–64 %); 4 (22 %, 6–48 %) |
  | Prepare: alerts; followed by overflow; by ≥ 5 ft | 8; 6 (75 %, 35–97 %); 4 (50 %, 16–84 %) | 8; 6 (75 %, 35–97 %); 4 (50 %, 16–84 %) |
  | Prepare: leads before the 4 large onsets | 4.0, 6.6, 13.3, 18.5 h | +4.0, +6.6, +13.3, +18.5 h |
  | Prepare: alerts with no overflow | Dec 2015, Nov 2018 | 2015-12-08, 2018-11-27 |
  | Move now 5.0 ft | 4 of 4 (40–100 %), 0.8–3.5 h after onset | 4 of 4 (40–100 %), 0.8–3.5 h after onset |
  | Move now 4.0 ft | 7 alerts, 4 large | 7 alerts, 4 large |

  **Every number agrees.** The only rule I had to state that the supervisor did not is the exclusion of the record-start episode. Their "from Nov 14, 2015" count implies the same.
- **2021 and 2025 against Abbotsford (2 events only, amendment 1 A8):**
  - Prepare came 12.7 h (2021, daylight) and 17.7–19.1 h (2025, night) before the City's first alert.
  - Move now at 5.0 ft came 4.5 h before the alert in 2021, but 2.9–4.2 h after it in 2025.

### D-03.24 — Archive completeness test, and the SR 544 record start (addendum 3, sections 3 and 6; Oct 10, 02:04 UTC)

- **Whole years:**
  - every IEM task is one calendar year (`sdate` YYYY-01-01, `edate` YYYY+1-01-01);
  - production `history_downloads` holds all 23 years (2004–2026), `ok`, for each of FLWSEW, FLSSEW, FFASEW and ESFSEW, with 0 failures.
- **Test** (`tests/test_nws_archive.py`):
  - the fixture `tests/fixtures/iem_nrkw1_2015_2026.txt` holds every archived product naming NRKW1 from 2015-11-14 to 2026-10-09: 75 products, 290 kB, cut from the whole-year downloads;
  - the test asserts **all 18 warning events**, with the supervisor's anchors: ETN 78 at 19:50Z Nov 14, 2021; **ETN 88 at 09:29Z (1:29 AM PST) Nov 28, 2021**, the event a partial-year pull once missed; ETN 47 at 06:17Z Dec 10, 2025;
  - and whole-year coverage without gaps, for all four PILs.
- **SR 544 record start (§6):**
  - USGS NWIS IV gives the first records at 00:15 PST, 2015-11-14 (08:15Z): 3.59, 3.73, 3.80 and 3.83 ft, at 08:15–09:00Z.
  - **Our backfill lacks those four**, and starts at 09:15Z (3.84 ft), although its chunk is recorded from 08:15Z with 45 rows. The cause is not yet known.
  - Impact: none on any count. That episode is excluded by rule (D-03.23), and the onset of each later episode is unaffected.
  - The backfill skips recorded chunks, so a re-fetch needs a forced window: a change to live code, left as an open issue for Stage 4 rather than patched tonight.

### D-03.25 — R0: AI rainfall is testable (Oct 10, 02:05 UTC)

- **Run:** `scripts/r0_availability.py`, one Previous Runs request per SNOTEL site with all 5 models and `precipitation`, `_previous_day1` and `_previous_day2`, Dec 7–12, 2025.
  - **3 requests (≈ 5 counted calls); no quota refusal.** The responses are cached in `/srv/floodlead/datasets/r0/`; the summary is `docs/data/r0-availability.json`.
- Non-null hours out of 144 at each of the 3 sites:

  | Model | Lead 0 | Day-1 lead | Day-2 lead |
  |---|---|---|---|
  | `ecmwf_aifs025_single` (AIFS, AI) | 144 | **144** | **144** |
  | `ecmwf_ifs025` | 144 | 144 | 144 |
  | `gem_hrdps_continental` | 144 | 144 | **0** |
  | `ncep_hrrr_conus` | 144 | 144 | **0** |
  | `ncep_nbm_conus` | 144 | 144 | 144 |

- **Result: AI rainfall (AIFS) returns values at fixed day-1 and day-2 leads, so R1 can run in Stage 4.**
  - HRDPS and HRRR have no day-2 values, so their comparison is day-1 only.
  - The model names in addendum 2 were accepted as given; no substitution.
- **Grid note:** Elbow Lake (910) and MF Nooksack (1011) fall in the same ECMWF 0.25° cell (48.75, −122.0), so AIFS and IFS give identical values there. That is effectively 2 ECMWF sample cells, against 3 for HRDPS, HRRR and NBM. This is stated with R1.
- These are raw availability counts, not a forecast verification.

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

- `12:44–12:49` — Draft PR #5 opened. Terms pages fetched and the probes above run (D-03.2, D-03.3).
  - Wrote `migrations/006_history_downloads.sql` (a new table only), `src/floodlead/history/{download,tasks,cli}.py`, `archive.read`, and the five records in `data-contract.md` (inputs 8–11).
  - Task counts:
    - `eccc-peaks` 1+ pages;
    - `eccc-daily` 1 page per station, + follow-ups;
    - `eccc-climate` 122;
    - `iem-nws` 46;
    - `ncei` 23;
    - `snotel` 23;
    - `openmeteo-archive` 184, `-histfc` 56, `-prevruns` 32 (≈ 7,100 Open-Meteo calls in total).

- `12:50` — **Downloads started** (`docker compose run -d --name hist-{eccc,us,openmeteo} backfill floodlead history download …`, image `7e91866`), after `floodlead migrate` → `006_history_downloads.sql`. 19:50:03Z.
  - `iem-nws` finished at 19:51:39Z: 46 requests, 13,034,726 B, 0 errors.
  - `eccc-peaks`: 4 pages (37,806 rows), 21.9 MB.
- `12:51–12:55` — **F1 fair CRPS** (D-03.4).
  - `src/floodlead/crps.py` and `tests/test_crps.py`: point forecast = AE; tied edges; equality with a numerical integral of the same CDF; bias tables.
  - Scorer: `crps` is now fair, `crps_qs` is kept, plus MAE skill; naive rows carry NOAA points; `recompute_crps`.
  - `pytest -q -s tests/test_crps.py`:
    ```
    7 levels  calibrated normal                fair +0.0 %   quantile score -19.3 %
    7 levels  log-normal (s=0.5)               fair +0.0 %   quantile score -18.2 %
    7 levels  under-dispersed (sd 0.5 vs 1)    fair -0.2 %   quantile score -14.2 %
    7 levels  over-dispersed (sd 2 vs 1)       fair +1.2 %   quantile score -12.9 %
    19 levels (all four cases)                 fair +0.0 … +0.1 %
    ```
  - Full suite → **102 passed**, 4 deselected. Test fixtures now truncate `history_downloads` with `raw_objects` (new FK).
  - `evaluation.md` corrected: the "ranks models" sentence is withdrawn.
- `12:55` — Score tables dumped before migration 007 (D-03.5).

- `12:56` — Migration 007 applied on production (`floodlead migrate` → `007_crps_qs.sql`).
  - **First recompute failed and rolled back:** `psycopg.ProgrammingError: can't change 'autocommit' now: connection in transaction status INTRANS`, after 37.2 s. The chunk updates had run inside the first statement's implicit transaction, so the error rolled all of them back. Nothing changed on production.
  - The test had passed only because the pooled connection was reused from an earlier `scorer.run`, which leaves autocommit on.
  - Fix: autocommit is set before the first statement. The test now uses a fresh pool, as production does: **it fails without the fix and passes with it**.

- `12:58–13:04` — **Feedback** (D-03.6):
  - migration 008;
  - `src/floodlead/feedback.py`, `POST /v1/feedback`, health counts, `floodlead feedback list`, the issue form;
  - `tests/test_feedback.py`: validation, encryption round trip and wrong key, per-IP and global limits, end to end (202, not echoed, encrypted at rest, decrypted only by the reader, absent from captured logs and output, health counts, append-only), 413/400/429.
  - **The test caught a bug in my first version:** health folds every job block into the overall status, and the feedback block had none, so health would have returned 500. Feedback counts now sit outside the status roll-up.
  - `pytest -q` → **107 passed**.

- `13:05` — Feedback deployed: `floodlead migrate` → `008_feedback.sql`; the API recreated with `FEEDBACK_KEY` (`.env`, generated on the VM, not printed).
  - Public checks:
    - `POST {}` → 400;
    - a synthetic smoke test (`"Worker smoke test after deploy (synthetic, no personal data)."`) → 202 `{"status":"received"}`;
    - `floodlead feedback list` → `#1 2026-10-09 20:05Z useful=yes route=#/ … 1 item(s)`;
    - health `feedback: {counts_only: true, total: 0 → 1}`.
- `13:05–13:15` — Typical yearly peaks (D-03.7), issuer thresholds through new cards (D-03.8), `/v1/gauges/fraser-valley`, `/v1/track-record`, F4 (D-03.9), F3 (D-03.10).
  - New tests:
    - `tests/test_typical_peaks.py` (5): the median and the ice rule, ok, insufficient, the datum shift rejected (with tolerance edges), flags;
    - `test_typical_peaks_enter_the_ledger_in_new_cards_before_first_use`;
    - contract tests for both endpoints.
  - `pytest -q` → **115 passed**, 4 deselected.
- `13:12–13:22` — **History loaded, peaks computed, deployed** (`8e48476`):
  - `floodlead migrate` → `009_history_tables.sql`, `010_statement_timeouts.sql`;
  - `floodlead history load peaks` → **37,789 rows** in 37.3 s (17 of 37,806 features have no value or date);
  - `floodlead history load daily` → **448 stations, 7,825,554 daily rows** in 525.6 s (peak RSS 52 MB);
  - `floodlead history typical-peaks` → `{'stations': 433, 'counts': {'ok': 302, 'insufficient': 122, 'flagged': 8, 'rejected': 1}}` in 24.3 s.
  - Fraser Valley gauges (`/v1/gauges/fraser-valley` after the deploy at 20:22Z):

    | Gauge | Level now (m) | Age (min) | Typical yearly peak (m) | n (years) | Below peak (m) |
    |---|---|---|---|---|---|
    | Sumas R. near Huntingdon (08MH029) | 1.266 | 48 | 3.397 | 12 (2013–2024) | 2.131 |
    | Chilliwack R. at Vedder Crossing (08MH001) | 1.528 | 63 | 3.307 | 14 (2011–2024) | 1.779 |
    | Chilliwack R. above Slesse Ck (08MH103) | 0.558 | 78 | 2.817 | 14 (2011–2024) | 2.259 |
    | Fraser R. at Hope (08MF005) | 3.600 | 73 | 8.903 | 20 (2005–2024) | 5.303 |
    | Fraser R. at Mission (08MH024), tidal | 0.975 | 73 | 5.562 | 20 (2005–2024) | 4.587 |
    | Nicomekl R. at 203 St (08MH155) | 1.006 | 93 | 3.971 | 14 (2011–2024) | 2.965 |
    | Coquihalla R. below Needle Ck (08MF062) | 1.817 | 48 | 2.958 | 13 (2011–2024) | 1.141 |

  - `/v1/track-record` → 21,341 forecasts in 25 issuances, 0 gaps, 20 skill rows, 6 NOAA matched pairs; 0 official and 0 typical-peak crossings in the window.
  - Its statements are generated from the numbers. Example: "Lower median error (MAE) than pure persistence only at: persistence-v1 USGS 1 h (+4.5 %, n 200); … 3 h (+2.2 %, n 180); … 6 h (+3.9 %, n 150). Everywhere else pure persistence is as good or better."
- **Download progress** (`history_downloads`):
  - **iem-nws:** 46 ok, 13.0 MB, 19:50:08 → 19:51:39Z.
  - **snotel:** 23 ok, 85 MB, done 19:54:59Z.
  - **ncei:** 22 ok + 1 empty (2026 not yet available), 183 MB, done 19:58:52Z.
  - **eccc-peaks:** 4 pages, 21 MB.
  - **eccc-daily:** 1,026 ok + 4 empty, done 20:09:17Z.
  - **eccc-climate:** 121 ok + 1 empty, done 20:11:27Z.
  - **openmeteo:** still running; paced at 30 s per point-year (≈ 2.3 h).

- `13:23` — **Frontend** (a background agent briefed with the API contracts above; its files reviewed by the worker): `web/app.js`, `index.html`, `style.css`, `README.md`, `scripts/screenshots.cjs` (445 lines added, 15 removed).
  - **Feedback box:** the last card on every route, Yes/No plus text with a live count, the privacy sentence, `POST /v1/feedback`, messages for 202/400/413/429/offline, and the GitHub link.
  - **"Fraser Valley gauges":** a card on `#/` after the ledger panel, with a jump button in the hero.
  - **"How to read this":** a `<details>` panel in `index.html` under the header, on every route.
  - **`#/track-record`:** the statements first, then forecasts and the chain head and anchor, verify commands, one table per source, and the NOAA pair count.
  - Worker review:
    - no `innerHTML`, `eval` or inline styles or handlers added;
    - user text is never rendered;
    - the help text's colour claims match the chart (`COLORS.noaa #1f5fbf` blue, `COLORS.fl #5d7f78` grey-green).
  - `tests/test_web.py` gains the two new snapshot slugs → 18 passed.
  - **Deviation:** Caddy serves `./web` from this working tree, so the agent's edits were live on the public site while it worked (about 20 minutes) and before this commit put them in PR #5 (fixed by D-03.11). All the backend code they call was already in PR #5 and deployed.

- `13:24–13:27` — **Public app outage found and fixed (D-03.11).**
  - A headless check of `#/` and `#/track-record` showed an empty `#app` and 404s. `curl` gave `/ 404`, `app.js 404`, `style.css 404`. `docker compose exec caddy ls -la /srv/web` showed `total 0`, a deleted directory.
  - Fix:
    - `sudo mkdir /srv/floodlead/web`;
    - `scripts/deploy_web.sh` (`rsync -a --delete`);
    - `compose.yaml` caddy volume `${WEB_DIR:-/srv/floodlead/web}:/srv/web:ro`;
    - `docker compose up -d caddy`.
  - Back at **20:26:43Z**: `/ 200`, `/app.js 200`, `/style.css 200`, `/.deployed-commit 200` (fb18035).
- `13:27` — **AC-2, feedback from the app on the public URL:** `scripts/feedback_e2e.cjs` (headless Chromium, 375 px, `#/track-record`) clicked Yes, typed a synthetic sentence and submitted.
  - Result: `{"http_status":202,"status_text":"Thank you. Your feedback was received.","page_errors":[]}`.
  - Screenshots `img/stage-03/feedback-before-submit-375.png` and `feedback-after-submit-375.png`.
  - Read back on the VM:
    ```
    $ floodlead feedback list
    #1 2026-10-09 20:05Z useful=yes route=#/ station=- v=stage-03
        Worker smoke test after deploy (synthetic, no personal data).
    #2 2026-10-09 20:27Z useful=yes route=#/track-record station=- v=stage-03
        Synthetic end-to-end test by the build worker (no personal data).
    2 item(s)
    ```
- `13:28` — **AC-5, screenshots** (`scripts/screenshots.cjs`, zenika/alpine-chrome@sha256:ee10e242…, public URL, 64 s).
  - `layout-check.txt`: **scrollWidth = viewport on every page** (`#/`, `#/` with the help panel open, `#/stations`, two station pages, `#/track-record`) at 1280 and 375 px.
  - `page errors (all pages): 0; with navigator.language=en-US@posix: 0`.
  - The files are in `img/stage-03/`: track record, Fraser Valley list, help panel, feedback and the overflow watch.

- `13:30–13:38` — README "Build Session 3 — working in public"; contract files updated (table below).

- `13:31` — Snapshot refreshed: `floodlead export-demo` → 45 files, including `v1_gauges_fraser-valley.json` and `v1_track-record.json`. Health in the snapshot carries feedback **counts only** (`{"counts_only":true,"total":2,…}`).
  - Snapshot mode checked with `python3 -m http.server -d web 8080` and `scripts/screenshots.cjs http://localhost:8080/`:
    - 14/14 layout rows OK;
    - `page errors (all pages): 0; with navigator.language=en-US@posix: 0` (the console shows only the expected `/v1` 404 probes);
    - the track record renders from the snapshot under the "Snapshot from Fri, Oct 9, 13:30 PDT" banner.
- `13:31` — F3 check: a plain `psql` session now shows `statement_timeout = 15min` and `idle_in_transaction_session_timeout = 30min` (database defaults from migration 010). `scripts/dbshell` shows `5min` and `8MB`.

- `13:47–13:48` — **Addendum 1 received and applied to part 1** (D-03.12): `main` merged into `stage-03-public` (`0b609eb`); README and help-panel corrections; `tests/test_web.py` → 18 passed.

- `14:17` — **AC-4, thresholds in the ledger before first use** (the 21:15Z issuance, the first with the typical-peak code):
  ```
  seq   | type       | model          | created_at  | change (trimmed)                                         | supersedes | values | bytes
  21383 | model_card | persistence-v1 | 21:15:00.59 | typical yearly peak thresholds added or updated (params…) | 1719       | 302    | 22179
  21384 | model_card | trend3h-v1     | 21:15:00.59 | typical yearly peak thresholds added or updated (params…) | 3          | 302    | 21814
  forecasts of base 21:00Z: seq 21385–22238 (854), 584 with a typical:peak threshold; issuance seq 22239
  ```

- `14:30–14:31` — **AC-4, the chain still verifies** after the new cards, from the API and from GitHub alone. Anchor 26 at 21:30:00Z covers seq 22239: commit `e92c8f65`, `ledger/entries/2026/10/09/21.jsonl.gz`, 409,434 B.
  ```
  $ python3 scripts/verify_ledger.py --api https://<host>
  OK {"entries": 22239, "first_seq": 1, "last_seq": 22239, "head_hash": "d2b8921a…7b9f", "by_type": {"genesis": 1, "model_card": 5,
      "forecast": 22195, "issuance": 26, "official_forecast": 12}, "anchors_checked": 26, "anchors_outside_range": 0, "source": "api"}
  $ python3 scripts/verify_ledger.py --source github
  OK {… same entries, head and counts …, "anchors_checked": 26, "source": "github", "files": 26}
  $ curl -s $H/v1/ledger/21383 | jq -r .canonical | jq '.data.params.typical_peak'
  persistence-v1 · typical-peak-v1 · period [2005, 2024] · 302 values · eccc:08MH029 {"level_m": 3.397, "n_years": 12, "years": [2013, 2024]}
  ```
- `14:32` — Part 1 finished. PR #5 marked ready with the STAGE REPORT.

- `19:00–19:10` (Oct 10, 02:00–02:10Z) — **Supervisor's protocol review and addenda 2 and 3 applied.**
  - `main` merged into `stage-03-history` after PR #5 (`a6f87d6`).
  - Amendments 1–3, each in its own commit (D-03.20–D-03.22).
  - Trust table and the reproduction of the supervisor's count (D-03.23); archive-completeness test and the SR 544 record-start finding (D-03.24); R0 (D-03.25).
  - `pytest -q` → **154 passed**, 4 deselected; `ruff` clean.
  - **Part 2 deployed from PR #6:**
    - the `floodlead-app:part2` image, built at `3f8aea8`, tagged `latest`;
    - `docker compose up -d --no-build ingest api`; `scripts/deploy_web.sh` → `.deployed-commit` `3f8aea8…`;
    - health green; `/v1/official-scorecard` → scorecard 2, NRKW1 32 scored events.
  - Screenshots (`img/stage-03/official-scorecard-*.png`, `layout-check-part2.txt`): **19 of 19 layout rows OK** at 1280 and 375 px, including `#/official-scorecard` with every `<details>` open; `page errors (all pages): 0; with navigator.language=en-US@posix: 0`.
- **Latency probes, 7 hourly runs 20:40Z Oct 9 → 01:40Z Oct 10:**
  - **SNOTEL newest hour 41 min old every time.** The datasets' 120-min cut-off is conservative.
  - **ECCC Abbotsford A climate-hourly stuck at 07:00Z Oct 9**, falling further behind (13.7 → 18.7 h), and never with precipitation. ECCC climate-hourly is not near-real-time at this station.
  - **NCEI KBLI: none in the last 7 days at any probe.**
  - Open-Meteo "archive": recent hours are model-filled.
- **Disk:**
  - history tables **1.6 GB** in all: `eccc_daily` 665 MB, `openmeteo_hourly` 527 MB, `rain_hourly` 376 MB (both rain tables include dead tuples from the reloads; a VACUUM would reclaim them), NWS 23 MB;
  - database 6.4 GB (was 4.8 GB); raw archive 342 MB gzipped; datasets 54 MB; disk 28 % used.
- Contract files (part 2): `README.md` (scorecard table), `architecture.md`, `data-contract.md` (FFASEW/ESFSEW; latencies), `roadmap.md` (the AI-rain shadow archive after Demo Day; satellite imagery rejected), `tests/fixtures/README.md`, `docs/evaluation-protocol.md` (frozen plus amendments 1–3).

## Measurements

| What | Value | How measured | When |
|---|---|---|---|

## Acceptance criteria

Part 1 (PR #5). Part 2's criteria (AC-8 to AC-10) are reported with PR 2.

| AC | Result | Evidence |
|---|---|---|
| AC-1 Fair CRPS live | **PASS** | Bias table (`pytest -s tests/test_crps.py`, 7 levels): fair +0.0 / +0.0 / −0.2 / +1.2 % against quantile-score −19.3 / −18.2 / −14.2 / −12.9 % (normal, log-normal, under-, over-dispersed); 19 levels ±0.1 %. All stored scores recomputed (scorer run 31: 55,258 rows + 27,641 naive, 38.4 s). `/v1/scores/summary` shows fair `mean_crps_m`, `mean_crps_qs_m`, and per pair `crpss`, `mae_skill`, `paired_crps`, `paired_mae`, `n_pairs`. Pure persistence is in `/v1/scores/official`. Work log `12:51–12:56` |
| AC-2 Feedback end to end | **PASS** | Submitted from the app on the public URL (`scripts/feedback_e2e.cjs` → `{"http_status":202,"status_text":"Thank you. Your feedback was received.","page_errors":[]}`, screenshots before/after). Read back only with `floodlead feedback list` → item #2 decrypted. Synthetic text only. Issue form `.github/ISSUE_TEMPLATE/feedback.yml` is on the branch; it goes live on GitHub when PR #5 is merged to `main`. Work log `13:27` |
| AC-3 Fraser Valley list and typical yearly peaks | **PASS** | `/v1/gauges/fraser-valley`: **7 of 7** Fraser Valley gauges with a level, an age and an `ok` typical yearly peak (table at `13:12–13:22`). BC counts: 433 computed, **302 ok, 8 flagged, 1 rejected, 122 insufficient**. Screenshots `fraser-valley-desktop.png`, `fraser-valley-375px.png` |
| AC-4 Ledger records the thresholds before first use; chain verifies | **PASS** | Base 21:00Z issuance (run 21:15Z): new cards **seq 21383** (`persistence-v1`, supersedes 1719) and **seq 21384** (`trend3h-v1`, supersedes 3), each with `params.typical_peak` (302 values, provenance and rules; 22,179 / 21,814 B canonical) and `change: "typical yearly peak thresholds added or updated (params.typical_peak); forecast method and other parameters unchanged"`. The first forecast using them is **seq 21385**; 584 of the 854 forecasts (seq 21385–22238) carry `typical:peak`. The old cards are unchanged. Verifiers: work log `14:31` |
| AC-5 Track record and help panel, desktop and 375 px | **PASS** | `layout-check.txt`: scrollWidth = viewport on every page, including `#/track-record` and `#/` with the help panel open, at 1280 and 375 px. 0 page errors, 0 with a POSIX locale. Screenshots `track-record-*.png`, `help-open-375px.png`. Work log `13:28` |
| AC-6 README section; PR merged before 01:00 UTC | **PASS** (README) / supervisor (merge) | README "Build Session 3 — working in public" (`0ae99d6`) |
| AC-7 F2, F4, F3 | **PASS** | F2: `uptime -s`, `last -x reboot`, `docker ps` (work log `12:44`). F4: background replay refresh every 50 min (D-03.9; timing evidence below). F3: database defaults `statement_timeout 15min`, `idle_in_transaction_session_timeout 30min`; `scripts/dbshell` 5 min / 8 MB (work log `13:31`) |
| AC-11 ruff and pytest | **PASS** | `ruff check .` → All checks passed; `pytest -q` → 117 passed, 4 deselected, DB tests run (part-1 branch) |
| AC-12 Decisions, stage doc, contracts | **PASS** (part 1) | 12 decisions (D-03.1–D-03.12). The stage doc is in 13 of the 15 part-1 commits on top of `main` (counting the commit that records this number; one of the 15 is a merge of `main`), 19:43–21:32Z. Contract files table below |

Part 2 (PR #6):

| AC | Result | Evidence |
|---|---|---|
| AC-8 ECCC daily history and annual peaks in new tables | **PASS** | `eccc_daily` **7,825,554 rows, 448 stations**, 1903-04-01 → 2026-06-09, median 53 years per station (1–123), **665 MB**. `eccc_annual_peaks` **37,789 rows, 962 BC stations**, 1923–2025, 4.9 MB. Typical peaks for 433 stations (part 1) |
| AC-9 Rainfall with licence records, latencies and as-issued start dates; the NWS archive parsed with the official warning timeline per event | **PASS** | **Records:** 5 new usage-rights records (D-03.2), plus FFASEW/ESFSEW. **Rows:** `rain_hourly` eccc-climate 1,007,776, ncei 188,757, snotel 587,425; `openmeteo_hourly` archive 1,597,056, histfc 475,008, prevruns 264,576. **Latency** (7 probes): SNOTEL 41 min; ECCC Abbotsford stuck, 14–19 h, no precipitation; NCEI not live. **As-issued forecast rain from:** previous runs day 1 **2024-01-19**, day 2 2024-01-20 (historical forecast 2018-01-01, not as-issued at lead). **NWS:** 7,293 products, 11,018 VTEC records; the scorecard and catalogue give the official timeline per event; the archive test holds all 18 NRKW1 events since Nov 2015, including ETN 0088 |
| AC-10 Training sets, features table, leakage and split tests, event catalogue, frozen protocol | **PASS** | `nooksack_hourly_{honest,oracle}_v1` (193,007 rows each) and `fraser_valley_daily_*` (93,805), sha256 pinned. `docs/data/features-nooksack-v1.md`. `tests/test_datasets.py` (poisoning after each cut-off changes no feature); `scripts/check_datasets.py` → **0 violations on every row**; `tests/test_train_data.py` (the Stage 4 loader rejects WY2022, WY2026, WY ≥ 2027). Catalogue: 20 Nooksack events with the first NWS warning. **Protocol frozen at `45367d1`, sha256 `ecdefe0b…abad`**; amendments 1 → `45fd36a3…8214`, 2 → `39355efe…2cbe4`, 3 → `c78bed9f…ec7c` |
| Addendum 1 (scorecard, relay replay, arrival, the review's bar) | **PASS** | `/v1/official-scorecard`, `#/official-scorecard` and the README table, with n and period (D-03.16). Relay v1 replay (superseded) and the relay v2 trust table (D-03.23). Arrival is a labelled range only (protocol §6). The bar is adopted (protocol §6) |
| Addendum 3 (tiers, trust table, archive test) | **PASS** | Tiers in amendment 2; trust table `trust-v2.json` with every alert listed; **the supervisor's count reproduced exactly**; archive-completeness test. Alert wording from the trust table: Stage 4/7 |
| Addendum 2 (R0) | **PASS** | AIFS returns day-1 and day-2 leads, so AI rainfall is testable (D-03.25). R1/R2 are Stage 4 work; R3 (satellite overlay) not done (optional) |
| AC-11 ruff and pytest | **PASS** | `ruff check .` → All checks passed; `pytest -q` → **154 passed**, 4 deselected (DB tests run) |
| AC-12 Decisions, stage doc, contracts | **PASS** | 25 decisions in the stage (D-03.13–D-03.25 in part 2). The stage doc is in most part-2 commits (count in the report). Contract files above |

## Contract files changed

| File | What changed | Why |
|---|---|---|
| `data-contract.md` | Five usage-rights records (ECCC climate-hourly, NCEI Global Hourly US-only, NRCS SNOTEL, Open-Meteo non-commercial, IEM NWS archive) with the terms pages fetched on Oct 9; inputs 8–11; feedback privacy tier; typical-peak lineage | D-03.2, D-03.6, D-03.7 |
| `evaluation.md` | The fair CRPS replaces the quantile score; the "ranks models" sentence withdrawn; MAE skill against pure persistence; future models store 19 quantiles; naive in the NOAA comparison | F1, D-03.4 |
| `architecture.md` | Components (history, scorer, feedback, web deploy), Stage 3 tables, new endpoints, DB guard rails, web deploy | Facts changed |
| `docs/ledger-spec.md` | The `typical` threshold kind and `params.typical_peak` in model cards | D-03.8 |
| `README.md` | "Build Session 3 — working in public": who it is for and 3 steps, feedback, what is measured live (with the run ID), known limits, how FloodLead will be judged, what changed; links to the track record | Part 1 item 6 |
| `docs/evaluation-protocol.md` (part 2) | New: frozen before any model (`45367d1`); amendments 1–3 on Oct 10 | Part 2 item 7; review A1–A8; addenda 2–3 |
| `README.md` (part 2) | "How accurate were the official forecasts?" table | Addendum 1 item 3.1 |
| `data-contract.md` (part 2) | NWS FFASEW/ESFSEW; measured latencies | D-03.13, D-03.14 |
| `architecture.md` (part 2) | New tables, `/v1/official-scorecard`, history commands | Facts changed |
| `roadmap.md` | AI-rain shadow archive after Demo Day; satellite imagery rejected | Addendum 2 items 6–7 |
| `compose.yaml` | Caddy serves `/srv/floodlead/web` (deployed by `scripts/deploy_web.sh`) | D-03.11 |

## Open issues and handoff to next stage

Part 1 (at PR #5):

1. **Outage caused by the worker, 19:41–20:26Z (probable).** Caddy served a deleted directory after a git checkout (D-03.11). Fixed, and the root cause is removed. **Nothing monitors the public page itself**: health checks the API, not `GET /`. Add a static-site check to health or to an external probe in Stage 5.
2. **Skill claims.** The track record now shows fair CRPS and median MAE against pure persistence, with generated statements.
   - The means still rest on a few tidal, regulated or step-changed stations (Stage 2 open issue 2, e.g. 08LF027).
   - A step-change and tidal flag for truth is still to do, in Stage 3 part 2 or Stage 4.
3. **Typical yearly peak limits.**
   - The datum rule cannot see a datum change under about 0.5 m, and can flag a real but unusual season.
   - 122 BC gauges have fewer than 10 years of annual peaks, so they get no value.
   - Regulated rivers and lake outlets get a value like any other gauge.
4. **Feedback.**
   - Retention period not yet set (Stage 7 privacy policy).
   - Losing `FEEDBACK_KEY` makes the stored text unreadable; there is no key escrow.
   - Two synthetic test items (#1, #2) are in the append-only table. They are labelled as synthetic in their text.
5. **Skipped from F3:** raising `timescaledb.max_background_workers` and compressing old chunks (each needs a dump first and a decision).
6. **The GitHub issue form** goes live when PR #5 is merged; GitHub reads templates from the default branch.
7. **Open-Meteo is non-commercial** (D-03.2). Fine for the datathon and for training; a commercial FloodLead needs a paid plan or a swap.
8. **Downloads still running at PR time:** Open-Meteo reanalysis, 184 point-years at 30 s each, expected to finish ≈ 22:05Z. Parsing is part 2.

Part 2 (at PR #6):

1. **P(≥ 150 ft) has no development event.** North Cedarville reached 150 ft only in the two held-out floods; the protocol makes it distribution-derived and descriptive. Development years hold only 5 events ≥ 148 ft and 3 overflows: thin evidence for any alert rule.
2. **The SR 544 backfill lacks the first four USGS records** (08:15–09:00Z, Nov 14, 2015), for a cause not yet known. No count is affected. A forced re-fetch is for Stage 4.
3. **The history is approved (revised) data**, not what was seen live. Only the live ledger is fully as-seen.
4. **KBLI live use needs the NWS METAR feed**, a new source with its own record (Stage 5). NCEI's copy is not live.
5. **ECCC Abbotsford hourly climate has no precipitation and is not near-real-time.** Fraser Valley rain rests on Hope and Pitt Meadows (daily) and Open-Meteo.
6. **Scorecard limits:**
   - categories use today's NWS stages;
   - 49 of 156 NRKW1 segments state no crest;
   - the page shows the "after the crest" bin with a meaningless timing value of 288 h, which the README already drops;
   - n is small at 12–48 h leads.
7. **Relay v2 is in-sample:**
   - the 5.0 ft Move-now level is provisional and is re-checked after the first overflow of 2026–27 (SR 544 bridge);
   - a warning re-issued during an ongoing overflow counts ✘ (FA.W ETN 3, 2021);
   - Move now came after the City's alert in 2025.
8. **R1 and R2 are Stage 4 work** (if on schedule). R3 was not done. In the ECMWF grid, Elbow Lake and MF Nooksack share one cell.
9. **The rain tables carry dead tuples from the reloads** (`openmeteo_hourly` 527 MB); a VACUUM would reclaim them.
10. **One `git commit -a` swept a frontend draft into `638d6d3`**, recorded and not rewritten. Part-2 code was deployed from PR #6 at 02:07Z on Oct 10, after PR #5 merged.
