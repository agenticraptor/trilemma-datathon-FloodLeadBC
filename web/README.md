# FloodLead BC web app (`web/`)

A static, no-build-step app: `index.html`, `app.js` (vanilla ES2020), `style.css`, and uPlot 1.6.32
vendored under `vendor/uplot/` (MIT, see `vendor/uplot/README.md` for source and sha256).
It makes **no third-party requests** (no CDNs, web fonts or analytics) and works under
`Content-Security-Policy: default-src 'self'`: no inline scripts, inline styles or event-handler attributes.

## Screens (hash router)

| Route | Screen |
|---|---|
| `#/` | **Sumas Prairie overflow watch** (default, the demo path): North Cedarville now vs. the NWS flood stages, the Overflow SR 544 gauge, a 7-day chart with NOAA's official forecast and the FloodLead baseline, FloodLead chances, your own level, the 2021/2025 replay, the ledger panel; then **Fraser Valley gauges** (latest level, data age and the position against each gauge's typical yearly peak, linking to `#/station/<id>`; a "Jump to the Fraser Valley gauges" button in the hero scrolls there) |
| `#/stations` | Station picker: every gauge, searchable by name or ID |
| `#/station/<id>` | One station: latest level, official thresholds, 7-day chart, latest FloodLead baseline forecast |
| `#/track-record` | **Track record** (one scorer run, its ID on every table): the plain-language statements first, then forecasts issued (count, since when, gaps), the ledger chain head and latest public anchor with the two "verify it yourself" commands, a table per source (ECCC BC gauges, USGS Nooksack/Sumas gauges) of fair CRPS, CRPSS, MAE and MAE skill against pure persistence per model and horizon with n pairs, stations and days, and the NOAA matched-pair count |

On every page:

- **"How to read this"**: a collapsed `<details>` panel under the header (static HTML in `index.html`, so it works
  without `app.js`): stage and gauge datum, data age and provisional data, "chance of reaching", FloodLead
  baseline vs NOAA official, what the ledger proves.
- **"Was this useful?"**: the last card of every route. Yes / No toggles plus optional text (max 1,000
  characters, live count); no name, email or phone fields. Submit is disabled until Yes/No or text is set. It sends
  `POST /v1/feedback` with `{"route", "station_id", "useful", "text", "app_version": "stage-03"}`; `station_id` is
  the station of a `#/station/<id>` page and `null` on pages that show several stations. 202 → "Thank you…" and
  the form resets; 429 → "Too many submissions…"; 400/413/422 → the response's `detail` as text; a network error or
  snapshot mode (no API) → "Feedback cannot be sent from the offline snapshot." (no request is made once the app
  knows it is on snapshot data). The typed text is never rendered anywhere, and server messages are set as text
  only. A link "Prefer GitHub? Open an issue" opens a new GitHub issue with the `feedback.yml` template.

## Run it

- **Production / full stack:** Caddy serves this directory at `https://<PUBLIC_HOSTNAME>/` and the API at
  `/v1/...` on the same origin. The app calls the live API.
- **Locally, no setup (snapshot mode):**

  ```sh
  python3 -m http.server -d web 8080
  # open http://localhost:8080/
  ```

  There is no API behind `http.server`, so the app loads the prepared files in `web/data/snapshot/` and shows
  a banner "Snapshot from <time> — live API not reachable".
- **Refresh the snapshot** (backend CLI, against the live database): `floodlead export-demo`
  writes `web/data/snapshot/*.json`.

## How data loading and snapshot mode work

All data goes through one helper, `api(path)` in `app.js`:

1. It `fetch`es `path` (e.g. `/v1/health`) on the same origin, with a 12 s timeout.
2. **2xx with a JSON body** → used as is.
3. **404 with a JSON body** → the live API answered "not here" (for example an endpoint that is not deployed
   yet): the screen shows a friendly placeholder. No snapshot is used.
4. **Anything else** — network error, timeout, 5xx, or a non-JSON answer (a plain static server such as
   `http.server` returns an HTML 404 for `/v1/...`) — loads `data/snapshot/<slug>.json` instead. After a
   network error or non-JSON answer the app treats the API as unreachable and goes straight to the
   snapshot for the rest of the page load.
5. If a snapshot file is used, the yellow banner shows the earliest `snapshot_at` (else `generated_at`)
   among the files used. A missing snapshot file gives the same placeholder as a 404.

### Snapshot file names (the slug rule)

