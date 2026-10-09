# Stage 3 — addendum 2 (supervisor, Oct 9 ~21:40 UTC): satellites and AI rainfall

The owner asked whether satellite imagery with computer-vision or vision-language models could give FloodLead an edge in flood timing and accuracy. The sourced answer is [`docs/research/satellite-imagery-for-flood-prediction.md`](../../research/satellite-imagery-for-flood-prediction.md); read its summary and its test-plan table.

**Decision: no satellite imagery or vision models as forecast inputs.**
- **Timing:** free radar looks at Sumas Prairie about every 3 days, and scenes go public 2–6 h after sensing. In both floods, every satellite view came after the gauges had shown the overflow.
- **Cloud:** optical satellites are blind on flood days.
- **Evidence:** none shows satellite inputs improving 1–48 h timing in a gauged basin.
- **Models:** vision-language models answer about 40% of geospatial benchmark questions and do worse on radar.

The credible "AI edge" is AI **rainfall** forecasts. They can be tested before Demo Day only as a one-event case study, so that is what this addendum adds.

Apply these after addendum 1. All are $0 in cash. Each is a decision in the stage doc.

1. **T0: availability check (part 2, first; ~30 min).**
   - From the VM, query the Open-Meteo Previous Runs API for precipitation over Dec 7–12, 2025, at the upper-basin points you defined for rainfall, with the previous-day 1 and day 2 offsets.
   - Models: `ecmwf_aifs025_single`, `ecmwf_ifs025`, `gem_hrdps_continental`, `ncep_hrrr_conus`, `ncep_nbm_conus` (check the exact model names in the docs).
   - Record which models return values at fixed leads. If AIFS is absent, write "AI rainfall not testable before Demo Day" and skip items 3–4.
   - **Quota warning:** the supervisor's sandbox hit "Daily API request limit exceeded" on the free tier today. Long ranges and many variables count as several calls. Pace every Open-Meteo pull, cache responses on disk, and log the call counts. If the free tier blocks the history downloads, stop and report: a paid plan would need the human's approval.
2. **Protocol amendment (part 2, item 7, before T1 runs).** Add a dated section to the frozen `docs/evaluation-protocol.md` that fixes, before any data is pulled:
   - the sample points: the grid cells containing the approved upper-basin rain gauges and SNOTEL sites;
   - the windows: 24 h and 48 h ending at North Cedarville's minor-stage crossing on Dec 10, 2025;
   - the truth: hourly gauge totals, **never** IMERG;
   - the outputs: each model's forecast and observed totals at day-1 and day-2 leads, their ratio, and the timing error of the heaviest 6 h;
   - the reporting rules: every model is reported; the result is labelled "one event, descriptive"; AIFS is treated as 6-hourly information (Open-Meteo interpolates it); no product change before the demo, whatever the result.
3. **T1: run the case study (Stage 4, Oct 10–11, only if Stage 4 is on schedule; 4–6 h + 1 h QA).** Use the cut order in PLAN.md: precipitation forecasts are cut first if time runs short.
4. **T2: plug-in sensitivity (Stage 4, optional, declared in the same amendment; 2–3 h).** Swap each rain source into the Stage 4 model on the Dec 2025 holdout without retraining. Report every variant, labelled "sensitivity, not skill".
5. **T3: satellite timeline and flood-extent overlay (optional, after the core of part 2; 2–4 h).**
   - **Source:** Natural Resources Canada's Emergency Geomatics Service (EGS) flood polygons for 2021 and 2025. They are free under the Open Government Licence – Canada, at `data.eodms-sgdot.nrcan-rncan.gc.ca/public/EGS/{2021,2025}/Flood/CAN/BC/`. Approved under the owner's standing instruction of Oct 9 ("approve all", "don't await feedback"); the owner may veto. Add its usage-rights record first.
   - **Use:** show "where the water went" on the replay page, as a zone layer only. Never use it as a forecast input or a timing label.
   - **Demo slide:** a timeline of when satellites saw each flood against gauge onset, the City's alerts and water on farms. Take its numbers from the research document's first table and re-check them against the catalogues.
6. **Not to build or buy:**
   - satellite segmentation pipelines;
   - commercial radar or optical imagery (about $1,000–15,000 per event);
   - vision-language models reading imagery;
   - self-hosted AI weather models.

   Do not request Google WeatherNext access: approval takes 5–7 business days, after Demo Day.
7. **After Demo Day (record in the roadmap, do not build now):** a live shadow archive of AI and physics rainfall forecasts (AIFS, AIGFS/HGEFS, IFS, HRDPS, HRRR, NBM) logged as issued and scored storm by storm against basin gauges. Use AI rain as a model feature only after at least 30 scored wet days show lower 24 h and 48 h CRPS than HRDPS and NBM.
