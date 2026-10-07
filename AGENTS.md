# AGENTS.md — FloodLead BC

Instructions for AI agents and collaborators working in this repository.

## Read first

1. `README.md` — what this is and why.
2. `product-brief.md` — users, pain, wedge, non-goals.
3. `data-contract.md` — inputs, licences, privacy. **Do not add a data source without a usage-rights record here.**
4. `architecture.md` — components, schema, API.
5. `evaluation.md` — metrics, thresholds, kill criteria.

## Hard rules

- **No unlicensed data.** Every new external input needs a YAML usage-rights record in `data-contract.md` before code depends on it. Yellow sources are baseline-only and must not become core dependencies.
- **No scraping** of sites whose terms do not clearly permit it.
- **No leakage.** Features may only use information available at the forecast's `issued_at`. Precipitation features use forecasts as issued.
- **Ledger is append-only.** Never edit or delete ledger rows. Model changes create a new `model_version`.
- **No performance claims** in docs or UI unless produced by `evaluation.md` experiments, with the run ID.
- **Messaging safety.** Never send to a contact without their recorded SMS opt-in. Never notify contacts before the user approves. Never contact emergency services.
- **Personal data** stays encrypted, in a Canadian region, and never enters the ledger, logs or test fixtures.
- **Not a warning service.** User-facing text must point to EmergencyInfoBC and local authority orders.

## Conventions

- Python 3.12, `ruff` + `pytest`; type hints required in `src/`.
- Small PRs; each updates any contract file whose facts changed (`product.yaml`, `architecture.md`, `data-contract.md`, `evaluation.md`).
- Tests live in `tests/`: unit, contract (schema of external feeds), replay (2021 window asserts alert time), calibration regression (fails if ECE > 0.05).

## Escalate to a human when

- A source's licence or terms are unclear or change.
- A model version underperforms persistence on the live ledger.
- Any messaging behaviour would reach someone who has not opted in.
