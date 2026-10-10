# Roadmap — FloodLead BC

## Now (to Demo Day, Oct 13, 2026)

| Date | Goal | Done when |
|---|---|---|
| Oct 7 | Build Session 2 — Building | AMQP archive live; 30-day backfill; persistence baseline + ledger publishing for ~40 stations |
| Oct 8 | First model | HYDAT training set; LightGBM quantile v1; walk-forward harness; first calibration plot |
| Oct 9 | Build Session 3 — Working in Public | Hourly forecasts live; PWA deployed; voice/SMS approval flow working end to end |
| Oct 10–12 | Proof | 2021 replay; walk-forward results in `evaluation.md`; tests green; `llms.txt` and registry entry |
| Oct 13 | Demo Day | Model frozen at noon; live ledger scores since Oct 7 |

**Cut order if behind:** HRDPS features → calendar holds → non-English voice → challenger models.

## Next bets (after Demo Day)

1. Expand to all BC real-time stations and to Vancouver Island and Okanagan tributaries.
2. Sub-daily model trained on the self-built 5-minute archive once it has a full fall/winter season.
3. Upstream travel-time learning across the Fraser and Nooksack systems.
4. Shared farm plans: one threshold, many helpers, with roles and check-ins.
5. Punjabi voice and SMS by default for Fraser Valley users who choose it.
6. Contribute a dataset guide for the self-built sub-daily archive to the Trilemma data catalog.
7. A live shadow archive of AI and physics rainfall forecasts: AIFS, AIGFS/HGEFS, IFS, HRDPS, HRRR and NBM, logged as issued and scored storm by storm against the basin gauges. AI rain becomes a model feature only after at least 30 scored wet days show lower 24 h and 48 h CRPS than HRDPS and NBM (Stage 3 addendum 2; R0 on Oct 10 found AIFS available at day-1 and day-2 leads).

## Explicit rejects

| Rejected | Why |
|---|---|
| Issuing evacuation guidance | Official orders belong to local authorities; we link to them |
| Scraping private or unlicensed feeds | Violates the data contract |
| Parcel-level inundation maps | Needs DEM and hydraulic modelling beyond microproduct scope |
| Satellite imagery or vision models as forecast inputs | Free radar revisits about every 3 days, clouds blind optical sensors, and in both floods every satellite view came after the gauges had shown the overflow (Stage 3 addendum 2; `docs/research/satellite-imagery-for-flood-prediction.md`) |
| Auto-calling 911 | Safety and liability; users call emergency services themselves |
| Snowmelt basins in v1 | Different physics; would dilute the first proof |
| Chatbot front end | Adds no forecast skill; the value is the calibrated number and the action |
