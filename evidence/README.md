# Evidence

Reproducible Build Session 1 evidence. Python standard library only (plus matplotlib for the chart).

```bash
cd evidence
python pull_gauges.py        # pulls 30-day real-time + daily history for 7 Fraser Valley gauges (~1 min)
python summarize.py          # writes station_summary.csv and prints the signal checks
python chart_nov_2021.py     # draws nov-2021-fraser-valley.png
```

| File | What it is |
|---|---|
| `station_summary.csv` | Coverage, cadence, history and data-quality counts per gauge (pulled Oct 7, 2026) |
| `nov-2021-fraser-valley.png` | November 2021 daily flow as a multiple of each gauge's typical yearly peak |
| `user-outreach.md` | First-user recruitment and interview log |

Raw station JSON is not committed; re-run `pull_gauges.py` to fetch it.

Contains information licensed under the Open Government Licence – Canada. Contains data from Environment and Climate Change Canada.
