# Stage 00 — Environment discovery and readiness

> Living document. Written while the stage is built, committed with the code. Newest work-log entries at the bottom.

| | |
|---|---|
| Branch | `stage-00-environment` |
| Started | 2026-10-07 13:03 PT |
| Finished | (fill at end) |
| Prompt | `docs/build/prompts/STAGE-00-environment.md` |
| Status | in progress |

## Goal

Find out exactly what this VM is, what already runs on it, and whether it can do everything Stage 1 needs (Docker Compose stack of `db` + `api` + `caddy` on 80/443, hourly polling of ECCC Datamart, USGS and NOAA, a raw archive on local disk, pushes and PRs to GitHub). The supervisor adapts the Stage 1 prompt from this report, so the value here is accuracy: every claim below is backed by a command that was run on the VM and its real output. The stage is read-only apart from the small set of safe changes the prompt allows (install missing `git`/`curl`/`jq`/`gh`/`uv`, create `.env` and `/srv/floodlead/archive`, a self-expiring inbound probe on port 80, and this doc plus its PR). Nothing that already exists on the VM is stopped, changed or removed.

## Inputs read

- `CLAUDE.md` — stage protocol (branch, stage doc first, document while building, small commits, PR without merging, STAGE REPORT). Production-safety rules: never touch existing containers/volumes; secrets only in `.env`.
- `AGENTS.md` — hard rules (licensed data only, no leakage, append-only ledger, messaging safety, personal data in Canada).
- `docs/build/PLAN.md` — stage map; Stage 1 needs ECCC Datamart hourly CSVs (all BC), USGS Nooksack/Sumas, NOAA NWPS forecasts, raw archive on VM disk with daily snapshots as the off-machine copy.
- `docs/build/prompts/STAGE-00-environment.md` — this stage's prompt (8 discovery areas, allowed changes, report format).
- `docs/build/STAGE-00-human-setup.md` — superseded reference; it assumed an `e2-standard-4` Debian 12 VM in `northamerica-northeast2` with a 100 GB pd-balanced disk and a `floodlead-web` firewall tag. Surprising: the actual VM may not match any of these, which is what this stage checks.
- `data-contract.md`, `architecture.md`, `evaluation.md`, `product.yaml` — read for context. `architecture.md` still describes "Parquet on S3-compatible object storage" and "managed Postgres"; PLAN.md says archive goes to local disk instead of a bucket. Not changed in this stage (Stage 1 owns the archive design), noted under open issues.
- Surprise found at the very start: the local clone had **no commits** (only an untracked `Trilemma_Foundation_Datathon_Resources.md`); `git pull origin main` brought in 6 commits cleanly. The untracked file was left untouched. Also: `git` has no `user.name`/`user.email` configured on this VM; commits in this stage set the identity per command via environment variables rather than editing `~/.gitconfig`.

## Plan

1. Branch `stage-00-environment`, open this doc, commit and push it (done first, before any discovery).
2. Machine: hostname, OS, kernel, CPU, RAM, swap; GCE metadata (project, zone/region, machine type, tags, external IP, service account, scopes). Decide Canada yes/no.
3. Disk: `lsblk`, `df -hT`, disk type/size, largest directories, snapshot schedule (if `gcloud` is permitted).
4. What already runs: Docker objects, listening ports, running services, crontabs, load. Conclude free ports for `db`/`api`/`caddy`.
5. Time: `timedatectl`, skew vs `Date` headers from ECCC Datamart and NOAA.
6. Tools: versions of docker/compose/git/gh/uv/python/claude/gcloud; install only missing `git`/`curl`/`jq`/`gh`/`uv`. **Do not install Docker** — ask the human if absent.
7. Outbound: status + timing + newest-data age for every Stage 1 source; DNS for `<ip-with-dashes>.sslip.io`.
8. Inbound: if 80/443 are free, run a self-expiring (`timeout 3600`) `http.server` probe on port 80 with a random token; list firewall rules if permitted.
9. Repo: remote, branch, sync with `origin/main`, push/PR permission, `.env` key names and gitignore check. Create `.env` (missing keys only, `chmod 600`) and `/srv/floodlead/archive` if allowed.
10. Fill decisions, measurements and acceptance criteria; push; open PR `Stage 00: Environment` (do not merge); print the STAGE 0 REPORT in the terminal only (it contains the project ID and IP, which stay out of this public doc).

## Decisions

### D-00.1 — Git identity for commits without changing global config

- **Context:** `git config user.name` / `user.email` are unset on this VM, so `git commit` would fail. The prompt forbids changing existing files beyond the allowed list.
- **Options considered:** (a) write `user.name`/`user.email` into `~/.gitconfig`; (b) write them into the repo's `.git/config`; (c) pass them per commit via `GIT_AUTHOR_*`/`GIT_COMMITTER_*` environment variables.
- **Choice:** (c), using the same author identity as the existing commits on `main`.
- **Why:** leaves every existing file untouched and matches history authorship.
- **Reversibility / cost:** nothing to undo. Later stages may prefer (b) for convenience; that is a human call.
- **Follow-ups:** human may want to set a repo-local identity before Stage 1.

## Work log

- `13:03` — `git pull origin main` on the previously empty clone → fast-forward to `b7b263e` ("Stage 0 discovery prompt; archive to local disk instead of a bucket"). Read `CLAUDE.md`, `AGENTS.md`, `PLAN.md`, the Stage 0 prompt, template and contract files. `git checkout -b stage-00-environment`. Quick tool check: `which` finds `gh`, `git`, `curl`, `jq`, `gcloud` (snap), `claude`, `python3`, `openssl`; **`uv` and `docker` are not on PATH**; `systemctl status docker` → `Unit docker.service could not be found.` `gh auth status` → logged in to github.com (scopes include `repo`, `workflow`).

## Measurements

Every number this stage measured, with how it was measured.

| What | Value | How measured | When |
|---|---|---|---|

## Acceptance criteria

| AC | Result | Evidence |
|---|---|---|
| AC-1 | PASS / PARTIAL / FAIL | command → output |

## Contract files changed

| File | What changed | Why |
|---|---|---|

## Open issues and handoff to next stage

- (filled at end)
