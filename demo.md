# Demo — FloodLead BC

Scripts for humans and agents to replay the happy path.

## Human demo (4 minutes)

1. **0:00 — The problem.** Photo of Sumas Prairie, November 2021. "About 628,000 birds, 12,000 hogs and 420 cows died. The warning said 'Flood Watch'. It didn't say *when*."
2. **0:40 — Setup.** On the PWA, pick the Chilliwack River at Vedder Crossing gauge (08MH001), set a "move cattle" level, add a trucker contact (who has opted in).
3. **1:20 — 2021 replay.** Play November 13–16, 2021 at high speed. The forecast fan rises; when P(crossing within the needed lead time) passes the threshold, FloodLead calls the phone on stage. Press 1 to approve. The trucker's phone gets the text and replies YES.
4. **2:30 — Proof.** Walk-forward reliability curve; lead time gained vs the advisory; false-alarm rate, shown honestly.
5. **3:15 — Live.** Open the public ledger: forecasts issued since Oct 7, hash-chained, with live skill vs persistence and trend.
6. **3:45 — Close.** "Open data, open ledger, agent-readable API. Not a warning service — a head start."

## Agent / CLI replay

```bash
# 1. Start services
docker compose up -d

# 2. Load the 2021 replay window for demo stations
python -m floodlead.replay --start 2021-11-13 --end 2021-11-17 --stations demo --speed 600

# 3. Create a threshold and a test contact (sandbox messaging)
curl -X POST localhost:8000/v1/thresholds \
  -H 'Content-Type: application/json' \
  -d '{"station_id":"08MH001","label":"move cattle","level_m":<level>,"lead_needed_h":6,"risk_pref":0.6}'

# 4. Watch the agent state machine
python -m floodlead.agent --watch --dry-run

# 5. Verify the ledger chain
python -m floodlead.ledger verify --since 2026-10-07
```

Demo stations are confirmed in [`evidence/station_summary.csv`](evidence/station_summary.csv). Threshold levels are set from each gauge's history once the model is trained.

## Expected outputs

- Agent log shows `detect → compose → call_user → await_approval → notify_contacts` with timestamps.
- `ledger verify` prints `OK` and the current head hash, which matches the latest line in `ledger/heads.txt`.
- `/v1/scores/summary` returns skill for the model and every baseline.

## Judge questions to expect

| Question | Answer |
|---|---|
| Isn't this the River Forecast Centre's job? | They forecast basins. We score ourselves against them in public and only alert on personal thresholds, linking to official orders. |
| How do you know you're not overfitting? | Water-year walk-forward splits, the 2021 holdout, basin-grouped splits, and a live ledger nobody can edit after the fact. |
| What about Google Flood Hub? | It's a baseline wherever it covers the gauge. Our difference is the personal threshold, the action agent and public scoring against BC's own models. |
| What if the data feed stops? | Users get a "data gap" notice, never silence, and stale forecasts are suppressed. |
