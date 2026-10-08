# Stage 2 — addendum 1 (supervisor, Oct 8)

Apply these to Stage 2 now. Where they conflict with `STAGE-02-ledger-app.md`, this addendum wins. Record each one as a decision in your stage doc.

0. **Timeline reset: two PRs.** Stage 2 is starting at about 19:30 UTC on Oct 8, not the night before, and the Build Session 2 mentors review `main` at about **Oct 9 01:00 UTC** (18:00 PT). The deadlines in the prompt are replaced by this order:

   | Order | Deliverable | Target (UTC) |
   |---|---|---|
   | 1 | F1 (the rollover is at Oct 9 00:00) | first |
   | 2 | The app's overflow-watch view built on Stage 1 data (live level vs official stages, NOAA's forecast, data age), the 2021/2025 replay, snapshot mode, the README Build Session 2 section and F3 | ~21:30 |
   | 3 | The ledger core with `persistence-v1` and `trend3h-v1` issuing hourly, then the app's forecast panel (chances of crossing, personal level) and ledger panel | ~23:15 |
   | 4 | **PR 1** from `stage-02-ledger-app`, titled `Stage 02 (part 1): first app and forecast ledger`, with a STAGE REPORT covering what is done and listing what is not. The supervisor QAs and merges it before the mentors look | by ~23:30 |
   | 5 | Everything else: official forecasts in the ledger, scoring, the remaining API, anchors and ledger publication (addendum item 3), verifiers, F2, health additions, tests and docs. Use a new branch `stage-02-part2` from the merged `main`, keep updating the same stage doc, and open **PR 2** `Stage 02 (part 2): scoring, anchors and verification` | after PR 1 |

   If the ledger work (order 3) slips past ~23:15, open PR 1 without it. A working app on `main` when the mentors look matters more.

1. **New credentials in `.env`.** `USGS_API_KEY` and `LEDGER_GITHUB_TOKEN` are now set. Recreate the services that read them (`docker compose up -d ingest`, plus whatever runs the anchor job). Confirm without printing either value:
   - USGS responses now show the keyed rate limit (`x-ratelimit-limit` is no longer 1000), and
   - the anchor job writes to the `ledger` branch with the token.

   Use the token for anchors from now on, not manual pushes from your session.

2. **No disk snapshots.** The owner has declined them; this is an accepted risk. Remove every claim that daily snapshots are the off-machine copy (`architecture.md`, `README.md`, `data-contract.md`, and your Stage 2 docs). Leave the Stage 1 doc as written; you may add a dated note to it. State it plainly: there is no off-machine copy of the raw archive or the database.

3. **Publish the ledger itself, not just its head.** Nothing else leaves the VM, so the live track record must. Each hour, the anchor job also writes that hour's new ledger entries to the `ledger` branch as `ledger/entries/YYYY/MM/DD/HH.jsonl.gz`. Each line is one entry, exactly as stored: seq, entry_type, created_at, canonical, prev_hash and entry_hash.
   - Put the entries file and its `heads.txt` line in the same commit if you can.
   - Add `--source github` to `scripts/verify_ledger.py` so it can verify the chain from these files alone, without the VM.
   - Measure bytes per hour. If a month at that rate would add more than ~1 GB to the repository, say so in the report and propose an alternative; never drop the publication silently.

4. **`brief.md` is on `main`.** The supervisor drafted it at the owner's request, and it is labelled as AI-drafted. Link it from the README as "Brief (AI-drafted at the author's request)", never as the author's own words, and do not edit it.

5. **The reboot test moves to you.** This replaces "Do not reboot the VM" in the Stage 2 prompt. As the very last step of Stage 2, after PR 2 is open with the full STAGE REPORT in its body and the report is printed, run `sudo reboot` once and do nothing after it. The supervisor will check from outside that:
   - health returns to green,
   - hourly issuance continues, and
   - any base time missed during the reboot appears as a `gap` entry.
