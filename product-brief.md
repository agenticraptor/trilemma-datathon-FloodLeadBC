# Product brief — FloodLead BC

## One sentence

FloodLead tells one floodplain farmer, in hours, when their river gauge will reach the level at which they must act, and starts their action plan when it does.

## Target users

| Segment | Who | Why they care |
|---|---|---|
| Primary | Livestock farmers on BC floodplains, starting with the Fraser Valley (Sumas, Vedder, Chilliwack, Nicomekl/Serpentine) | Moving animals takes hours. In November 2021 about 628,000 poultry, ~12,000 hogs and 420 dairy cattle died on and around Sumas Prairie, and about 1,100 farms were under evacuation order or alert. |
| Secondary | Riverside households, campgrounds, small businesses near gauged rivers | Need to know when to move cars, pumps and people. |
| Tertiary | Volunteers and truckers who help move animals | Need a clear, early "come now" request instead of a midnight scramble. |

## The pain (today's workflow)

1. The BC River Forecast Centre (RFC) posts a basin-level label: High Streamflow Advisory → Flood Watch → Flood Warning.
2. The farmer opens a raw Water Survey of Canada gauge chart and guesses where the line is heading.
3. Outside freshet season, RFC's CLEVER model is updated only once or twice a week.
4. Decisions to move animals get made late, at night, by phone, with no shared plan.

**The repeated pain:** every atmospheric-river season, the same farmers ask the same question — *how many hours do I have?* — and nothing answers it for their gauge and their threshold.

## The wedge

A personal action threshold ("move cattle at 4.2 m on the Vedder at Vedder Crossing") turned into a calibrated probability of crossing within 6/12/24/48 hours, plus an agent that calls the farmer, waits for a yes, and texts their helpers.

## What is new versus incumbents

| Incumbent | What it does | What it does not do |
|---|---|---|
| BC River Forecast Centre | Basin advisories; CLEVER/COFFEE model forecasts at selected stations | Personal thresholds, hourly probabilistic lead time, actions |
| Water Survey of Canada / Wateroffice | Raw 5-minute gauge levels | Any forecast |
| Google Flood Hub | Global AI river forecasts and alerts | Personal action thresholds, contact fan-out, public scoring against BC's own models (BC gauge coverage still to be checked) |
| Regional district alerts (FVRD, RDKB) | Evacuation orders once issued | Lead time before an order exists |

## Success metric

- **Primary:** median hours of lead time gained over the RFC advisory at equal or better false-alarm rate (2021 replay and walk-forward backtest).
- **Secondary:** Brier skill score vs persistence ≥ 0.10 at 12 h; calibration error ≤ 0.05; live ledger skill since launch.
- **Usage:** at least 3 real farmers or riverside households set a threshold and receive a test alert by Demo Day.

## Non-goals

- Issuing or replacing official warnings or evacuation orders.
- Parcel-level inundation mapping.
- Snowmelt-dominated basins in v1.
- Calling emergency services on anyone's behalf.
