# Data contract — FloodLead BC

Every material external input has known provenance and documented usage rights, as required by the Build Trilemma [Frame](https://build.trilemma.foundation/docs/playbook/frame) and [Data Licensing](https://build.trilemma.foundation/docs/playbook/frame/data-licensing) guides. This is a builder's record, not legal advice.

## Inputs at a glance

| # | Source | Role | Freshness | Licence | Light |
|---|---|---|---|---|---|
| 1 | ECCC real-time hydrometric (Datamart hourly CSV) | Core feature + ground truth (BC gauges) | 5-min observations; all 429 BC files rewritten every 30 min (Last-Modified ~:01 and ~:31; observed 20:31–22:31 UTC, Oct 7) and visible on the server 2–6 min later; newest row 22–47 min old just after a rewrite, up to 107 min just before one; station-lag p50 ~49 min (measured Oct 7) | OGL – Canada | 🟢 |
| 2 | ECCC historical daily hydrometric | Training history | Daily, decades | OGL – Canada | 🟢 |
| 3 | ECCC MSC HRDPS precipitation | Model feature | 4 runs/day | ECCC Data Servers End-use Licence | 🟢 |
| 4 | BC River Forecast Centre advisories, CLEVER/COFFEE | Scoring baseline only | Irregular | Province of BC website terms (pending) | 🟡 |
| 5 | Google Flood Hub | Scoring baseline only | Daily | Google terms (pending) | 🟡 |
| 6 | USGS water data (Nooksack and Sumas gauges, Washington) | Core feature + ground truth (the river that floods Sumas Prairie) | 15-min; newest value 14–52 min old (measured Oct 7); instantaneous history since 2004–2007 at the main sites; keyless API limit 1,000 requests/hour per IP | US public domain | 🟢 |
| 7 | NOAA NWS National Water Prediction Service (official forecasts, flood stages) | Official baseline + official thresholds | NRKW1 and NKSW1 forecasts issued about daily (15:36 UTC on Oct 7), 6-hourly points to 7 days (NRKW1, 29 points) or 10 days (NKSW1, 40 points); observed series ~37 min behind | US public domain (NWS) | 🟢 |
| 8 | ECCC historical hourly climate (Fraser Valley stations) | Training feature (observed rainfall) | Hourly; latency to be measured | ECCC Data Servers End-use Licence (OGL-Canada on open.canada.ca) | 🟢 |
| 9 | NOAA NCEI Global Hourly (KBLI only) and USDA NRCS SNOTEL hourly (3 Nooksack sites) | Training feature (observed rainfall, snow) | Hourly; latency to be measured | US public domain | 🟢 |
| 10 | Open-Meteo reanalysis, historical forecasts and previous runs (basin points) | Training feature (basin rainfall; as-issued forecasts where they exist) | Hourly | CC BY 4.0, free API non-commercial only | 🟡 non-commercial |
| 11 | Archived NWS flood warnings and statements (IEM text archive) | Comparator: official hours of warning | As issued | Public domain | 🟢 |

Yellow sources are never core dependencies. If their terms do not allow the intended use, we only link to them and compare against what any member of the public can see.

## Usage-rights records

```yaml
- source: ECCC Real-time Hydrometric Data
  url: https://open.canada.ca/data/dataset/65d3a88b-eb09-4fd9-ac44-cf42dc1f7444
  license: OGL-Canada-2.0
  license_url: https://open.canada.ca/en/open-government-licence-canada
  access_method: HTTPS polling (every 5 min, conditional GETs) of Datamart hourly and 30-day CSVs (dd.weather.gc.ca/today/hydrometric/csv/BC/), OGC API (api.weather.gc.ca) for station metadata and daily history
  commercial_use: true
  redistribution: true
  attribution_required: true
  share_alike: false
  terms_reviewed: 2026-10-06
  notes: Provisional values can be revised. Datamart keeps ~30 days of real-time files; we archive from day one.

- source: ECCC Historical Hydrometric Data (HYDAT-derived daily means and extremes)
  url: https://eccc-msc.github.io/open-data/msc-data/obs_hydrometric/readme_hydrometric_en/
  license: OGL-Canada-2.0
  license_url: https://open.canada.ca/en/open-government-licence-canada
  access_method: OGC API collections; HYDAT bulk download
  commercial_use: true
  redistribution: true
  attribution_required: true
  share_alike: false
  terms_reviewed: 2026-10-06
  notes: Daily resolution only. Sub-daily history must be self-archived.

- source: ECCC MSC Datamart / GeoMet (HRDPS precipitation)
  url: https://eccc-msc.github.io/open-data/readme_en/
  license: ECCC Data Servers End-use Licence
  license_url: https://eccc-msc.github.io/open-data/licence/readme_en/
  access_method: HTTPS (GRIB2), AMQP notifications
  commercial_use: true
  redistribution: true
  attribution_required: true
  share_alike: false
  terms_reviewed: 2026-10-06
  notes: Subset to basin polygons; store only basin aggregates.

- source: BC River Forecast Centre warnings and model forecasts
  url: https://bcrfc.env.gov.bc.ca/warnings/
  license: Province of BC website terms (to confirm)
  access_method: HTTPS (HTML/PDF), polled no more than every 15 minutes
  commercial_use: unknown
  redistribution: false
  attribution_required: true
  share_alike: false
  terms_reviewed: pending
  notes: Baseline only. We store our own timestamped observation of advisory level for scoring; we do not republish their pages.

- source: Google Flood Hub
  url: https://sites.research.google/gr/floodforecasting/
  license: Google terms (to confirm)
  access_method: Public web / Flood Forecasting API if granted
  commercial_use: unknown
  redistribution: false
  attribution_required: true
  share_alike: false
  terms_reviewed: pending
  notes: Baseline only, at gauges it covers.

- source: USGS water data (instantaneous and daily values)
  url: https://api.waterdata.usgs.gov/ogcapi/v0/
  license: US Public Domain
  license_url: https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits
  access_method: USGS Water Data OGC API v1 (api.waterdata.usgs.gov/ogcapi/v1; collections continuous, time-series-metadata, monitoring-locations); legacy waterservices.usgs.gov NWIS IV as fallback (used for the 2004-10 → present history backfill and for live data while the OGC quota is exhausted). Keyless OGC limit 1,000 requests/hour per IP (an API key from api.waterdata.usgs.gov/signup raises it)
  commercial_use: true
  redistribution: true
  attribution_required: false   # credit requested: "U.S. Geological Survey"
  share_alike: false
  terms_reviewed: 2026-10-07
  notes: >-
    "USGS-authored or produced data and information are considered to be in the U.S. Public Domain."
    Recent values are provisional (qualifier P) and may be revised; store revisions.

- source: NOAA NWS National Water Prediction Service (NWPS) gauges, forecasts and flood categories
  url: https://api.water.noaa.gov/nwps/v1/
  license: US Public Domain (NWS)
  license_url: https://www.weather.gov/disclaimer
  access_method: NWPS REST API (gauges/{lid}; gauges/{lid}/stageflow/forecast for official forecasts, because gauges/{lid}/stageflow cuts some gauges' forecasts at request time + 7 days; gauges/{lid}/stageflow archived raw)
  commercial_use: true
  redistribution: true
  attribution_required: true    # credit NOAA/NWS; required by our own honesty rules
  share_alike: false
  terms_reviewed: 2026-10-07
  notes: >-
    Public domain "unless specifically noted otherwise". Conditions: do not claim it as our own,
    do not imply NOAA/NWS endorsement or affiliation, do not modify it and present it as official,
    do not use NWS logos. We show official forecasts unmodified and clearly labelled, next to ours.

# Stage 3 (Oct 9): rainfall and official-warning history. Approved by the human on Oct 9 ("approve all").
# Terms checked by the worker on 2026-10-09; the pages fetched are named in terms_checked_at.

- source: ECCC historical hourly climate observations (precipitation, temperature)
  url: https://api.weather.gc.ca/collections/climate-hourly
  license: ECCC Data Servers End-use Licence v2.1.1 (Aug 2026) on this access route; the same data are published under OGL-Canada on open.canada.ca
  license_url: https://eccc-msc.github.io/open-data/licence/readme_en/
  terms_checked_at: https://eccc-msc.github.io/open-data/licence/readme_en/ (fetched 2026-10-09, "Version 2.1.1 - August 2026")
  access_method: OGC API climate-hourly, one request per station-year (properties filtered), paced 1 request/s; stations in and near the Fraser Valley (Abbotsford A, Hope, Pitt Meadows, White Rock)
  commercial_use: true
  redistribution: true
  attribution_required: true
  share_alike: false
  terms_reviewed: 2026-10-09
  latency: to be measured in Stage 3 part 2
  notes: Raw responses archived unchanged. Hourly precipitation is missing for many hours at some stations; recorded as found.

- source: NOAA NCEI Global Hourly (Integrated Surface Database), US stations only
  url: https://www.ncei.noaa.gov/access/services/data/v1?dataset=global-hourly
  license: US Public Domain (NOAA) for US stations; non-US ISD data are under WMO Resolution 40 and are NOT used
  license_url: https://www.ncei.noaa.gov/pub/data/noaa/readme.txt
  terms_checked_at: https://www.ncei.noaa.gov/pub/data/noaa/readme.txt (fetched 2026-10-09; "The non-U.S. data in ISD are subject to WMO Resolution 40 restrictions, and cannot be redistributed")
  access_method: NCEI Access Data Service, one CSV per station-year, paced 1 request / 3 s; Bellingham Intl Airport (KBLI, 727976-24217) only
  commercial_use: true
  redistribution: true
  attribution_required: false   # credit "NOAA National Centers for Environmental Information"
  share_alike: false
  terms_reviewed: 2026-10-09
  notes: Canadian stations come from ECCC directly (record above), never from ISD.

- source: USDA NRCS SNOTEL hourly (precipitation accumulation, temperature, snow water equivalent, snow depth)
  url: https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data
  license: US Government work, public domain (17 U.S.C. 105)
  license_url: https://wcc.sc.egov.usda.gov/awdbRestApi/swagger-ui/index.html
  terms_checked_at: AWDB REST API reachable 2026-10-09; the NRCS policy pages tried (nrcs.usda.gov/policy-and-legal/policy, /policies-and-links) returned 404 that day, so the public-domain status rests on 17 U.S.C. 105, not on a page we could read
  access_method: AWDB REST API, hourly, one request per year for 3 Nooksack sites (Wells Creek 909, Elbow Lake 910, MF Nooksack 1011), paced 1 request / 2 s
  commercial_use: true
  redistribution: true
  attribution_required: false   # credit "USDA NRCS"
  share_alike: false
  terms_reviewed: 2026-10-09
  notes: Provisional data are revised; PREC is a season accumulation (inches), so hourly amounts are differences.

- source: Open-Meteo historical weather (reanalysis), historical forecast and previous-runs APIs
  url: https://open-meteo.com/en/docs/historical-weather-api
  license: CC BY 4.0 (data); free API for non-commercial use only
  license_url: https://open-meteo.com/en/licence
  terms_checked_at: https://open-meteo.com/en/terms and https://open-meteo.com/en/licence and https://open-meteo.com/en/pricing (fetched 2026-10-09)
  access_method: archive-api, historical-forecast-api and previous-runs-api, one request per basin point and year, paced 1 request / 30 s (≈ 52 calls/min, ≈ 3,100 calls/h, ≈ 7,100 calls in total, under the free limits of 600/min, 5,000/h and 10,000/day; a request longer than 2 weeks counts as several calls)
  commercial_use: false   # the free API is non-commercial; a commercial FloodLead needs a paid Open-Meteo plan or a swap to ECCC/NOAA model archives
  redistribution: true    # CC BY 4.0, with attribution
  attribution_required: true    # "Weather data by Open-Meteo.com" (CC BY 4.0); underlying models credited per the licence page
  share_alike: false
  terms_reviewed: 2026-10-09
  notes: >-
    The historical-forecast API is assembled from the first hours of each archived model run, so it is close to a
    short-lead forecast, not a 1-2 day forecast; the previous-runs API holds what was forecast 1 and 2 days before
    each hour. Which one is a fair "as-issued" input, and from what date each exists for our basins, is decided in
    Stage 3 part 2 (stage doc). Basin points are listed in src/floodlead/history/tasks.py.

- source: Archived NWS text products (flood warnings FLWSEW and flood statements FLSSEW) via the Iowa Environmental Mesonet
  url: https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py
  license: Public domain (NWS products are US public domain; IEM states "The materials found on this website are in the public domain and may be used freely by anyone for any lawful purpose")
  license_url: https://mesonet.agron.iastate.edu/disclaimer.php
  terms_checked_at: https://mesonet.agron.iastate.edu/disclaimer.php (fetched 2026-10-09)
  access_method: retrieve.py?pil=FLWSEW|FLSSEW&sdate&edate&fmt=text, one request per product and year since 2004, paced 1 request / 2 s
  commercial_use: true
  redistribution: true
  attribution_required: false   # "Attributing the Iowa Environmental Mesonet of Iowa State University would be appreciated" — we do
  share_alike: false
  terms_reviewed: 2026-10-09
  notes: The comparator for "hours of warning". The products are used as issued; parsed fields (P-VTEC, H-VTEC for NRKW1, NKSW1, NREW1, NOEW1) keep a link to the raw product.
```

## Freshness and lineage

```text
HTTPS poll (ECCC Datamart CSV / USGS OGC JSON / NWPS JSON)
   │
   ├──► raw payload: gzip, sha256, read-only, $ARCHIVE_DIR/raw/<source>/YYYY/MM/DD/HH/  (raw_objects index)
   │
   └──► parse ──► observations (TimescaleDB; SI + raw value; revisions appended to observation_revisions)
                  official_forecasts (NWPS, unmodified)
                                                              │
HYDAT daily (Stage 3) ────────────────────────────────────────┤
HRDPS GRIB2 ──► basin-mean precip (later stage) ───────────────┤
                                                              ▼
                                                   features ──► forecast (model_version)
                                                              ──► ledger (sha256 chain)
                                                              ──► score (vs observed)
```

- Every observation row keeps `raw_object_id` (the payload that set its value), `published_at`, `first_seen_at`, `last_seen_at` and `revision_count`; every change is appended to `observation_revisions`.
- Every forecast is a `forecast` ledger entry (Stage 2+). It stores:
  - its `model`, with the model's parameters in a `model_card` entry;
  - `data_as_of`, the newest observation it used;
  - `input_hash` and the hash of its error library;
  - only inputs with `ts ≤ created_at` and `first_seen_at ≤ created_at`.
  See [`docs/ledger-spec.md`](docs/ledger-spec.md). NOAA official forecasts enter the ledger exactly as received (`official_forecast` entries).
- Identical re-fetches write no observation rows (Stage 2, F2). `last_seen_at` is when the current value was last written. The per-station "last seen" for each payload kind is kept in `payload_coverage`.
- Observations are stored as first received and as revised; scoring uses the value available at the time of the forecast for features, and the final value for ground truth.

### Typical yearly peak (Stage 3)

`typical_peaks` (method `typical-peak-v1`) is derived from ECCC annual instantaneous peaks (record "ECCC Historical Hydrometric Data", archived pages in `history_downloads` source `eccc-peaks`) and checked against ECCC daily means (`eccc_daily`) and live levels. It is labelled everywhere as FloodLead-derived, not an official flood level, and kept apart from NOAA's official thresholds. The values used in forecasts are fixed in the model cards' `params.typical_peak` before first use.

## Freshness SLOs

Aligned with `/v1/health` (thresholds in `docs/stages/STAGE-01-live-archive.md`, D-01.14).

| Feed | Expected (measured Oct 7) | Amber if | Red if |
|---|---|---|---|
| ECCC real-time (Datamart) | files rewritten ~every 30 min; newest row 22–107 min old | newest row > 150 min, or last successful poll > 30 min, or < 80 % of stations reported in 3 h | newest row > 360 min or last successful poll > 90 min |
| USGS 15-min | newest value 14–52 min old | newest > 120 min or last successful poll > 45 min | newest > 360 min or last poll > 120 min |
| NWPS official forecasts | issued about daily | newest issuance > 36 h or last poll > 90 min | newest issuance > 72 h or last poll > 180 min |
| HRDPS (later stage) | new run every 6 h | no new run for 9 h → model falls back to gauge-only features | — |
| RFC advisory snapshot (later stage) | every 15 min | fetch failure for 2 h → baseline marked missing, not zero | — |

## Privacy tiers

| Tier | Data | Handling |
|---|---|---|
| Public | Gauge data, forecasts, ledger, scores | Published openly |
| Personal | User phone, gauge choice, thresholds | Encrypted at rest, Canadian region, deleted on request |
| Feedback (Stage 3) | Anonymous in-app feedback: page, station shown, yes/no, free text | No name, email, phone or IP stored; free text encrypted at rest (Fernet, key in `.env`), on the VM in Canada; never logged, echoed, published, put in the ledger, snapshots or fixtures; read only on the VM (`floodlead feedback list`); retention to be set with the Stage 7 privacy policy |
| Third-party personal | Contacts' phone numbers | Stored only after the contact opts in by SMS; never shared or sold |

No personal data ever enters the public ledger.

## Attribution

Contains information licensed under the Open Government Licence – Canada. Contains data from Environment and Climate Change Canada. Credit: U.S. Geological Survey. Official forecasts and flood categories: NOAA National Weather Service (not affiliated with or endorsed by NOAA/NWS).
