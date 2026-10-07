# Test fixtures

Small **real** payloads, trimmed. They were taken on 2026-10-07 from the raw archive (`/srv/floodlead/archive`) or fetched directly, and are kept small so tests stay fast. Nothing is synthetic except the trims noted below.

| File | Source | Trim |
|---|---|---|
| `eccc_hourly_08MH001.csv` | ECCC Datamart `hourly/BC_08MH001_hourly_hydrometric.csv` (Last-Modified 2026-10-07 21:01:28 UTC, sha256 `de56c9c2…`) | header + first 6 rows + last 2 rows |
| `eccc_daily_08NJ026_sentinel.csv` | ECCC Datamart `daily/BC_08NJ026_daily_hydrometric.csv` | header + 5 consecutive rows around a real `99999.000` level sentinel (2026-10-06T15:50-08:00) |
| `eccc_listing_hourly.html` | `https://dd.weather.gc.ca/today/hydrometric/csv/BC/hourly/` | first 14 lines (6 file entries, all stamped 2026-10-07 21:01) |
| `usgs_continuous_12210700.json` | USGS OGC v1 `continuous/items`, North Cedarville, June 2026 | 3 stage + 3 discharge features; `links` cut to two, and the `next` link's cursor replaced by the placeholder `EXAMPLE` |
| `usgs_time_series_metadata.json` | USGS OGC v1 `time-series-metadata/items` | only sites 12210700 and 12210500; `links` removed |
| `nwps_gauge_NRKW1.json` | NOAA NWPS `gauges/NRKW1` | only identity, `flood.categories`, units |
| `nwps_stageflow_NRKW1.json` | NOAA NWPS `gauges/NRKW1/stageflow` (issued 2026-10-07T15:36Z) | last 3 observed points, first 4 forecast points |

Credits: Contains information licensed under the Open Government Licence – Canada; contains data from Environment and Climate Change Canada. Credit: U.S. Geological Survey. NOAA National Weather Service (not affiliated with or endorsed by NOAA/NWS).
