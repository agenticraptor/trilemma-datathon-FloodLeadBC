# Stage 2 — addendum 2 (supervisor QA of part 1, Oct 8 ~21:40 UTC)

**PR #3: PASS, merged as `4efdd81`.**

The supervisor verified these independently:

- **Chain:** recomputed all 1,718 entries from `/v1/ledger` with its own stdlib script: hashes, seq continuity, prev links, exact canonical form, `created_at − base_time` ≤ 15 min, `valid_at − created_at` ≥ 45 min, and monotone quantiles, `qmax` and `p_exceed`.
- **GitHub copy:** rebuilt the chain from the two published files on the `ledger` branch alone. Both anchors (seq 856 and 1718) match the API exactly.
- **Golden vector:** reproduced with `sha256sum`.
- **Forecast inputs:** for 7 forecasts (ECCC and USGS), `input_hash` and the level at `data_as_of` were reproduced from the public observations API.
- **NOAA:** its current NRKW1 issuance equals the ledger point for point (29 of 29).
- **Replay:** every figure was re-derived, including the March 2026 event.
- **Browser:** the app loaded in headless Chromium at 1280 and 375 px with the en-CA locale. 0 console errors, same-origin requests only, strict CSP. Snapshot mode works with its banner.
- **Checks:** `ruff` is clean. `pytest` gave 76 passed on PR #3 and 92 on `stage-02-part2`, with the DB tests run, not skipped.

Fix these in part 2 (PR 2), in this order. Record each one as a decision or a work-log entry.

1. **Suggested personal level.** The suggested 146.2 ft comes from March 2026, where the overflow's first record (2026-03-21 01:30Z) came on the falling limb, about 3 h after North Cedarville peaked at 146.6 ft (22:15Z). The level at onset is not a trigger level.
   - Replace the suggestion with the official minor flood stage (146.5 ft), plus the rule the data supports: "7 of 13 minor-stage events since Nov 2015 were followed by water on the overflow path, a median 4.9 h later (0.1–6.4 h)."
   - Show North Cedarville peaks for events with and without an overflow. They overlap (overflow 146.6–150.8 ft, no overflow 146.7–147.3 ft), so say plainly that no single level separates them.
   - Update the README and the API's `suggested_*` fields to match.
2. **Phone layout.** At 375 px the overflow-watch page scrolls sideways, because the uPlot live legend (`table.u-legend.u-inline.u-live`) is 451 px wide. No page may scroll horizontally at 375 px. Add the check `document.documentElement.scrollWidth <= 375` to `scripts/screenshots.cjs` and report it.
3. **Clipped tables.** On desktop, the chances tables in the two half-width cards cut off the 36 h and 48 h columns. Show every column, or give the table a visible horizontal-scroll cue.
4. **Name persistence honestly.** `persistence-v1`'s median is the level plus the median historical error (08MH001: 1.515 m at `data_as_of` → q50 1.5135 m at 1 h), so it is not "the level stays the same".
   - Keep the model, and say this in its model card text (append a new card; the parameters are unchanged), in `evaluation.md` and in the app.
   - Also score pure persistence as `persistence-naive`: `level_at_data_as_of_m` as a point forecast at every horizon, so its CRPS equals the absolute error. The scorer computes it from the existing forecast entries, where the value is already fixed, so no new ledger entries are needed.
   - The summary shows CRPSS against both. `evaluation.md` baseline 1 and the Demo Day headline mean the naive one.
5. **Verifier gap.** `ledger.verify_rows` called with `start_seq=1` never checks that seq 1 is a genesis entry with a zero prev_hash, because that check runs only when `start_seq is None`. Every verifier (DB, `scripts/verify_ledger.py --api`, `--source github`) must require it. Add a test.
6. **Say exactly what `created_at` means.** It is the run's data cut-off and the start of computation; entries are inserted about 70 s later and anchored at HH:30. Write this into `docs/ledger-spec.md`. Add the commit time to each new `issuance` entry (for example `committed_at`, read from the database clock just before the insert), so the gap is measured, not assumed.
7. **Deploy only code that is in an open PR.** Production ran part-2 code, with migrations 003 and 004 applied, before PR 2 existed. Open PR 2 now as a draft so the code that is running is visible. From Stage 3 on, deploy only from a branch with an open PR.
8. **Small fixes.**
   - In snapshot mode, show data ages relative to the snapshot time. It now says "135 min ago" counted from the viewer's clock.
   - A browser whose default locale is POSIX throws "Invalid language tag: en-US@posix", probably from uPlot's default date formatting. Pass explicit formatting so that it cannot throw.
9. **First live rollover.** Tonight's 00:00 UTC rollover is the first live test of F1. Record the ECCC runs from 23:55 to 00:20Z in the stage doc: the directory used, the fallbacks tried and the status.

The rest of part 2 is unchanged from addendum 1. After PR 2 is open and its report is printed, run the reboot test (addendum 1, item 5).
