# Stage 4: the supervisor's go for the single final run (Oct 11, ~00:45 UTC)

## Checkpoint review: GO, on the conditions below

**Verified independently:**
- **Commit order.** Amendment 4 (`216907f`, 02:44Z) precedes the first model code (`8bee4d4`, 02:52Z).
- **Protocol.** The frozen text and amendments 1–3 are unchanged prefixes of the current protocol (`fd6ecb6e…03ab`).
- **Manifest.** `stage4-final-manifest-v1.json` hashes to `1127595c…f39f4c` at `fca4df6` and at `61a4e58`. Its dataset hashes equal the frozen pins.
- **Ledger.** The model card `floodlead-nooksack-v1` is at seq 32517:
  - created 09:23:40Z;
  - its entry hash recomputes (`970c7099…b927`);
  - its parameters carry the manifest's sha256;
  - it is the exact head anchored at 09:30:01Z in `ledger/heads.txt` on GitHub, and it is present in `entries/2026/10/10/09.jsonl.gz`.
- **The whole ledger.** Recomputed from the API: 45,362 entries, 0 problems.
- **Development baseline.** Recomputed from the raw USGS record at the 60-min cut-off, pure persistence's MAE equals the development report: 0.0409 ft at 1 h and 0.1276 ft at 6 h (77,612 rows); 1.1347 ft against 1.1337 ft on rising limbs at 6 h (877 against 878 rows). The targets, latency and rows are aligned.
- **The final-run command.**
  - It refuses on any dataset or artifact hash mismatch, and refuses to overwrite its output.
  - It scores WY2022 with the WY2005–2021 artifacts, and WY2026 and the live period with the WY2005–2025 artifacts.
  - It reports §11, the per-event listing and the kill criteria.

**What the development results already say** (not the result). Write these down now, so the final report cannot drift:
- **Level skill (T6) is large:** CRPSS 0.77 / 0.63 / 0.45 at 6 / 12 / 24 h. Most of it comes from following recessions and the 4–5 h upstream lead.
- **The model's prepare rule** (p\* = 0.5, k = 2) found **1 of 3** development ≥ 148 ft events, with FAR 0.5. On the same three events, relay v2's NWS-based Prepare found all three.
- **The model's move rule** (0.5, 1) found 3 of 3 overflows, **3.4–6.9 h before onset**, with FAR 0.2. That is the model's most promising contribution.
- **BSS against NWS (0.57)** is against yes/no readings of the official crest. Any probabilistic forecast gains from that comparison.

## Amendment 5: reporting rules, committed and pushed before the run

Add this as a dated amendment, in its own commit, with its sha256 in the stage doc, **pushed to GitHub before the final run starts**. It changes no model, no (p\*, k), no target and no bar. It fixes only how the results are reported.

1. **Met / robust.**
   - "Met" means the point estimate meets the bar.
   - "Robust" means the 95% interval also clears it.
   - Every target is shown with both labels and its interval.
2. **The alert-rule trade-off.**
   - Report the held-out POD, FAR and leads for **every** (p\*, k) in the §5 grid, for both tiers, labelled "descriptive: the trade-off".
   - The pre-chosen rules are the result.
   - Show relay v2's Prepare and Move-now on the same held-out events, side by side.
3. **NWS comparisons.**
   - Every Brier skill score against NWS carries the words "NWS read as yes/no; any probabilistic forecast gains from this comparison".
   - **Add a descriptive crest comparison.** At each held-out issuance with a North Cedarville product in force, compare the model's median of M_48 and the NWS forecast crest, each against the observed maximum in (t, t + 48 h]. Report MAE and bias for both, with n, overall and per event.
4. **Per-event timelines** for every held-out overflow (Nov 14 and Nov 28, 2021; Dec 10, 2025; Mar 20, 2026) and every held-out ≥ 148 ft event. For each, give:
   - the model's first prepare and first move alerts;
   - the maximum P(≥ 148 ft within 24 h) and P(≥ 150 ft within 24 h) in the 48 h before the crest;
   - relay v2's tier times;
   - NWS's first warning and first "major";
   - the City's first alert and first order (2021 and 2025 only);
   - the onset and the crest.
5. **Reliability for rare events.** Show the bins with p ≥ 0.1 and their counts. State that ECE is dominated by near-zero rows.

## The run

1. Commit and push amendment 5.
2. Run `floodlead model final-run --supervisor-go "supervisor (Claude) via Pranay, Oct 11 2026 ~00:45 UTC"` with the same container caps.
3. Commit the results file **unedited**, immediately, in its own commit.
4. If a bug appears, stop and report it. A re-run needs a new amendment (amendment 4, item 9), and both results are published.

## Then, without waiting for the supervisor's review of the results

1. **Write-up.** Stage doc, the README section "Results (Stage 4)" with the run ID and the §11 table, "what this does and does not show", and the PR marked ready.
2. **Start Stage 5's plumbing in shadow mode, whatever the result.**
   - Hourly live feature rows from FloodLead's own archive, with the same code as `datasets.row`.
   - A live KBLI feed from the NWS METAR service. Write its usage-rights record first: NWS data are US public domain, and the owner's standing approval covers new data sources.
   - Hourly issuance of `floodlead-nooksack-v1` into the ledger (19 quantiles), labelled "shadow: not shown to users".
   - What the app and alerts may use waits for the kill-criteria decision and the supervisor's Stage 5 prompt.
3. **The VM's pending kernel upgrade.**
   - Check whether unattended upgrades may reboot automatically. If they can, turn automatic reboots off until Oct 14 and record it.
   - Do not reboot before Demo Day unless something requires it.
