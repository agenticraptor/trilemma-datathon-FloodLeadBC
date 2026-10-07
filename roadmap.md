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

## Explicit rejects

| Rejected | Why |
|---|---|
| Issuing evacuation guidance | Official orders belong to local authorities; we link to them |
| Scraping private or unlicensed feeds | Violates the data contract |
| Parcel-level inundation maps | Needs DEM and hydraulic modelling beyond microproduct scope |
| Auto-calling 911 | Safety and liability; users call emergency services themselves |
| Snowmelt basins in v1 | Different physics; would dilute the first proof |
| Chatbot front end | Adds no forecast skill; the value is the calibrated number and the action |
