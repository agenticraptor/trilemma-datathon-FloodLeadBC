# Data contract — FloodLead BC

Every material external input has known provenance and documented usage rights, as required by the Build Trilemma [Frame](https://build.trilemma.foundation/docs/playbook/frame) and [Data Licensing](https://build.trilemma.foundation/docs/playbook/frame/data-licensing) guides. This is a builder's record, not legal advice.

## Inputs at a glance

| # | Source | Role | Freshness | Licence | Light |
|---|---|---|---|---|---|
| 1 | ECCC real-time hydrometric (Datamart hourly CSV) | Core feature + ground truth (BC gauges) | 5-min observations; all 429 BC files rewritten about every 30 min (observed 20:31 and 21:01 UTC, Oct 7); newest row 22–47 min old just after a rewrite, up to 107 min just before one; station-lag p50 ~49 min (measured Oct 7) | OGL – Canada | 🟢 |
| 2 | ECCC historical daily hydrometric | Training history | Daily, decades | OGL – Canada | 🟢 |
| 3 | ECCC MSC HRDPS precipitation | Model feature | 4 runs/day | ECCC Data Servers End-use Licence | 🟢 |
| 4 | BC River Forecast Centre advisories, CLEVER/COFFEE | Scoring baseline only | Irregular | Province of BC website terms (pending) | 🟡 |
| 5 | Google Flood Hub | Scoring baseline only | Daily | Google terms (pending) | 🟡 |
| 6 | USGS water data (Nooksack and Sumas gauges, Washington) | Core feature + ground truth (the river that floods Sumas Prairie) | 15-min; newest value 14–52 min old (measured Oct 7); instantaneous history since 2004–2007 at the main sites; keyless API limit 1,000 requests/hour per IP | US public domain | 🟢 |
| 7 | NOAA NWS National Water Prediction Service (official forecasts, flood stages) | Official baseline + official thresholds | NRKW1 and NKSW1 forecasts issued about daily (15:36 UTC on Oct 7), 6-hourly points to 7 days (NRKW1, 29 points) or 10 days (NKSW1, 40 points); observed series ~37 min behind | US public domain (NWS) | 🟢 |

Yellow sources are never core dependencies. If their terms do not allow the intended use, we only link to them and compare against what any member of the public can see.

## Usage-rights records

```yaml
- source: ECCC Real-time Hydrometric Data
  url: https://open.canada.ca/data/dataset/65d3a88b-eb09-4fd9-ac44-cf42dc1f7444
  license: OGL-Canada-2.0
  license_url: https://open.canada.ca/en/open-government-licence-canada
  access_method: HTTPS polling (every 10 min, conditional GETs) of Datamart hourly and 30-day CSVs (dd.weather.gc.ca/today/hydrometric/csv/BC/), OGC API (api.weather.gc.ca) for station metadata and daily history
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
  access_method: USGS Water Data OGC API v1 (api.waterdata.usgs.gov/ogcapi/v1; collections continuous, time-series-metadata, monitoring-locations); legacy waterservices.usgs.gov NWIS as fallback. Keyless limit 1,000 requests/hour per IP (an API key from api.waterdata.usgs.gov/signup raises it)
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
  access_method: NWPS REST API (gauges/{lid}, gauges/{lid}/stageflow)
  commercial_use: true
  redistribution: true
  attribution_required: true    # credit NOAA/NWS; required by our own honesty rules
  share_alike: false
  terms_reviewed: 2026-10-07
  notes: >-
    Public domain "unless specifically noted otherwise". Conditions: do not claim it as our own,
    do not imply NOAA/NWS endorsement or affiliation, do not modify it and present it as official,
    do not use NWS logos. We show official forecasts unmodified and clearly labelled, next to ours.
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
- Every forecast row (Stage 2+) stores `model_version`, `feature_snapshot_hash` and the latest observation timestamp it used.
- Observations are stored as first received and as revised; scoring uses the value available at the time of the forecast for features, and the final value for ground truth.

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
| Third-party personal | Contacts' phone numbers | Stored only after the contact opts in by SMS; never shared or sold |

No personal data ever enters the public ledger.

## Attribution

Contains information licensed under the Open Government Licence – Canada. Contains data from Environment and Climate Change Canada. Credit: U.S. Geological Survey. Official forecasts and flood categories: NOAA National Weather Service (not affiliated with or endorsed by NOAA/NWS).
