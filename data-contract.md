# Data contract — FloodLead BC

Every material external input has known provenance and documented usage rights, as required by the Build Trilemma [Frame](https://build.trilemma.foundation/docs/playbook/frame) and [Data Licensing](https://build.trilemma.foundation/docs/playbook/frame/data-licensing) guides. This is a builder's record, not legal advice.

## Inputs at a glance

| # | Source | Role | Freshness | Licence | Light |
|---|---|---|---|---|---|
| 1 | ECCC real-time hydrometric | Core feature + ground truth | ~5-min observations, pushed by AMQP | OGL – Canada | 🟢 |
| 2 | ECCC historical daily hydrometric | Training history | Daily, decades | OGL – Canada | 🟢 |
| 3 | ECCC MSC HRDPS precipitation | Model feature | 4 runs/day | ECCC Data Servers End-use Licence | 🟢 |
| 4 | BC River Forecast Centre advisories, CLEVER/COFFEE | Scoring baseline only | Irregular | Province of BC website terms (pending) | 🟡 |
| 5 | Google Flood Hub | Scoring baseline only | Daily | Google terms (pending) | 🟡 |

Yellow sources are never core dependencies. If their terms do not allow the intended use, we only link to them and compare against what any member of the public can see.

## Usage-rights records

```yaml
- source: ECCC Real-time Hydrometric Data
  url: https://open.canada.ca/data/dataset/65d3a88b-eb09-4fd9-ac44-cf42dc1f7444
  license: OGL-Canada-2.0
  license_url: https://open.canada.ca/en/open-government-licence-canada
  access_method: AMQP (dd.weather.gc.ca, topic hydrometric.csv.#), HTTPS CSV, OGC API (api.weather.gc.ca)
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
```

## Freshness and lineage

```text
ECCC AMQP message ──► raw CSV (immutable, Parquet, hashed) ──► observation table
                                                              │
HYDAT daily ──────────────────────────────────────────────────┤
HRDPS GRIB2 ──► basin-mean precip ────────────────────────────┤
                                                              ▼
                                                   features ──► forecast (model_version)
                                                              ──► ledger (sha256 chain)
                                                              ──► score (vs observed)
```

- Every forecast row stores `model_version`, `feature_snapshot_hash` and the latest observation timestamp it used.
- Observations are stored as first received and as revised; scoring uses the value available at the time of the forecast for features, and the final value for ground truth.

## Freshness SLOs

| Feed | Expected | Alert if |
|---|---|---|
| Real-time hydrometric (watched gauges) | New reading every 5–15 min | No reading for 30 min → "data gap" notice to subscribed users |
| HRDPS | New run every 6 h | No new run for 9 h → model falls back to gauge-only features |
| RFC advisory snapshot | Every 15 min | Fetch failure for 2 h → baseline marked missing, not zero |

## Privacy tiers

| Tier | Data | Handling |
|---|---|---|
| Public | Gauge data, forecasts, ledger, scores | Published openly |
| Personal | User phone, gauge choice, thresholds | Encrypted at rest, Canadian region, deleted on request |
| Third-party personal | Contacts' phone numbers | Stored only after the contact opts in by SMS; never shared or sold |

No personal data ever enters the public ledger.

## Attribution

Contains information licensed under the Open Government Licence – Canada. Contains data from Environment and Climate Change Canada.
