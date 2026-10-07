# FloodLead BC

**Hours of warning before *your* river gauge crosses *your* action level — and an agent that starts your plan when it does.**

FloodLead BC is a flood lead-time forecaster for BC farmers and riverside households. It turns the federal real-time hydrometric feed into a calibrated probability that a specific gauge will cross a level the user chose ("check pumps", "move cattle", "leave") within the next 6–48 hours. When the risk passes the user's own threshold, an agent calls them, waits for approval, and then texts the people on their action list. Every forecast is written to a public, hash-chained ledger and scored against what the river actually did.

> **Status:** Build Session 1 (Framing) complete, entering Build Session 2 — Datathon Season 2026, Trilemma Foundation × Northeastern University Vancouver.
> **Not an official warning service.** Always follow EmergencyInfoBC and your local authority's evacuation orders.

---

## One sentence

BC's flood advisories describe whole basins in cubic metres per second and return periods; FloodLead tells one farmer, in hours, when their gauge will reach the level at which they must act, and starts that action for them.

## Build Session 1 evidence

Answers to the [Build Session 1 checklist](https://github.com/TrilemmaFoundation/Datathon-Season-2026/blob/main/build%20session%20checklist/build-session-1.md). Data figures were pulled from the ECCC hydrometric API on Oct 7, 2026; scripts are in [`evidence/`](evidence/).

### Problem evidence

**The problem is real and recurring.** The same farmland flooded twice in four years:

- **November 2021:** about 628,000 poultry, ~12,000 hogs and 420 dairy cattle died on and around Sumas Prairie, and about 1,100 farms were under evacuation order or alert ([Castanet](https://www.castanet.net/news/BC/353513/Thousands-of-poultry-pigs-cattle-killed-in-Abbotsford-flooding)).
- **December 2025:** the Nooksack overflowed into Abbotsford. 165 livestock farms were inside the evacuation area, 66 of them under order, and "farmers have been moving livestock out overnight" ([City of Abbotsford, Dec 11, 2025](https://www.abbotsford.ca/sites/default/files/2025-12/2025-12-11%20-%20Floodwaters%20cross%20into%20Abbotsford%20and%20Evacuation%20Orders%20expanded.pdf)). A Chilliwack River dike also breached ([Global News](https://globalnews.ca/news/11575062/bc-fraser-valley-flooding)).

**The pain is timing, not awareness.** A Sumas Way farm-market owner said that in 2021 they "had little time to prepare", and that in 2025, even with 20+ hours of siren warnings, uncertainty about *when and from where* water would rise made people feel unsafe ([The Cascade](https://ufvcascade.ca/the-2025-floods-effect-on-abbotsfords-farmers/)).

**Am I the N-of-1 user?** No. I am a Vancouver developer, not a floodplain farmer. That is the weakest part of this framing, so the first users are being recruited directly: a Sumas Prairie farm business affected in 2021 and 2025, and the BC Dairy and BC Poultry associations, which convened a roundtable of affected animal producers in January 2026 ([City of Abbotsford](https://www.abbotsford.ca/node/11732)). Interview status is tracked in [`evidence/user-outreach.md`](evidence/user-outreach.md). Until at least one farmer confirms the pain in their own words, the problem is supported by public evidence, not first-hand use.

**A single prompt or search does not solve it.** A chatbot has no live gauge feed and no calibrated error history for a specific gauge. Official tools give basin labels (RFC advisories), raw levels (Wateroffice) or evacuation orders after the fact. None says "your level, in X hours, with Y% confidence" and none acts on it. Whether Google Flood Hub covers these gauges is still being checked.

**Scope is a microproduct.** First version: ~7 Fraser Valley gauges, one threshold per user, one alert-and-approve flow, one public ledger.

### Data evidence

**Access — confirmed.** BC has 2,324 hydrometric stations in the ECCC API, 434 of them reporting in real time. For 7 demo gauges, the last 30 days of real-time data arrived at a 5-minute cadence with 8,552–8,756 rows each and no gap longer than 1.2 h:

| Gauge | Station | Real-time (30 d) | Daily history | Years with flow |
|---|---|---|---|---|
| Chilliwack R. at Vedder Crossing | 08MH001 | level + flow | 1911 → Jun 2026 | 90 |
| Chilliwack R. above Slesse Ck (upstream) | 08MH103 | level + flow | 1963 → Jun 2026 | 64 |
| Sumas R. near Huntingdon | 08MH029 | level + flow | 1935 → Dec 2024 | 51 |
| Nicomekl R. at 203 St, Langley | 08MH155 | level + flow | 1985 → Dec 2024 | 40 |
| Fraser R. at Mission | 08MH024 | level only | 1965 → Mar 2025 | 53 |
| Coquihalla R. below Needle Ck | 08MF062 | level + flow | 1965 → Feb 2025 | 41 |
| Slesse Ck near Vedder Crossing | 08MH056 | level + flow | 1967 → Oct 2011 | 45 |

Full table: [`evidence/station_summary.csv`](evidence/station_summary.csv).

**Permission — confirmed.** Open Government Licence – Canada: commercial use, redistribution and derived products allowed with attribution (see [`data-contract.md`](data-contract.md)).

**Signal — present, and it tells us what the model needs.**

![November 2021 flows relative to each gauge's typical yearly peak](evidence/nov-2021-fraser-valley.png)

- On Nov 15, 2021, Vedder Crossing ran at **2.5×** its typical yearly peak, the 2nd-highest annual peak in 90 years. In December 2025 it reached 1.2× and the upstream gauge 1.6×.
- Vedder Crossing has crossed its typical-yearly-peak level in **71 events since 1911 (15 since 2000)**, so there are labelled events to learn from. They are rare per gauge, so the model must pool gauges.
- In **23 of those 71 events**, flow the day before was under half the threshold. Daily data gives no warning; the model needs hourly data and precipitation forecasts.
- The upstream gauge was over its own threshold on the **same day** in 31 of 46 events, but on the **day before** in only 8. Travel time is under a day, so the upstream lead must be learned from 5-minute data.

**Data-quality issues found (and handled in the pipeline):**

- Approved daily history lags months behind (e.g. Sumas ends Dec 2024), and real-time files only cover 30 days. The gap between them is lost unless archived, so archiving starts in Build Session 2.
- The real-time feed contains ±99999 sentinel values (1 row at 08MH001, 9 at 08MH056).
- Gauges fail when they are needed most: Sumas has no daily values for Nov 16–17, 2021, and Coquihalla below Needle Creek has none from Oct 2021 to Jun 2022.
- Fraser at Mission reports level but no flow in real time.

### Taking into Build Session 2

1. Start the AMQP archive and 30-day backfill for the 7 gauges (then all 434 real-time BC gauges).
2. Persistence and trend baselines writing to the public hash-chained ledger every hour.
3. Training set from daily history; first LightGBM quantile model; walk-forward harness.
4. At least one farmer interview, recorded in [`evidence/user-outreach.md`](evidence/user-outreach.md).
5. Check Google Flood Hub coverage of these gauges and add it as a baseline if present.

## Problem brief

| | |
|---|---|
| **Target user** | Livestock and crop farmers on BC floodplains (first: Fraser Valley — Sumas Prairie, Chilliwack/Vedder, Nicomekl), plus riverside households and campgrounds. |
| **Problem** | Official River Forecast Centre (RFC) products are basin-level labels (High Streamflow Advisory → Flood Watch → Flood Warning). They don't say *when* a given gauge will reach the level at which *this* person needs 6 hours to move animals. Outside freshet season, RFC's CLEVER model updates once or twice a week. People watch raw gauge charts and guess. |
| **Why it matters** | In the November 2021 Sumas Prairie floods, about 628,000 poultry, ~12,000 hogs and 420 dairy cattle died, and about 1,100 farms were under evacuation order or alert. Moving animals takes hours; every extra hour of reliable warning is trailers that leave in time. |
| **Data inputs** | ECCC/Water Survey of Canada real-time water level and discharge (5-minute data, ~2,100 stations), ECCC daily historical hydrometric records, ECCC HRDPS precipitation forecasts. RFC advisories used only as a comparison baseline. |
| **Output utility** | Per gauge and per user threshold: P(crossing within 6/12/24/48 h), P10/P50/P90 peak level, median hours-to-crossing. Voice + SMS alert, approval step, then contact fan-out. |
| **Success metric** | Lead time gained over the official advisory at the same skill (hours), and calibrated forecasts that beat persistence (Brier skill score, CRPS), scored live on the public ledger. |

## What is new (and what isn't)

**Not new:** river gauges, flood maps, global river forecasts (e.g., Google Flood Hub), or alerting apps.

**New:**
1. **Personal action thresholds** expressed as calibrated hours-to-crossing probabilities, not basin labels.
2. **Hourly, scored forecasts at tributary gauges**, published to an append-only ledger and compared against persistence, trend extrapolation, RFC models and Google Flood Hub wherever they cover the same gauge.
3. **An agent that runs the person's pre-approved plan** — call, confirm, notify contacts, escalate — instead of just showing a chart.

## Data and usage rights

Every material input has documented rights below. Full records live in [`data-contract.md`](data-contract.md).

| Source | Use | Licence | Traffic light |
|---|---|---|---|
| ECCC real-time hydrometric data | Core model input; ledger scoring | Open Government Licence – Canada | 🟢 Green |
| ECCC historical hydrometric (daily) | Training data | Open Government Licence – Canada | 🟢 Green |
| ECCC MSC Datamart / GeoMet (HRDPS precipitation) | Model feature | ECCC Data Servers End-use Licence (attribution required) | 🟢 Green |
| BC River Forecast Centre advisories and CLEVER/COFFEE forecasts | **Comparison baseline only** — linked and cited, never republished | Province of BC website terms (under review) | 🟡 Yellow |
| Google Flood Hub | Comparison baseline only, where it covers a gauge | Google terms (under review) | 🟡 Yellow |

```yaml
- source: ECCC Real-time Hydrometric Data
  url: https://open.canada.ca/data/dataset/65d3a88b-eb09-4fd9-ac44-cf42dc1f7444
  license: OGL-Canada-2.0
  license_url: https://open.canada.ca/en/open-government-licence-canada
  access_method: AMQP push (dd.weather.gc.ca, hydrometric.csv.#) + HTTPS CSV + OGC API
  commercial_use: true
  redistribution: true
  attribution_required: true
  share_alike: false
  terms_reviewed: 2026-10-06
  notes: Provisional data; Datamart keeps only the last 30 days of real-time files, so we archive from day one.

- source: ECCC MSC Datamart / GeoMet (HRDPS, observations)
  url: https://eccc-msc.github.io/open-data/readme_en/
  license: ECCC Data Servers End-use Licence
  license_url: https://eccc-msc.github.io/open-data/licence/readme_en/
  access_method: HTTPS + AMQP
  commercial_use: true
  redistribution: true
  attribution_required: true   # "Contains data from Environment and Climate Change Canada"
  share_alike: false
  terms_reviewed: 2026-10-06
  notes: Large GRIB2 files; we subset to basin polygons.

- source: BC River Forecast Centre advisories and model forecasts
  url: https://bcrfc.env.gov.bc.ca/warnings/
  license: Province of BC website terms (to confirm)
  access_method: HTTPS (HTML/PDF)
  commercial_use: unknown
  redistribution: false        # we link and cite, never re-host
  attribution_required: true
  share_alike: false
  terms_reviewed: pending
  notes: Used only as a scoring baseline. Not a core dependency.
```

**Personal data:** users' phone numbers, contact lists and thresholds are stored encrypted in a Canadian region, used only to deliver alerts, and deleted on request. Contacts must opt in by SMS before receiving anything.

## How it works

```text
ECCC AMQP / Datamart / GeoMet
        │
        ▼
  Ingestor (dedupe, schema checks) ──► Raw archive (Parquet, Canadian region)
        │
        ▼
  TimescaleDB ──► Feature builder ──► Forecast model (hourly, per station)
                                              │
                         ┌────────────────────┼─────────────────────┐
                         ▼                    ▼                     ▼
                Public ledger API      Risk detector          Scoring job
                (hash-chained)              │               (vs observed)
                                            ▼
                                    Agent: call user → wait for approval
                                    → text contacts → escalate if no reply
```

| Layer | Choice |
|---|---|
| Ingestion | Python asyncio AMQP consumer; 30-day Datamart backfill; HRDPS basin subsetting |
| Storage | TimescaleDB (Postgres 16) + Parquet archive; DuckDB for offline training |
| Model | LightGBM quantile regression + isotonic calibration; discrete-time hazard for time-to-crossing |
| Serving | FastAPI, hourly scoring |
| Agent | State machine (detect → compose → call → await approval → notify → escalate); voice + SMS provider |
| Front end | Next.js PWA: gauge chart with forecast fan, threshold setup, public ledger |
| Observability | Prometheus/Grafana (feed lag, ingest rate, alert latency); data-quality checks on every batch |
| Deployment | Single VM + managed Postgres in a Canadian region |

Full data architecture record: [`architecture.md`](architecture.md).

## How we will prove it works

- **Walk-forward backtest by water year (2005–2025).** Train on years ≤ Y, test on Y+1; hold out November 2021 entirely until the final run. Precipitation features use forecasts as issued, not observed rain.
- **Baselines:** persistence ("level stays the same"), linear trend extrapolation (what people do today), RFC advisory level, RFC CLEVER/COFFEE where published, Google Flood Hub where it covers the gauge.
- **Metrics:** Brier score and reliability diagram (exceedance), CRPS (quantiles), hit rate / false-alarm ratio, and median lead time gained over the advisory.
- **Live public ledger:** every hourly forecast for every station, timestamped and SHA-256 chained, from the day ingestion starts. The chain head is committed to this repo daily so anyone can verify nothing was edited after the fact.
- **2021 and 2025 replays:** the hour FloodLead would have crossed 70% for the Sumas and Chilliwack/Vedder gauges, against the hour of each RFC advisory upgrade and the observed peak.

All performance numbers in this repo will come from these experiments. None are claimed in advance.

## Go / no-go criteria

| Gate | Go if | Otherwise |
|---|---|---|
| Data access | AMQP archive running and 30-day backfill complete for ≥ 40 BC stations | Switch to HTTPS polling of Datamart CSVs |
| Licence | All core inputs Green (done for ECCC) | Drop any Yellow source to "link only" |
| Model skill | Walk-forward Brier skill score vs persistence ≥ 0.10 at 12 h, calibration error ≤ 0.05 | Ship "gauge watch + trend" mode without probability alerts, and say so |
| Originality | Our personal-threshold + agent + public-scoring combination isn't already offered for these gauges | Re-scope the claim; keep competitor as a baseline |
| Agent safety | Voice/SMS flow passes opt-in, approval and stale-data tests | No outbound messages to contacts |

## Plan to Demo Day

| Date | Session | Deliverable |
|---|---|---|
| Oct 5 | Build Session 1 — Framing | This README, data contract, go/no-go gates |
| Oct 7 | Build Session 2 — Building | Archive live; persistence baseline + ledger running; first LightGBM model |
| Oct 9 | Build Session 3 — Working in Public | Hourly forecasts live; PWA deployed; voice/SMS approval flow working |
| Oct 10–12 | — | 2021 replay; walk-forward results; tests; agent-readable registry entry |
| Oct 13 | Demo Day | Live ledger scores since Oct 7, 2021 replay, end-to-end alert on stage |

**If behind, cut in this order:** HRDPS features (use upstream gauges only) → calendar holds → non-English voice → challenger models.

## Repository layout

Follows the [Build Trilemma folder contract](https://build.trilemma.foundation/standards/folder-contract).

```text
README.md          ← you are here
AGENTS.md          instructions for collaborator agents
product.yaml       machine-readable product record
product-brief.md   users, pains, wedge, non-goals
architecture.md    data architecture record
data-contract.md   inputs, freshness, lineage, privacy, usage rights
evaluation.md      metrics, thresholds, kill criteria
roadmap.md         next bets and explicit rejects
demo.md            replayable demo scripts
src/               application code
tests/             unit, contract, replay and calibration tests
```

## Non-goals

- Issuing or replacing official flood warnings or evacuation orders.
- Inundation mapping at parcel level.
- Snowmelt-dominated basins in the first release (rain-driven coastal tributaries first).
- Contacting emergency services automatically.

## Attribution

Contains information licensed under the Open Government Licence – Canada. Contains data from Environment and Climate Change Canada.

## References

- Trilemma Foundation — [Request for Microproducts](https://build.trilemma.foundation/docs/request-for-microproducts), [Frame](https://build.trilemma.foundation/docs/playbook/frame), [Data Licensing](https://build.trilemma.foundation/docs/playbook/frame/data-licensing)
- [ECCC Real-time Hydrometric Data](https://open.canada.ca/data/dataset/65d3a88b-eb09-4fd9-ac44-cf42dc1f7444) · [MSC Open Data](https://eccc-msc.github.io/open-data/readme_en/)
- [BC River Forecast Centre — Flood Warnings and Advisories](https://bcrfc.env.gov.bc.ca/warnings/) · [CLEVER model](https://bcrfc.env.gov.bc.ca/freshet/map_clever.html)
- 2021 Sumas Prairie losses: [Castanet](https://www.castanet.net/news/BC/353513/Thousands-of-poultry-pigs-cattle-killed-in-Abbotsford-flooding), [CBC](https://www.cbc.ca/lite/story/1.6260251)

## Licence

Code: MIT. Data remains under its publishers' licences (see above).
