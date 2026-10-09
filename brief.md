# FloodLead BC — brief

> **Authorship:** drafted by Claude (the project's AI supervisor) at Pranay's request, from his decisions during the build and the evidence in this repository. The Build Session 2 checklist asks for a brief in the author's own words; this one is AI-drafted, and is labelled so that nobody is misled.
>
> **Revised Oct 9, 2026** after a sourced review of what farmers actually have today: [`docs/research/fraser-valley-flood-warning-status-quo.md`](docs/research/fraser-valley-flood-warning-status-quo.md). That review corrected earlier claims in this brief; the corrections are listed at the end.

## 1. The problem, and when it happens

Farmers on Sumas Prairie need to know, early enough and in daylight, **whether water is coming to their farm, when, and how sure anyone is**. Then they can move young stock first, line up trailers and receiving farms, and move milking herds and poultry before the roads close. The problem comes with autumn and winter atmospheric-river storms, as in November 2021 and December 2025.

Upstream forecasting is not the weak link any more. US forecasters flagged the December 2025 Nooksack flood about 5 days ahead, and their first North Cedarville flood warning came about 14 hours before the river crossed flood stage. The weak link is **the last mile, from the Everson overflow to the barn**:
- **No probabilities.** No official product gives a calibrated probability.
- **Low crest forecasts.** The first official crest forecasts were about 2 ft too low a day ahead, in both floods: 148.9 ft forecast against 150.76 ft observed in 2021, and 148.4 ft against about 150.5 ft in 2025.
- **No arrival times.** Nobody forecasts when overflow water reaches the border or a given road. In 2025 the City's 7-hour rule of thumb was off: the water took roughly 10–20 hours.
- **No night-time phone push.** Abbotsford's own alerts are web, email and door-knocking.
- **No track record.** Nobody publishes how accurate their forecasts have been.

## 2. A real example, and why it matters to the author

The flood path is concrete. When the Nooksack River in Washington overtops near Everson, the water flows north across the border into Sumas Prairie.

- **November 2021.** The US Weather Service warned at 3:40 PM PST on Nov 14 that the river would overflow "toward Sumas and the Canadian border". Abbotsford's first alerts touching the prairie came about 9 hours later. Its evacuation orders came after the water, and dairy farmer Chelsea Meier was woken by water at about 4 AM on Nov 16: "We got no warning" ([CBC](https://www.cbc.ca/news/canada/british-columbia/meier-farm-sumas-prairie-recover-floods-abbotsford-warning-system-failure-1.6268183)).
- **December 2025.** Alerts came 12–18 hours before the water, much of it overnight.
- **Every minor-stage event since 2015.** In the data FloodLead holds, water reached the overflow path in 7 of 13 events where North Cedarville (USGS 12210700) crossed minor flood stage (146.5 ft). It came a median 4.9 hours later (range 0.1–6.4 hours). The river level at which the overflow began varied from 146.2 to 148.4 ft, so no single level predicts it.

Pranay lives in Vancouver, not on a farm. He chose this problem after asking how floodplain flooding reaches him and his family in the city. In 2021 the same storm cut Vancouver off from the rest of Canada by road and rail, emptied grocery shelves and rationed fuel. In December 2025, Highway 1 across Sumas Prairie closed for almost 48 hours. The sources are in the README section "Why this is my problem too".

## 3. Evidence and data

- **Harm:**
  - In November 2021 about 628,000 poultry, ~12,000 hogs and 420 dairy cattle died (BC Dairy puts cattle deaths near 500), and about 1,100 farms were under evacuation order or alert ([Castanet](https://www.castanet.net/news/BC/353513/Thousands-of-poultry-pigs-cattle-killed-in-Abbotsford-flooding)).
  - In December 2025, 165 livestock farms were inside the evacuation area, 66 of them under order ([City of Abbotsford](https://www.abbotsford.ca/sites/default/files/2025-12/2025-12-11%20-%20Floodwaters%20cross%20into%20Abbotsford%20and%20Evacuation%20Orders%20expanded.pdf)).
- **Lead time decides outcomes.** A 450-head dairy herd was moved to seven farms in one day and lost no animals. A broiler farmer moved about half his birds before "time ran out" and lost about 40,000. Both cases are in the review.
- **Data in use, all openly licensed:**
  - ECCC real-time levels and flows for about 430 BC gauges, archived since October 7, 2026 (ECCC keeps only 30 days);
  - USGS 15-minute data for the Nooksack and Sumas gauges since 2004–2007;
  - NOAA's official forecasts and flood stages;
  - the archive of NWS flood warnings actually issued;
  - rainfall observations and archived rainfall forecasts.

  Licences are in [`data-contract.md`](data-contract.md).

## 4. What existing alternatives leave unresolved

| Alternative | What it gives | What is missing |
|---|---|---|
| NOAA NWS (Nooksack) | Flood watch days ahead; official forecast at North Cedarville (6-hourly steps, about 7 days) and Ferndale; river flood warnings with a forecast crest; an Everson overflow warning toward the border | Probabilities; first crests about 2 ft low in both big floods; no forecast at the overflow gauges; no phone alerts for river warnings; no published accuracy record |
| BC River Forecast Centre | Basin advisories, watches and warnings; station forecasts for Sumas at Huntingdon and Chilliwack at Vedder (COFFEE 5-day, CLEVER 10-day) | Deterministic, in daily steps, and COFFEE runs only during rain events; no forecast of the Nooksack overflow reaching Canada (its Dec 2025 warning relayed the US forecast); no push alerts |
| City of Abbotsford | Evacuation alerts and orders (web, email, door-knocking); a 7-hour overflow-to-Abbotsford rule of thumb | Night-time phone push; arrival-time estimates that held in 2025 |
| FVRD and Chilliwack (Alertable), BC Emergency Alerts | Opt-in app and SMS alerts; province-wide alerts reserved for imminent threats to life (never used for a Fraser Valley flood) | One channel covering all of Sumas Prairie |
| Watching the gauges | ECCC and USGS observations | Any forecast, any sense of how sure to be |

No one publishes a scored record of their own forecasts. And none of these channels acts on one person's plan.

## 5. The useful result FloodLead makes possible

- **Now:** live levels against official stages, NOAA's forecast as published, baseline chances for any level you type, and a replay of every past flood, all from data checkable in a public ledger.
- **Next, in order of how certain the value is:**
  1. **Relay and translate.** Push the warnings that already exist, plus overflow-gauge triggers, to a farmer's phone in farm terms. Replays from archived timestamps suggest this alone would have reached farmers about 9 hours before Abbotsford's first alert in 2021, and about 5–7 daylight hours before it in 2025. Stage 4 recomputes this with rules frozen in advance.
  2. **Score the official forecasts.** Publish how far past official crest forecasts were from what happened, so farmers know how much to trust a "moderate" forecast.
  3. **Calibrated probabilities and hourly timing.** For example, the chance of major flooding at North Cedarville and the timing of the overflow, from a model that must beat persistence, the trend and the official warnings on floods it never saw. This is unproven until that test is run, and it will be reported whatever it shows.

## Key choices, and why

| Choice | Why |
|---|---|
| Focus on the last mile from the Everson overflow to the barn, not on out-forecasting NWS | That is where 2021 failed and where 2025 was still weak; beyond about a day, rainfall forecasts limit everyone |
| Every forecast goes into a public, hash-chained ledger before the outcome is known, and is scored | Trust has to be earned in public, and no agency here publishes a track record |
| Archive first | ECCC deletes real-time data after 30 days |
| A pre-registered test against persistence, trend, the 7-hour rule and the official warnings actually issued | So that we do not fool ourselves or the judges |
| Not a warning service; alerts only with recorded consent; personal data stays in Canada | Official alerts carry legal weight and relocation reimbursement; FloodLead complements them |

**Not claimed here:**
- No skill numbers yet; they will come only from the live scorer or the pre-registered test, with run IDs.
- First-hand farmer interviews have not been done ([`evidence/user-outreach.md`](evidence/user-outreach.md)).
- Big overflows are rare, and the planned 2026 replacement of the SR 544 overflow culvert with a bridge will change the overflow's behaviour. Any proof is provisional.

### Corrections on Oct 9, 2026

- **Quote attribution.** Earlier versions quoted "a Sumas Way farm-market owner" saying they "had little time to prepare". The article does not say Sumas Way, and the wording was a paraphrase (the article has "barely had any time to prepare"). That quote has been removed.
- **BC station forecasts.** Earlier versions said BC offers only basin-level products. The River Forecast Centre also publishes station forecasts (COFFEE and CLEVER).
- **The 147.5 ft overflow level.** Earlier versions suggested the overflow begins near 147.5 ft, based on two floods. Across 7 overflows the level ranged from 146.2 to 148.4 ft.
