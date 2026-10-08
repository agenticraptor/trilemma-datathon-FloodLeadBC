# FloodLead ledger branch

This branch holds only the public FloodLead forecast ledger, written hourly by the anchor job:

- `ledger/heads.txt`: one line per anchor, `<anchored_at> <seq> <entry_hash>`.
- `ledger/entries/YYYY/MM/DD/HH.jsonl.gz`: the entries added since the previous anchor, one JSON object per line
  (seq, entry_type, created_at, canonical, prev_hash, entry_hash) exactly as stored.

Verify with `python3 scripts/verify_ledger.py --source github` (on `main`) or by the rules in `docs/ledger-spec.md`.
This branch is append-only by convention: commits only add lines and files, never rewrite them.
