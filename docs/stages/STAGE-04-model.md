# Stage 04 — The Nooksack model, tested once on floods it never saw

> Living document. Written while the stage is built, committed with the code. Newest work-log entries at the bottom.

| | |
|---|---|
| Branch | `stage-04-model` |
| Started | 2026-10-09 19:36 PT (2026-10-10 02:36 UTC) |
| Finished | (fill at end) |
| Prompt | `docs/build/prompts/STAGE-04-model.md`; the contract is `docs/evaluation-protocol.md`, the frozen text plus amendments 1–3 (4 added in this stage) |
| Status | in progress |

## Goal

Build the hourly Nooksack model the frozen protocol describes:
- North Cedarville level quantiles at 1–48 h;
- P(≥ 148 ft) and P(≥ 150 ft) within 12/24/48 h, read from the window maximum's distribution;
- P(overflow onset at SR 544) within 6/12/24 h, and its time.

Choose everything by walk-forward on development years only. Fix the final models publicly in the ledger before any held-out row is scored. Then run the held-out test once (WY2022, WY2026, the live period) against pure persistence, the 3 h trend, the gauge-watch rule, NWS as issued and the relay tiers, and report it whatever it shows.

The relay (trust table) and the official scorecard already stand on their own; the model has to earn its place on top of them. **A model that loses is a legitimate, publishable result.**

## Inputs read

- **`docs/build/prompts/STAGE-04-model.md`:**
  - fixes F1–F5 (F6 optional);
  - amendment 4 before any fit;
  - development, a checkpoint with a ledger card, the final run after the supervisor's go, R1;
  - VM safety: training containers capped at `--cpus 1.0 --memory 3g`;
  - targets: checkpoint by 15:00Z, PR by 21:00Z.
- **The supervisor's QA finding:** the "low bias for big floods" comes from sorting warnings by outcome. Sorted by forecast, the observed crest = 15.2 + 0.89 × the first forecast (slope 95 % CI 0.35–1.44); the typical miss is 1.19 ft; when the first forecast was ≥ 148 ft, 8 of 10 came in lower. **The honest gap is the missing range, not a bias.** F3 and F4 carry this into the scorecard and the README.
- **`docs/evaluation-protocol.md`:** frozen at `45367d1` (`ecdefe0b…abad`); amendments 1–3, now `c78bed9f…ec7c`. Its main points:
  - development years WY2005–2025 except 2022;
  - the A2 final-run folds;
  - T1–T6;
  - §2.1: 0 development events at ≥ 150 ft, 5 at ≥ 148 ft, 3 overflows;
  - relay v2 is in-sample;
  - R0–R3.
- **`src/floodlead/train_data.py`** (`development_rows`, `walk_forward_folds`, `final_run_folds`), `docs/data/features-nooksack-v1.md`, `trust-v2.json` and `catalogue-v1.json`.
- **`evaluation.md`:** 19 quantiles for new models; the kill criteria (BSS ≥ 0.10 at 12 h; ECE ≤ 0.05; FAR not worse than the advisory).
- **`docs/build/PLAN.md`:**
  - go/no-go: GO, a tiered relay that states its odds; the model is a candidate upgrade to Prepare;
  - cut order: precipitation forecasts are cut first.
- **What to expect, written down now:**
  - the forks lead North Cedarville by only ~4–5 h, so beyond ~6 h skill has to come from rain;
  - as-issued forecast rain exists only from 2024-01-19, so the honest model has no forecast rain in most training years, and NWS (which uses forecast rain) is likely hard to beat at 12–48 h;
  - the held-out years hold the two largest floods on record at North Cedarville, so the final run tests extrapolation.

## Plan

1. Stage doc, then a draft PR.
2. F1–F5, then F6 if time allows:
   - F1: SR 544 re-fetch, Nov 13–15, 2015, with before and after counts; the trust table re-checked;
   - F2: the "after the crest" timing shown as "—";
   - F3: the forecast-conditioned scorecard view (regression, ≥ 148 ft outcomes, the long-lead sentence), reproducing the supervisor's numbers;
   - F4: README wording;
   - F5: `final_training_rows()` with tests.
3. **Amendment 4** (dated, own commit, sha256 here), before any fit:
   - NWS columns are comparators, not inputs;
   - Δ-level and window-maximum targets;
   - 19 quantiles;
   - crossing probabilities from M_H's CDF;
   - the overflow model from P(M_H ≥ L);
   - the families compared, the ablation groups, the re-run rule.
4. **Development:** walk-forward folds only, every fit logging its training years, with ablations, fit times and peak memory. Train in capped one-off containers, and check `/v1/track-record` for gaps after each long job.
5. **Development report:** `docs/data/stage4-development-v1.json`, labelled "development, used to choose the model; not the result".
6. **Checkpoint:**
   - final models per A2 via `final_training_rows()`;
   - `stage4-final-manifest-v1.json`;
   - a ledger `model_card` with the manifest sha256;
   - the 10-line status.
   - **STOP.** While waiting: R1, F6, the doc.
7. **After the go:** one final-run command, one run ID → `stage4-results-v1.json`; the §11 table; T1–T6 met or not met; every held-out event; the kill-criteria decision.
8. README results section, the STAGE REPORT, and PR ready by 21:00Z.

## Decisions

## Work log

- `19:36` — `git checkout main && git pull` → `8c04afb`; branch `stage-04-model`. The Stage 3 part-2 worktree was removed (its branch is merged). Read the prompt and the inputs above.

## Measurements

| What | Value | How measured | When |
|---|---|---|---|

## Acceptance criteria

| AC | Result | Evidence |
|---|---|---|

## Contract files changed

| File | What changed | Why |
|---|---|---|

## Open issues and handoff to next stage

- (filled at the end)
