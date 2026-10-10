# Stage 3 — addendum 3 (supervisor, Oct 9 ~22:10 UTC): frozen alert tiers and the trust numbers

Before committing to FloodLead, the owner asked two things:
- Does it give farmers extra time?
- Will its alerts be mostly right, rather than mostly false alarms?

The supervisor answered both from two sources:
- the full NWS warning archive: IEM AFOS `FLWSEW` and `FLSSEW`, whole years 2015–2026;
- the USGS SR 544 overflow gauge (12211195).

The answer is yes to both, provided alerts are tiered by the cost of the action and each alert states its own record. **Decision: GO.**

Apply this after addenda 1 and 2. It needs no new data sources and costs $0.

## 1. Freeze these tiers

They replace the examples in addendum 1, item 2. You froze the protocol at `45367d1` before this addendum reached you, so add the tiers to `docs/evaluation-protocol.md` as a dated amendment ("relay v2"; see [the protocol review](STAGE-03-protocol-review.md), A4), before any model is trained. Keep addendum 1's review bar (item 4) unchanged.

| Tier | Trigger | What the farmer does |
|---|---|---|
| Heads-up | NWS issues a new river flood warning for the Nooksack at North Cedarville (H-VTEC `NRKW1`, action `NEW`) | Nothing costly: check fuel, trailers and contacts; stay close |
| Prepare | The first North Cedarville product with H-VTEC severity ≥ 2 (a moderate or worse forecast) | Line up trucks and a receiving farm; move young stock and equipment |
| Move now | SR 544 overflow gauge (USGS 12211195) ≥ 5.0 ft | Move milking herds and poultry |

- **Move now is provisional.** The supervisor chose 5.0 ft after looking at the 2015–2026 record. It separates the four overflows in the years officials cite as reaching Canada (2020, 2021, 2025) from three small ones, which peaked at 4.06–4.91 ft.
  - Label it "chosen after seeing the data" everywhere.
  - Also report the 4.0 ft variant. That is the NWS minor stage for the gauge, and it was not chosen from the data.
- **Model variant (Stage 4).** "Prepare-M" is the protocol's model prepare tier (§5: North Cedarville ≥ 148 ft within 24 h, with (p\*, k) chosen on the validation years only). Report it beside the NWS-based Prepare. It replaces Prepare only if it wins under the protocol.
- **In-sample.** The supervisor chose the Prepare tier and the 5.0 ft level after seeing every year, including the held-out ones. Relay v2 numbers are descriptive and are never presented as held-out results.
- **Night.** Flag each trigger as day or night. Move now always pushes. Whether Prepare pushes at night is the farmer's choice (Stage 7).
- **Gauge missing.** If SR 544 is not reporting, the alert says so. Never infer a Move-now signal.

## 2. The trust table

This is a Stage 4 output for the track-record page, the README and the demo. Code computes it, with a run ID. Give one row per tier:
- alerts in the record, and alerts per year;
- how many were followed by any overflow, and how many by an overflow ≥ 5 ft;
- precision, with an exact 95% interval;
- overflows missed;
- lead before overflow onset, for each event and not just the median;
- for 2021 and 2025, the time against Abbotsford's first alert and first order.

List every alert with its outcome. Never show a rate without its list.

**The supervisor's independent count, for you to reproduce.** Do not adjust yours to match. If yours differs, report both and explain the difference.
- **Record:** 18 `NRKW1` warning events from Nov 14, 2015 to Oct 9, 2026 (10.9 years). 7 overflows at SR 544, 4 of them ≥ 5 ft.
- **Heads-up:** 18 alerts.
  - 7 were followed by an overflow: 39% (95% CI 17–64%).
  - 4 were followed by an overflow ≥ 5 ft: 22%.
- **Prepare:** 8 alerts.
  - 6 were followed by an overflow: 75% (95% CI 35–97%).
  - 4 were followed by an overflow ≥ 5 ft: 50% (95% CI 16–84%).
  - It flagged all 4 large overflows, 4.0, 6.6, 13.3 and 18.5 h before onset.
  - 2 alerts had no overflow at all: Dec 2015 and Nov 2018.
- **Move now:**
  - at 5.0 ft: 4 of 4 (95% CI 40–100%), reached 0.8–3.5 h after onset;
  - at 4.0 ft: 7 alerts, 4 of them large.

## 3. Test that the warning archive is complete (part 2)

The supervisor's first pass used partial-year downloads. It wrongly concluded that NWS had issued no warning before the Nov 28, 2021 overflow. NWS did: event 0088, at 1:29 AM PST on Nov 28, forecasting moderate flooding.
- Download whole years.
- Add a test that the archive holds that event and all 18 events above.

## 4. Alert wording

Every alert states its tier's record in plain words. Fill the numbers from the trust table; never hard-code them. For example:

> Prepare. NWS forecasts moderate flooding at North Cedarville. Since 2015 this has happened 8 times. The river overflowed at Everson 6 times. 4 of those overflows were as large as the ones in 2020, 2021 and 2025, when water reached Sumas Prairie.

## 5. What not to claim

The tiers' precision is the official warnings' precision. FloodLead adds:
- delivery to a farmer's phone;
- farm terms and tiers;
- the odds on every alert;
- a public record.

Say so on the track-record page. Do not claim a better forecast than NWS unless the protocol shows one.

## 6. Small fixes

- **SR 544 record start.** The replay gives it as 2015-11-14 09:15Z. The USGS file's first record is 00:15 PST (08:15Z). Check the backfill.
- **Re-checking the trigger.** The SR 544 gauge has reported continuously since Oct 1, 2026, and the 2026 bridge changes the hydraulics there. Re-check the 5.0 ft trigger after the first overflow of the 2026–27 season. Put this in the protocol and in the alert help text.

## 7. Your relay tiers in PR #6 (added ~22:30 UTC, after reading PR #6 at `6fe4edb`)

You already computed tiers from addendum 1's examples. Keep that work, with these changes:
- **Keep the old table, marked superseded.** In the stage doc, label it "superseded: addendum 1 examples, kept for the record". Do not delete it.
- **Count alerts, not minor-stage events.** Your table counts the 13 minor-stage events. A warning that never led to a minor crossing (for example Dec 8, 2015, or Oct 28, 2021) is therefore not counted as a false alarm, although to a farmer it is one. Count every warning event as one alert.
- **Keep the flood watch as a "Watch" row** in the trust table. Count every NWS flood watch naming Whatcom as one alert, scored the same way.
- **Report the Everson-overflow areal warnings (`FA.W`) as their own descriptive row.** In 2021 (twice) and 2025 they came after Prepare.
