# Stage 3: supervisor review of the frozen evaluation protocol (Oct 10, ~01:55 UTC)

**Reviewed:** `docs/evaluation-protocol.md` at `45367d1` on `stage-03-history`.
- The supervisor recomputed its sha256: `ecdefe0bcdb27ff00508c58da9d2819b13ad14b2c9e2febfe86a2741e230abad`.
- The file is unchanged at `fa5204e`.

**Verdict: sound. Eight amendments are required before any model is trained.**

## What is right

- It was frozen before any model was trained, with the dataset, catalogue and relay hashes pinned.
- It scores relay, automated observation and model skill separately. The model gets credit only for improving on the first two.
- It says plainly that North Cedarville never reached 150 ft in the development years. So P(≥ 150 ft) cannot be learned or calibrated before the final run, and it is reported descriptively.
- Every target is reported as met or not met. Every event is listed. Every rate has an exact binomial interval.

The supervisor's independent checks agree with it on:
- the 2021 and 2025 Prepare leads before Abbotsford's first alert (12.7 h; 17.7–19.1 h);
- the 7 overflows since the SR 544 gauge began: 3 in development years, 4 held out;
- the moderate-stage events.

## Required amendments

Add each one as a dated amendment at the end of the file, in its own commit, and record the new sha256 in the stage doc. Never edit the frozen text above the Amendments heading.

**A1. Training never sees held-out or live rows.**

Two gaps:
- §2 says "train on WY2005…WY(k−1)". For k ≥ 2023 that includes the held-out WY2022.
- The datasets mark only WY2022 and WY2026 as holdout, so the rows from Oct 1–7, 2026 (WY2027, the live period) have `holdout = false`.

Fix them:
- Define the development years explicitly: WY2005–WY2025, except WY2022.
- Every training fold and every calibration fit uses development years only.
- WY2027 onward is held out as the live period.
- Do not rebuild the frozen files. Filter by water year in the Stage 4 loader, and add a test that the loader rejects rows from WY2022, WY2026 and WY ≥ 2027.
- Correct the last paragraph of the protocol: the live period belongs to WY2027, not WY2026.

**A2. How the final run is trained.** Fix it now, as if the system had been live:
- WY2022 is scored by a model trained on WY2005–WY2021.
- WY2026 is scored by a model trained on WY2005–WY2025, including WY2022. A live system would have had the 2021 flood by December 2025.
- The live period is scored by the WY2026 model.
- Features, hyperparameters, the calibration method and (p\*, k) are frozen from the walk-forward folds. Nothing is chosen on WY2022 or WY2026.

**A3. T5 is crossing-probability skill, not level skill.**
- Rename T5. Its bar, Brier skill ≥ 0.10 against persistence at 12 h (evaluation.md's kill criterion), is a Brier score.
- Add **T6, level skill**: fair CRPSS > 0 and median-MAE skill > 0 against pure persistence at 6, 12 and 24 h, overall and on rising limbs. evaluation.md makes this the headline test: "A model that does not beat it on both fair CRPS and median MAE has no skill to claim."

**A4. Relay v2 (addendum 3).** Add the addendum 3 tiers as a second relay comparator, counted by alert. Keep the frozen relay as v1, as built.
- Label relay v2 "descriptive and in-sample". On Oct 9 the supervisor chose its Prepare tier and its 5.0 ft Move-now level after seeing every year, including the held-out ones.
- The 4.0 ft variant (the NWS minor stage at SR 544) was not chosen from the data.
- Never present relay v2 numbers as held-out results.

**A5. The model's tiers stay as frozen in §5.**
- Addendum 3's "Prepare-M" is §5's prepare tier: North Cedarville ≥ 148 ft within 24 h.
- The model's move tier stays at overflow onset within 12 h.
- Add no new model target.

**A6. The AI-rainfall case study (addendum 2).**
- Add it as its own amendment.
- Rename addendum 2's T0–T3 to R0–R3, so they don't clash with targets T1–T6.
- Label it "one event, descriptive". It changes nothing in the product before Demo Day.

**A7. Two more validity limits.**
- The SR 544 gauge has reported continuously since Oct 1, 2026, at about 3.53 ft when no water is flowing. Live onset is the first reading ≥ 3.6 ft, which is a different definition from the historical "first record".
- Relay v2 is in-sample (A4).

**A8. Wording.**
- **T3, "no systematic low bias":** state that the 95% bootstrap interval of (mean forecast probability − observed frequency) must not lie entirely below 0.
- **T1:** the comparison with the City's alert exists for 2 events only, 2021 and 2025. Say so wherever T1 is reported.
