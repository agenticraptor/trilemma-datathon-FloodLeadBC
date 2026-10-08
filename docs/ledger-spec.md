# FloodLead ledger specification (`floodlead-ledger-v1`)

FloodLead publishes every forecast it makes **before the truth is known**, in an append-only, SHA-256 hash-chained ledger. This document is the public specification. Anyone can re-implement the verifier in another language from it, using any SHA-256 implementation and the public API (`https://<host>/v1/ledger`).

**What it guarantees:** the ledger is *tamper-evident*, not tamper-proof.
- Changing, inserting, deleting or reordering any entry changes every later hash.
- Each published chain head (an *anchor*, see §7) commits to the whole history up to it.
- A database superuser could still disable the database's own guards, so the external anchors are what make such a rewrite visible to outsiders.

## 1. Entries

The ledger is one global sequence. Each entry has:

| Field | Meaning |
|---|---|
| `seq` | Position in the chain: 1 for genesis, then +1 per entry, no gaps |
| `entry_type` | `genesis`, `model_card`, `issuance`, `forecast`, `official_forecast` or `gap` |
| `created_at` | Creation time (for forecasts: the issue time and the input cutoff) |
| `canonical` | The exact UTF-8 JSON text that was hashed |
| `prev_hash` | `entry_hash` of entry `seq − 1`; for genesis, 64 zeros |
| `entry_hash` | `hex(sha256(prev_hash + "\n" + canonical))` |

The canonical text is a JSON object with exactly four keys: `seq`, `entry_type`, `created_at` and `data`. The values of `seq` and `entry_type` inside `canonical` must equal the entry's own fields.

## 2. Canonicalisation

- JSON with keys sorted by Unicode code point at every level, separators `,` and `:` with no whitespace, UTF-8 (non-ASCII characters are written as-is, not `\u` escaped), no NaN or Infinity.
- **Numbers are rounded before serialisation:** levels (metres) and probabilities to 4 decimals (0.1 mm; 1e-4), so no exponent notation appears. `-0.0` is written as `0.0`; a missing value is `null`.
- **Timestamps** are RFC 3339 in UTC with `Z`: `created_at` with milliseconds (`2026-10-08T20:01:13.352Z`), all others to the second (`2026-10-08T20:00:00Z`).
- Python reference: `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`.

**Verifiers hash the stored `canonical` text byte for byte. They never parse and re-serialise numbers.**

## 3. Hash rule and golden vector

```
entry_hash = lowercase_hex( SHA-256( UTF-8( prev_hash_hex + "\n" + canonical ) ) )
genesis prev_hash = "0000000000000000000000000000000000000000000000000000000000000000"
```

Golden vector (also in `tests/test_ledger.py`; check with `printf '%s\n%s' "$prev" "$canonical" | sha256sum`):

| seq | canonical | entry_hash |
|---|---|---|
| 1 | `{"created_at":"2026-10-08T20:00:00.000Z","data":{"chain":"floodlead-ledger-v1","note":"golden vector","π":3.1416},"entry_type":"genesis","seq":1}` | `4f02a159d797b56810d422afce63f20d47455a086f83bf582263d35985e2fa4e` |
| 2 | `{"created_at":"2026-10-08T20:15:03.123Z","data":{"p":0.0001,"q":{"0.5":42.0685},"stale":false,"station_id":"usgs:12210700","x":null},"entry_type":"forecast","seq":2}` | `74873df1285247e90aa859d27b11ba17d66b2c76c03e129f3c7b0bc9b5cd4b1e` |

(Entry 2's `prev_hash` is entry 1's hash. These two entries are a test vector, not the production chain.)

## 4. Entry types (`data` fields)

