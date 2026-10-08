# FloodLead BC — brief

> **Authorship:** drafted by Claude (the project's AI supervisor) at Pranay's request, from his decisions during the build and the evidence in this repository. The Build Session 2 checklist asks for a brief in the author's own words; this one is AI-drafted, and is labelled so that nobody is misled.

## 1. The problem, and when it happens

Farmers on the Fraser Valley floodplain, starting with Sumas Prairie, need to know *in hours* when the river gauge that matters to them will reach the level at which they must act: move animals, check pumps, leave. The problem arrives with autumn and winter atmospheric-river storms, as in November 2021 and December 2025.

Official products describe whole basins (BC advisories, watches and warnings) or, on the US side, give a forecast for a few gauges that is issued about once a day. None of them says "your level, in X hours, with Y % confidence", and none of them shows how often its past forecasts were right.

## 2. A real example, and why it matters to the author

The flood path is concrete. When the Nooksack River in Washington overtops near Everson, the water flows north across the border into Sumas Prairie. It happened in November 2021 and again in December 2025. In the data FloodLead already holds, the overflow gauge at SR 544 (USGS 12211195) first recorded water when the upstream North Cedarville gauge (USGS 12210700) stood at about 147.5 ft:

| Flood | North Cedarville crossed minor flood stage (146.5 ft) | Overflow first recorded | Hours between |
|---|---|---|---|
| November 2021 | 2021-11-14 21:30 UTC | 2021-11-15 02:25 UTC | 4 h 55 min |
| December 2025 | 2025-12-10 20:15 UTC | 2025-12-11 00:45 UTC | 4 h 30 min |

That is two floods only. Stage 2 recomputes it for every flood on record.

Pranay lives in Vancouver, not on a farm. He chose this problem after asking how floodplain flooding reaches him and his family in the city. In 2021 the same storm cut Vancouver off from the rest of Canada by road and rail, emptied grocery shelves and rationed fuel. In December 2025, Highway 1 across Sumas Prairie closed for almost 48 hours. The sources are in the README section "Why this is my problem too".

## 3. Evidence and data

- **Harm:** in November 2021 about 628,000 poultry, ~12,000 hogs and 420 dairy cattle died, and about 1,100 farms were under evacuation order or alert ([Castanet](https://www.castanet.net/news/BC/353513/Thousands-of-poultry-pigs-cattle-killed-in-Abbotsford-flooding)). In December 2025, 165 livestock farms were inside the evacuation area, 66 of them under order ([City of Abbotsford](https://www.abbotsford.ca/sites/default/files/2025-12/2025-12-11%20-%20Floodwaters%20cross%20into%20Abbotsford%20and%20Evacuation%20Orders%20expanded.pdf)).
- **The pain is timing:** a Sumas Way farm-market owner said they "had little time to prepare" in 2021 ([The Cascade](https://ufvcascade.ca/the-2025-floods-effect-on-abbotsfords-farmers/)).
- **Data in use, all openly licensed:** ECCC real-time levels and flows for about 430 BC gauges (archived since October 7, 2026, because ECCC keeps only 30 days); USGS 15-minute data for the Nooksack and Sumas gauges since 2004–2007; NOAA's official forecasts and flood stages for the Nooksack. Licences and conditions are in [`data-contract.md`](data-contract.md).

## 4. What existing alternatives leave unresolved

| Alternative | What it gives | What is missing |
|---|---|---|
| BC River Forecast Centre | Basin-level advisories, watches and warnings | Hours until *a given gauge* reaches *a given level* |
| ECCC Wateroffice | Raw gauge levels | Any forecast; about an hour behind in real time |
| NOAA NWS (Nooksack) | Official forecast at North Cedarville and Ferndale, 6-hourly, issued about once a day, plus flood stages | Probabilities, personal levels, Canadian gauges, and the overflow point itself (observed only) |
| Watching the gauge chart | What people do today | Any honest sense of how fast it will rise, or how sure to be |

None of them publishes a scored record of its own forecasts, and none acts on one person's plan.

## 5. The useful result the app makes possible

- **Now (Stage 2):** one screen shows how far North Cedarville is from the level at which the overflow began, NOAA's official forecast, and a baseline chance of reaching any level the user types within 6–48 h, each with its data age. A replay shows how the same gauge behaved before the 2021 and 2025 overflows began.
- **Next:** a model that must beat persistence, trend and NOAA in the public ledger before it is trusted, and then an opt-in call or text when the chance of reaching the user's level passes their own risk threshold.

## Key choices, and why

| Choice | Why |
|---|---|
| Forecast the level that matters to one person, in hours | The pain is timing, not awareness |
| Every forecast goes into a public, hash-chained ledger before the truth is known, and is scored against persistence, trend and NOAA | Trust has to be earned in public, and the numbers have to be checkable |
| Archive first | ECCC deletes real-time data after 30 days, so history not kept now is lost |
| US gauges are core | The Nooksack overflow is what floods Sumas Prairie |
| Not a warning service; alerts only with recorded consent; personal data stays in Canada | Safety and privacy come before features |

**Not claimed here:** no skill numbers yet; they will come only from the live scorer, with a run ID. First-hand farmer interviews are in progress ([`evidence/user-outreach.md`](evidence/user-outreach.md)).