`slug = path` with **one leading `/` removed**, then **every run of characters outside `[A-Za-z0-9._-]`
replaced by a single `_`**; the file is `data/snapshot/<slug>.json`. In JavaScript (exported as
`window.FloodLead.snapshotSlug`, between the `BEGIN/END snapshotSlug` markers in `app.js`):

```js
path.replace(/^\//, '').replace(/[^A-Za-z0-9._-]+/g, '_')
```

Python equivalent for `floodlead export-demo`:

```python
re.sub(r"[^A-Za-z0-9._-]+", "_", re.sub(r"^/", "", path))
```

`tests/test_web.py` checks that the rule in `app.js` and this documented rule agree.

### Canonical paths the app requests

The snapshot must contain exactly these paths (same parameter order) to cover the demo path:

| Path | Snapshot file |
|---|---|
| `/v1/health` | `v1_health.json` |
| `/v1/stations?limit=2000` | `v1_stations_limit_2000.json` |
| `/v1/stations/usgs:12210700` | `v1_stations_usgs_12210700.json` |
| `/v1/stations/usgs:12211195` | `v1_stations_usgs_12211195.json` |
| `/v1/stations/usgs:12210700/observations?param=level&days=7` | `v1_stations_usgs_12210700_observations_param_level_days_7.json` |
| `/v1/official-forecasts/NRKW1` | `v1_official-forecasts_NRKW1.json` |
| `/v1/stations/usgs:12210700/forecast` | `v1_stations_usgs_12210700_forecast.json` |
| `/v1/replay/overflow` | `v1_replay_overflow.json` |
| `/v1/replay/overflow/<event_id>/series` (every event, at least `2021-11-14` and `2025-12-10`) | `v1_replay_overflow_2021-11-14_series.json`, … |
| `/v1/ledger/head` | `v1_ledger_head.json` |
| `/v1/gauges/fraser-valley` (home page, Fraser Valley gauges) | `v1_gauges_fraser-valley.json` |
| `/v1/track-record` (`#/track-record`) | `v1_track-record.json` |

If either of the last two files is missing, its card shows a placeholder ("… not available right now") and the
rest of the page works. `POST /v1/feedback` is never part of a snapshot. In the Fraser Valley list the data age of
a snapshot is shown relative to that file's `snapshot_at`, like every other age.

The station screen (`#/station/<id>`) also requests `/v1/stations/<id>`,
`/v1/stations/<id>/observations?param=level&days=7`, `/v1/stations/<id>/forecast` and, for stations with an
NWPS id and no `official` block in their forecast, `/v1/official-forecasts/<lid>`. Include the ones you want
to work offline; the others show placeholders in snapshot mode.

Each snapshot file is exactly the API's JSON response plus a top-level `snapshot_at` (ISO 8601 UTC) and
keeps the `attribution` array.

## Units and labels

- North Cedarville and other US gauges: feet (as published) and metres. BC gauges: metres. The API serves SI;
  the app converts with 1 ft = 0.3048 m and uses `raw_value` (ft) for USGS observations where present.
- NOAA NWS forecasts are shown in feet, unmodified, labelled **NOAA NWS official forecast (unmodified)**
  (blue, dashed with markers).
- FloodLead forecasts (metres in the API) are labelled **FloodLead baseline (persistence / trend), live skill
  being measured** (muted grey-green, median plus 10–90 % band), never styled like NOAA's.
- Model names: **Persistence + typical drift (persistence-v1)** (the current level plus the station's
  typical past change over the same lead time, from its own history) and **Trend over 3 h, held after 6 h
  (trend3h-v1)** (the last 3 h trend, applied for at most 6 h).
- Times: Pacific (America/Vancouver) and UTC. Every reading shows its data time and age; real-time data
  is labelled provisional. Data from a snapshot file shows its age relative to that file's `snapshot_at`
  ("53 min before the snapshot"), not the viewer's clock.
- Locale: all number and date formatting uses explicit locales; `locale-guard.js` (loaded before uPlot)
  replaces an invalid `navigator.language` such as `en-US@posix`, which would otherwise make uPlot throw
  at load.

## Personal level

Typed on the overflow-watch screen, stored only in the browser's `localStorage`
(`floodlead.personalLevelFt.v1`) and never sent to the server. The chance of reaching it within each horizon
is P(max level over the window ≥ level), linearly interpolated through the seven `qmax` quantiles
(0.05 … 0.95) of each model; below the 0.05 quantile it shows "≥ 95 %", above the 0.95 quantile "< 5 %".

## Tests

```sh
uv run pytest -q tests/test_web.py   # static checks: CSP-safe HTML, same-origin assets, licence, slug rule, snapshot files
```