- **`genesis`** (seq 1): `chain` = `floodlead-ledger-v1`, `hash_rule`, `canonical_rule`, `spec`, `repo`, `repo_commit` (the deployed git commit), `purpose`.
- **`model_card`**: `model` (e.g. `persistence-v1`), `method` (plain-language description), `params` (every output-affecting parameter), `params_hash` (sha256 of the canonical `params`), `code_commit`. A new card is appended whenever a model's parameters change. Any output-changing change also means a new model version name.
- **`forecast`** (one per station × model × base time):
  - **Issue context:** `station_id`, `model`, `base_time`; `data_as_of` (time of the newest level observation used); `input_age_min` = `created_at − data_as_of`; `stale_inputs` (true when the input age exceeds the source's green lag: 150 min ECCC, 120 min USGS); `level_at_data_as_of_m`; `units` = `m`; `trend_slope_m_per_h` (trend model only).
  - **Reproducibility:** `input_hash` and `inputs_n` (sha256 of the canonical list `[[ts, value], …]` of the observations in the 3 h ending at `data_as_of`); `error_library` = `{hash, paths, definition}`.
  - **Thresholds:** `thresholds` = `[{key, kind, level_m, label, …}]`, where `kind` is `official` (NWS categories, with `level_ft` and `source`) or `rise` (+0.25 / +0.5 / +1.0 m above the level at `data_as_of`).
  - **Horizons:** `horizons` = `[{h, valid_at, q, qmax, p_exceed}]`, for h ∈ {1, 3, 6, 12, 18, 24, 36, 48} with `valid_at = base_time + h`:
    - `q` gives the quantiles (keys `"0.05"`, `"0.1"`, `"0.25"`, `"0.5"`, `"0.75"`, `"0.9"`, `"0.95"`) of the level at `valid_at`;
    - `qmax` gives the same quantiles of the **maximum level over (data_as_of, valid_at]**;
    - `p_exceed[key]` = P(that maximum ≥ the threshold), computed from the sample paths.
- **`issuance`** (one per hourly run, after its forecasts): `base_time`, `models`, `horizons_h`, `stations_with_recent_level`, `forecasts` (count per model), `forecast_seq` ([first, last]), `skipped` (counts per reason), `runtime_s`, `peak_rss_mb`, `code_commit`.
- **`gap`**: `base_time`, `detected_at`, `reason`. Written for a base time with no issuance: either the run started more than 30 min late, or no run happened (written by the next run).
- **`official_forecast`** (Stage 2 part 2): a NOAA NWS issuance exactly as received (stage in ft, flow in kcfs, valid times, `generatedTime`, NOAA's `issuedTime`), with our `fetched_at` and the sha256 of the raw payload.

## 5. Issuance rules

- `base_time` = the top of each UTC hour. The run starts at HH:15. A run that starts more than 30 min after its base time issues nothing for it and records a `gap`. **Forecasts are never backdated and gaps are never filled.**
- Inputs: only observations with `ts ≤ created_at` **and** `first_seen_at ≤ created_at` (the value as known then).
- A horizon is dropped when `valid_at − created_at < 30 min`.
- Each hourly run is appended in one database transaction, under an advisory lock, so concurrent writers cannot fork the chain or leave gaps.

## 6. Database guards (defence in depth, not the trust anchor)

A `BEFORE INSERT` trigger rejects any entry unless all three hold:
- `seq` = last `seq` + 1 (genesis: `seq = 1` and a zero `prev_hash`);
- `prev_hash` = the last `entry_hash`;
- `entry_hash = sha256(prev_hash || '\n' || canonical)`.

Other triggers reject `UPDATE`, `DELETE` and `TRUNCATE` on the ledger tables. A superuser can disable triggers; that is why anchors exist.

## 7. Anchors and publication

Every hour, the anchor job writes two things to the **`ledger` branch** of `https://github.com/agenticraptor/trilemma-datathon-FloodLeadBC` through the GitHub contents API (it never touches `main` and never force-pushes):

- it appends `<anchored_at> <seq> <entry_hash>` to `ledger/heads.txt`;
- it writes that hour's new entries to `ledger/entries/YYYY/MM/DD/HH.jsonl.gz`, one JSON object per line with `seq`, `entry_type`, `created_at`, `canonical`, `prev_hash`, `entry_hash`.

Each anchor (seq, hash, time, commit SHA and URL) is also recorded in the database. **Status:** anchoring and publication ship in Stage 2 part 2. Until then `/v1/ledger/head` reports `anchor.status = "pending"`.

## 8. How to verify

1. Page through `GET /v1/ledger?after_seq=<n>&limit=1000` (entries in `seq` order) until `next_after_seq` is `null`.
2. For each entry, check that:
   - `seq` follows the previous one;
   - `prev_hash` equals the previous `entry_hash` (64 zeros for genesis);
   - `sha256(prev_hash + "\n" + canonical)` equals `entry_hash`;
   - the `seq` and `entry_type` inside `canonical` match.
3. Check every line of `ledger/heads.txt` on the `ledger` branch: the entry at that `seq` must have that `entry_hash`.
4. To start from an anchor, take its `seq` and `entry_hash` as the trusted starting point and verify forward.

Reference implementations:
- `floodlead ledger verify [--from-seq N]` checks directly against the database.
- `scripts/verify_ledger.py` uses the Python standard library only, and checks via the API or the published files (Stage 2 part 2).

Minimal Python:

```python
import hashlib, json, urllib.request
prev, seq, after = "0" * 64, 1, 0
while True:
    page = json.load(urllib.request.urlopen(f"https://<host>/v1/ledger?after_seq={after}&limit=1000"))
    for e in page["entries"]:
        assert e["seq"] == seq and e["prev_hash"] == prev
        assert hashlib.sha256((e["prev_hash"] + "\n" + e["canonical"]).encode()).hexdigest() == e["entry_hash"]
        prev, seq = e["entry_hash"], seq + 1
    if page["next_after_seq"] is None:
        break
    after = page["next_after_seq"]
print("OK", seq - 1, prev)
```
