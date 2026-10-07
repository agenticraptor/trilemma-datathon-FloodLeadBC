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

### D-00.2 — Install `uv` without letting the installer edit shell profiles

- **Context:** `uv` was absent; the prompt allows installing it with the official installer. By default the installer appends PATH lines to `~/.bashrc`/`~/.profile`, which are existing files.
- **Options considered:** (a) default installer run; (b) `UV_NO_MODIFY_PATH=1` (binary only); (c) `pipx`/`pip` install (neither `pip3` nor `pipx` is present).
- **Choice:** (b). `~/.local/bin` is already on `PATH` (it holds `claude`), so nothing else is needed.
- **Why:** installs the tool without touching any existing file.
- **Reversibility / cost:** delete `~/.local/bin/uv` and `~/.local/bin/uvx` to undo.
- **Follow-ups:** none. `uv` sees the system CPython 3.12.3, so Stage 1 needs no Python download.

### D-00.3 — Docker is missing: stop and ask, do not install

- **Context:** `docker` is not installed (no binary, no `docker.service`; `apt-cache policy docker.io` → `Installed: (none)`, candidate `29.1.3-0ubuntu3~24.04.2`; `docker-ce` repo not configured). Stage 1 runs `db`, `api` and `caddy` under Docker Compose.
- **Options considered:** (a) install Docker now; (b) stop and ask the human.
- **Choice:** (b), as the prompt requires. The rest of discovery is read-only and continues.
- **Why:** the prompt says "Docker: if it is missing, stop and ask instead of installing". Installing Docker also adds iptables rules and a daemon to a VM that may host other work (there is a second login user on this VM), which is the human's call.
- **Reversibility / cost:** none yet. Stage 1 is blocked on Compose until the human approves an install route (Ubuntu `docker.io` + `docker-compose-v2` from the archive, or Docker's official `docker-ce` repo / `get.docker.com`, which `docs/build/STAGE-00-human-setup.md` used).
- **Follow-ups:** listed under "Needs human".

## Work log

- `13:03` — `git pull origin main` on the previously empty clone → fast-forward to `b7b263e` ("Stage 0 discovery prompt; archive to local disk instead of a bucket"). Read `CLAUDE.md`, `AGENTS.md`, `PLAN.md`, the Stage 0 prompt, template and contract files. `git checkout -b stage-00-environment`. Quick tool check: `which` finds `gh`, `git`, `curl`, `jq`, `gcloud` (snap), `claude`, `python3`, `openssl`; **`uv` and `docker` are not on PATH**; `systemctl status docker` → `Unit docker.service could not be found.` `gh auth status` → logged in to github.com (scopes include `repo`, `workflow`).
- `13:04` — Committed and pushed this doc (`b3e9e24`) before any discovery.
- `13:04` — **Machine.** `hostname` → `datathon`. `/etc/os-release` → `Ubuntu 24.04.5 LTS (Noble Numbat)`. `uname -r` → `7.0.0-1011-gcp` (x86_64). `nproc` → `2`; `lscpu` → `Intel(R) Xeon(R) CPU @ 2.20GHz`, 1 core × 2 threads. `free -h` → `Mem: 7.7Gi total, 922Mi used, 6.8Gi available`; `Swap: 0B` (no swap configured). GCE metadata server → machine type `e2-standard-2`, zone `northamerica-northeast2-a` (**Toronto, Canada: yes**), network tags `["http-server","https-server"]`, `scheduling/preemptible` → `FALSE`, image `ubuntu-2404-noble-amd64-v20260918`, default compute service account with `cloud-platform` scope. (Project ID, service-account email and IPs deliberately omitted here; they are in the terminal report only.) Note: the machine is **smaller** than the `e2-standard-4` (4 vCPU/16 GB) the superseded setup doc assumed.
- `13:05` — **Disk.** `lsblk` → `sda 100G` with `sda1 99G ext4 /`. `df -hT` → `/dev/root ext4 96G size, 4.5G used, 92G avail (5%)`. `gcloud compute disks describe` (permitted) → `type: pd-balanced`, `sizeGb: '100'`, created 2026-10-05, **no `resourcePolicies` → no snapshot schedule attached**. `gcloud compute snapshots list` → empty (no snapshots exist). `gcloud compute resource-policies list` → one schedule, `default-schedule-1`, but in `us-central1` (weekly, Sunday 20:00); snapshot schedules must be in the disk's region, so it cannot be attached to this disk as-is. `sudo du -xh --max-depth=2 /` (9.4 s) → `/` 4.5G total; largest: `/usr` 2.2G, `/usr/lib` 1.4G, `/var` 1.1G, `/home` 788M (all the worker user's home), `/var/lib` 758M, `/opt/google-cloud-ops-agent` 513M.
- `13:05` — **Network objects (gcloud, read-only).** `gcloud compute addresses list` → empty: **the external IP is ephemeral, not reserved**. If the VM is ever stopped and started it can change, which would break `<ip>.sslip.io` and its TLS certificate. Firewall rules on the `default` network: `default-allow-http` (tcp:80 from 0.0.0.0/0 → tag `http-server`) and `default-allow-https` (tcp:443 from 0.0.0.0/0 → tag `https-server`); this VM carries both tags, so **80 and 443 are open from the internet**. Also present: `default-allow-ssh` (22), `default-allow-rdp` (3389), `default-allow-icmp`, `default-allow-internal`, two `lb-health-check` rules, and a non-default rule `allow-bridge` (tcp:9777 from a single /32, no target tags, so it applies to every instance; nothing listens on 9777 on this VM). Not touched.
- `13:05` — **What already runs.** `docker` → `command not found` (also no `podman`, `containerd`, `runc`). `sudo ss -ltnp` → only `sshd` on 22, `systemd-resolved` on 127.0.0.53/54:53, Google Ops Agent `fluent-bit` on 20202 and `otelopscol` on 20201. **Ports 80, 443, 5432, 8000 are free.** `systemctl list-units --type=service --state=running` → only OS and Google guest/ops agents (chrony, cron, ssh, google-guest-agent, google-osconfig-agent, google-cloud-ops-agent-*, snapd, unattended-upgrades, …); no application services. `crontab -l` and `sudo crontab -l` → `no crontab for prana` / `no crontab for root`; `/var/spool/cron/crontabs` empty; `/etc/cron.d` holds only `e2scrub_all` and `sysstat`. Timers are all stock Ubuntu. Load: `uptime` → `up 1 day, 20:05, load average: 0.33, 0.29, 0.13`; `top` → 90.9% idle. Other accounts: `ubuntu` (uid 1000, home 20K) and a second login user (uid 1002, home 24K, no running processes). `/srv` is empty; `/opt` holds only the Google Ops Agent.
- `13:05` — **Time.** `timedatectl` → time zone `Etc/UTC`, `System clock synchronized: yes`, `NTP service: active`. `chronyc tracking` → source `metadata.google.internal`, stratum 3, `System time: 0.000004429 seconds fast of NTP time`. Skew vs HTTP `Date` headers (5 HEAD requests each, local time taken at request midpoint; `Date` has 1 s resolution, so each sample bounds the skew to a 1 s window and the windows are intersected): ECCC `dd.weather.gc.ca` → skew in **[−0.35, +0.11] s**; NOAA `api.water.noaa.gov` → skew in **[−0.42, +0.06] s**. Both are 0 s at the resolution available.
- `13:06` — **Tools.** `git version 2.43.0`, `gh version 2.102.0 (2026-09-30)`, `curl 8.5.0`, `jq-1.7`, `Python 3.12.3` (`/usr/bin/python3.12`), `claude` `2.1.293 (Claude Code)`, `Google Cloud SDK 585.0.0` (snap), `OpenSSL 3.0.13`. `pip3`, `pipx` and `ruff` are not installed. **`uv` was missing → installed** with the official installer (`UV_NO_MODIFY_PATH=1 sh install.sh`, see D-00.2) → `uv 0.12.23`; `uv python find 3.12` → `/usr/bin/python3.12` (3.12 available without download; `cpython-3.12.15` also downloadable). **Docker missing → not installed, see D-00.3.** `gcloud auth list` → the VM's default compute service account is the only credentialed account, with `cloud-platform` scope; it was permitted to describe disks, list snapshots, resource policies, firewall rules and addresses.

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
