# Stage 3 — addendum 1 (supervisor, Oct 9 ~20:35 UTC)

Read [`docs/research/fraser-valley-flood-warning-status-quo.md`](../../research/fraser-valley-flood-warning-status-quo.md) first: a sourced review of what Sumas Prairie farmers actually have today. It changes what "value" means for FloodLead, and so what Stage 4 will be judged on.

**The finding, in one line:** the weak link is no longer the upstream river forecast. It is the last mile from the Everson overflow to the barn:
- no calibrated probabilities;
- first official crests about 2 ft low in both big floods;
- no arrival time at the border (the City's 7-hour rule was off in 2025);
- no night-time phone push across the three jurisdictions;
- no published accuracy record.

Most near-term value is relay plus automation. Model skill is unproven and must be measured against the official warnings that were actually issued.

Apply these. Where they conflict with the Stage 3 prompt, this addendum wins. Record each one as a decision.

## 1. Corrections (the prompt's spot check was wrong; the file is now fixed)

- **Nov 2021:** the first North Cedarville warning (NEW, "moderate") came at 11:50 AM PST Nov 14 (19:50Z), with a forecast crest of 148.9 ft. The river crossed minor stage at 21:30Z and crested at 150.76 ft.
- **Dec 2025:** the first warning came at 10:17 PM PST Dec 9 (06:17Z Dec 10), with a forecast crest of 148.4 ft. The river crossed minor stage at 20:15Z Dec 10 and crested at about 150.5 ft.
- **Both floods:** the upgrade to "major" came after the overflow had begun. Your parser must reproduce these numbers.

## 2. Part 1 (before Build Session 3): fix claims that are wrong today

- **README, The Cascade claim.** The README cites The Cascade for "a Sumas Way farm-market owner" who "had little time to prepare", and for "20+ hours of siren warnings". The article does not say Sumas Way. "Had little time to prepare" is a paraphrase ("barely had any time to prepare"). "The uncertainty of when and from where" is the reporter's summary, not a quote. The only documented siren is the City of Sumas, WA one. Correct or remove these.
- **README, BC forecasts.** Wherever the README says BC gives only basin labels, add that the BC River Forecast Centre also publishes deterministic station forecasts (COFFEE 5-day and CLEVER 10-day, in daily steps; COFFEE runs only during rain events) for Sumas at Huntingdon and Chilliwack at Vedder.
- **README, link the review.** Link the research document from the README and the help panel.
- **Help panel:** do not say that no forecasts exist for BC gauges. `brief.md` was corrected on `main` by the supervisor; do not edit it.

## 3. Part 2 additions (cheap, high value; do them before the training sets)

1. **Official-forecast scorecard.** No agency here publishes one, so it is FloodLead's first verifiable contribution.
   - **Inputs:** every archived NWS product (FLW, FLS, and any RVF or HYD that carries values) for `NRKW1` (and `NKSW1`, `NREW1`, `NOEW1`), from the start of the IEM archive.
   - **For each product, extract:** issuance time; category; forecast crest and its time; forecast flood begin and end.
   - **Score against the observed gauge record:**
     - crest error (bias, MAE) by lead time;
     - error in timing of the crest and of the minor, moderate and major crossings;
     - whether the category was right;
     - lead of the first warning before the minor crossing;
     - when the "major" upgrade came relative to the overflow onset.
   - **Publish:** `GET /v1/official-scorecard`, a page in the app ("How accurate were the official forecasts?"), and a table in the README. Give n and the period for every number.
2. **Relay and trigger replay (no model).** Pre-register (in item 4) a tiered rule set built only from archived products and gauge readings. For example:
   - **Heads-up:** an NWS flood watch for the Whatcom lowlands, or a BC River Forecast Centre watch naming the Nooksack;
   - **Prepare:** an NWS North Cedarville warning forecasting ≥ minor, or the Everson overflow warning;
   - **Move:** SR 544 ≥ 3.6 ft and rising, or North Cedarville ≥ minor and rising.

   Compute every tier's time for every event since the overflow gauge began, including minor-stage events with no overflow, which count as false alarms. Compare against:
   - Abbotsford's alert and order times for 2021 and 2025, from the review's sources, with their uncertainty ranges;
   - the 7-hour rule.

   Flag each trigger as daylight or night (Abbotsford sunrise and sunset). This is the "relay value" that the model must not take credit for.
3. **Arrival at the border.** Be honest about the data:
   - no agency published when the water crossed in either flood;
   - USGS Sumas River near Sumas (12214500) has no data for Nov 2021, and only a gradual rise in Dec 2025;
   - the Emerson Rd overflow gauge (12211190) record starts Jan 2024, and the gauge was offline on Oct 9, 2026.

   So any arrival estimate is a labelled range from analogues. Claim no accuracy unless at least 3 events have verifiable arrival times.
4. **The pre-registered protocol (item 7) adopts the review's bar** (its last table) as targets. Each is reported as met or not met, never tuned to pass:
   - **Prepare tier:** ≥ 24 h before water reaches the border and ≥ 6 h before the City's alert; false-alarm ratio ≤ 0.5.
   - **Move tier:** ≥ 12 h before water reaches the farm's zone; POD ≥ 0.8 and FAR ≤ 0.2.
   - **Crest probabilities** for North Cedarville ≥ 148 ft and ≥ 150 ft within 12, 24 and 48 h:
     - no systematic low bias;
     - reliable probabilities;
     - Brier skill > 0 against NWS-derived probabilities (1 when the official forecast crest is at or above the threshold, else 0), across **all** archived warnings, not just 2021 and 2025.
   - **Overflow onset timing at 1–12 h:** skill > 0 against persistence and trend at every lead, and a smaller timing error than the NWS issued forecasts.
   - **Ablations** that separate relay value from model value:
     - relay rules only;
     - gauges only;
     - plus observed rain;
     - plus as-issued forecast rain.
   - **Exact binomial confidence intervals** on every event-based rate. State that 5 of 5 still means a lower bound of about 0.48.
   - **Validity limits:** the 2026 SR 544 bridge and the Emerson Rd gauge outage.
5. **Do not archive BC River Forecast Centre products yet.** Their licence record is still yellow. Name them as a comparator for later.

## 4. What Stage 4 will be (so you shape the datasets for it)

The model-free relay rules ship first. The model's targets are:
- the calibrated probabilities that North Cedarville reaches 148 ft and 150 ft within 12, 24 and 48 h;
- the probability and timing of overflow onset at SR 544 within 6, 12 and 24 h, issued hourly.

Its comparators are:
- persistence;
- the 3 h trend;
- the relay rules;
- the NWS warnings as issued.

The training sets must support all of them, including NWS-derived probabilities at every issuance time where a product was in force.
