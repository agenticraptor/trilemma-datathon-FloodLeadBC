# Stage 00 — Environment discovery and readiness

> Living document. Written while the stage is built, committed with the code. Newest work-log entries at the bottom.

| | |
|---|---|
| Branch | `stage-00-environment` |
| Started | 2026-10-07 13:03 PT |
| Finished | 2026-10-07 13:10 PT |
| Prompt | `docs/build/prompts/STAGE-00-environment.md` |
| Status | ready for QA |

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

### D-00.4 — Raw archive on the boot disk at `/srv/floodlead/archive`

- **Context:** PLAN.md moved the raw archive from a bucket to the VM disk. The prompt allows creating `/srv/floodlead/archive` if `/srv` exists and the path is free.
- **Options considered:** (a) `/srv/floodlead/archive` on the root filesystem; (b) a directory inside the repo clone (e.g. `data/`, gitignored); (c) a separate persistent disk mounted for the archive.
- **Choice:** (a). Created with `sudo install -d -m 755 -o prana -g prana /srv/floodlead /srv/floodlead/archive` (both new; `/srv` was empty). `ARCHIVE_DIR=/srv/floodlead/archive` written to `.env`.
- **Why:** the VM has a single 100 GB pd-balanced disk with 92 GB free, so (c) needs a new paid disk and a human decision. Keeping the archive outside the clone means a `git clean` or re-clone cannot delete it, and `/srv` is the FHS location for site data. It is bind-mountable into Compose services.
- **Reversibility / cost:** empty directories, trivial to move now. Disk cost: none beyond the existing boot disk.
- **Follow-ups:** the archive's only off-machine copy will be disk snapshots, and **no snapshot schedule is attached to the boot disk** (see open issues). Until one is, the archive has no off-machine copy.

### D-00.5 — Inbound probe not run (permission denied); firewall evidence used instead

- **Context:** ports 80 and 443 were free, so the prompt asks for a self-expiring `python3 -m http.server 80` probe as root.
- **What happened:** the command to start the probe was refused by the session's auto-mode permission check before anything ran (`/tmp/fl-probe` was never created). The worker did not retry it in another form.
- **Choice:** report the probe as not run and give the human the exact command. Use the firewall rules and instance tags (read with `gcloud`) as the evidence that 80/443 are open from the internet.
- **Why:** the honesty rules and the permission system both rule out a workaround. Firewall config shows that traffic is *allowed*, not that it *arrives*, so the inbound check is PARTIAL.
- **Reversibility / cost:** none. The human can run the probe in under a minute (command under open issues).
- **Follow-ups:** Stage 1's Caddy ACME HTTP-01 challenge is the next real proof of inbound reachability.

### D-00.6 — Did not edit `product.yaml` for the repository rename

- **Context:** `git push` printed "This repository moved. Please use the new location: …/trilemma-datathon-FloodLeadBC.git" and `gh repo view` confirms the new name. `product.yaml` (`repo:`) still has the old URL, and CLAUDE.md asks that contract facts be kept true.
- **Options considered:** (a) fix `product.yaml` and `git remote set-url` in this stage; (b) leave both and report.
- **Choice:** (b).
- **Why:** this stage's allowed changes are limited to this doc, `.env`, the archive directory, tool installs and the probe; everything else needs the human. GitHub redirects the old URL, so nothing is broken today.
- **Reversibility / cost:** a one-line change later.
- **Follow-ups:** under open issues for the supervisor to fold into Stage 1.

## Work log

- `13:03` — `git pull origin main` on the previously empty clone → fast-forward to `b7b263e` ("Stage 0 discovery prompt; archive to local disk instead of a bucket"). Read `CLAUDE.md`, `AGENTS.md`, `PLAN.md`, the Stage 0 prompt, template and contract files. `git checkout -b stage-00-environment`. Quick tool check: `which` finds `gh`, `git`, `curl`, `jq`, `gcloud` (snap), `claude`, `python3`, `openssl`; **`uv` and `docker` are not on PATH**; `systemctl status docker` → `Unit docker.service could not be found.` `gh auth status` → logged in to github.com (scopes include `repo`, `workflow`).
- `13:04` — Committed and pushed this doc (`b3e9e24`) before any discovery.
- `13:04` — **Machine.** `hostname` → `datathon`. `/etc/os-release` → `Ubuntu 24.04.5 LTS (Noble Numbat)`. `uname -r` → `7.0.0-1011-gcp` (x86_64). `nproc` → `2`; `lscpu` → `Intel(R) Xeon(R) CPU @ 2.20GHz`, 1 core × 2 threads. `free -h` → `Mem: 7.7Gi total, 922Mi used, 6.8Gi available`; `Swap: 0B` (no swap configured). GCE metadata server → machine type `e2-standard-2`, zone `northamerica-northeast2-a` (**Toronto, Canada: yes**), network tags `["http-server","https-server"]`, `scheduling/preemptible` → `FALSE`, image `ubuntu-2404-noble-amd64-v20260918`, default compute service account with `cloud-platform` scope. (Project ID, service-account email and IPs deliberately omitted here; they are in the terminal report only.) Note: the machine is **smaller** than the `e2-standard-4` (4 vCPU/16 GB) the superseded setup doc assumed.
- `13:05` — **Disk.** `lsblk` → `sda 100G` with `sda1 99G ext4 /`. `df -hT` → `/dev/root ext4 96G size, 4.5G used, 92G avail (5%)`. `gcloud compute disks describe` (permitted) → `type: pd-balanced`, `sizeGb: '100'`, created 2026-10-05, **no `resourcePolicies` → no snapshot schedule attached**. `gcloud compute snapshots list` → empty (no snapshots exist). `gcloud compute resource-policies list` → one schedule, `default-schedule-1`, but in `us-central1` (weekly, Sunday 20:00); snapshot schedules must be in the disk's region, so it cannot be attached to this disk as-is. `sudo du -xh --max-depth=2 /` (9.4 s) → `/` 4.5G total; largest: `/usr` 2.2G, `/usr/lib` 1.4G, `/var` 1.1G, `/home` 788M (all the worker user's home), `/var/lib` 758M, `/opt/google-cloud-ops-agent` 513M.
- `13:05` — **Network objects (gcloud, read-only).** `gcloud compute addresses list` → empty: **the external IP is ephemeral, not reserved**. If the VM is ever stopped and started it can change, which would break `<ip>.sslip.io` and its TLS certificate. Firewall rules on the `default` network: `default-allow-http` (tcp:80 from 0.0.0.0/0 → tag `http-server`) and `default-allow-https` (tcp:443 from 0.0.0.0/0 → tag `https-server`); this VM carries both tags, so **80 and 443 are open from the internet**. Also present: `default-allow-ssh` (22), `default-allow-rdp` (3389), `default-allow-icmp`, `default-allow-internal`, two `lb-health-check` rules, and a non-default rule `allow-bridge` (tcp:9777 from a single /32, no target tags, so it applies to every instance; nothing listens on 9777 on this VM). Not touched.
- `13:05` — **What already runs.** `docker` → `command not found` (also no `podman`, `containerd`, `runc`). `sudo ss -ltnp` → only `sshd` on 22, `systemd-resolved` on 127.0.0.53/54:53, Google Ops Agent `fluent-bit` on 20202 and `otelopscol` on 20201. **Ports 80, 443, 5432, 8000 are free.** `systemctl list-units --type=service --state=running` → only OS and Google guest/ops agents (chrony, cron, ssh, google-guest-agent, google-osconfig-agent, google-cloud-ops-agent-*, snapd, unattended-upgrades, …); no application services. `crontab -l` and `sudo crontab -l` → `no crontab for prana` / `no crontab for root`; `/var/spool/cron/crontabs` empty; `/etc/cron.d` holds only `e2scrub_all` and `sysstat`. Timers are all stock Ubuntu. Load: `uptime` → `up 1 day, 20:05, load average: 0.33, 0.29, 0.13`; `top` → 90.9% idle. Other accounts: `ubuntu` (uid 1000, home 20K) and a second login user (uid 1002, home 24K, no running processes). `/srv` is empty; `/opt` holds only the Google Ops Agent.
- `13:05` — **Time.** `timedatectl` → time zone `Etc/UTC`, `System clock synchronized: yes`, `NTP service: active`. `chronyc tracking` → source `metadata.google.internal`, stratum 3, `System time: 0.000004429 seconds fast of NTP time`. Skew vs HTTP `Date` headers (5 HEAD requests each, local time taken at request midpoint; `Date` has 1 s resolution, so each sample bounds the skew to a 1 s window and the windows are intersected): ECCC `dd.weather.gc.ca` → skew in **[−0.35, +0.11] s**; NOAA `api.water.noaa.gov` → skew in **[−0.42, +0.06] s**. Both are 0 s at the resolution available.
- `13:06` — **Tools.** `git version 2.43.0`, `gh version 2.102.0 (2026-09-30)`, `curl 8.5.0`, `jq-1.7`, `Python 3.12.3` (`/usr/bin/python3.12`), `claude` `2.1.293 (Claude Code)`, `Google Cloud SDK 585.0.0` (snap), `OpenSSL 3.0.13`. `pip3`, `pipx` and `ruff` are not installed. **`uv` was missing → installed** with the official installer (`UV_NO_MODIFY_PATH=1 sh install.sh`, see D-00.2) → `uv 0.12.23`; `uv python find 3.12` → `/usr/bin/python3.12` (3.12 available without download; `cpython-3.12.15` also downloadable). **Docker missing → not installed, see D-00.3.** `gcloud auth list` → the VM's default compute service account is the only credentialed account, with `cloud-platform` scope; it was permitted to describe disks, list snapshots, resource policies, firewall rules and addresses.
- `13:06` — Committed and pushed the log so far (`bbea560`). `git push` printed `remote: This repository moved. Please use the new location: https://github.com/agenticraptor/trilemma-datathon-FloodLeadBC.git` (push succeeded through the redirect). See D-00.6.
- `13:06` — **Outbound, ECCC Datamart.** `curl -s -o /dev/null -w '%{http_code} %{time_total}s' https://dd.weather.gc.ca/today/hydrometric/csv/BC/hourly/` → `200 0.135s` (63,785 B listing). `grep -oE 'BC_[A-Z0-9]+_hourly_hydrometric\.csv' | sort -u | wc -l` → **429 files**; 430 listing entries carry the same timestamp `2026-10-07 19:31` (UTC), which matches the supervisor's "all files rewritten at :31". `BC_08MH001_hourly_hydrometric.csv` → `200 0.072s`, 37,978 B, `Last-Modified: Wed, 07 Oct 2026 19:31:21 GMT`, 701 data rows; last row `08MH001,2026-10-07T10:20:00-08:00,1.541,,,1,17.9,,,1`. That is 18:20 UTC, so the newest observation was **71.3 min old when the file was written** and **106.7 min old at 20:06:39 UTC** (34 min before the next :31 rewrite). Note for Stage 1: timestamps carry a fixed **`-08:00`** offset (standard time) even though BC is on PDT (−07:00) today; parse the offset, never assume local time.
- `13:06` — **Outbound, ECCC OGC API.** `…/collections/hydrometric-stations/items?f=json&PROV_TERR_STATE_LOC=BC&limit=1` → `200 0.078s`, `numberMatched: 2324` BC stations (all statuses; first returned is a discontinued one).
- `13:06` — **Outbound, USGS.** OGC API `…/ogcapi/v0/collections` → `200 2.879s` (209,836 B), 39 collections including `continuous`, `latest-continuous`, `daily`, `monitoring-locations`, `time-series-metadata`. NWIS IV `?sites=12210700&parameterCd=00065&period=PT2H&format=json` with `curl -L` → `200 0.510s`, `num_redirects=0` (no redirect today), "NOOKSACK RIVER AT NORTH CEDARVILLE, WA", gage height, 5 values in the 2 h window; newest `138.01 ft` at `2026-10-07T12:15:00-07:00` (19:15 UTC), qualifier `P` (provisional), **51.9 min old**.
- `13:07` — **Outbound, NOAA NWPS.** `…/nwps/v1/gauges/NRKW1/stageflow` → `200 1.004s` (462,654 B). Forecast `issuedTime 2026-10-07T15:36:00Z` (**4.5 h old**), **29 points** from `2026-10-07T18:00Z` to `2026-10-14T18:00Z` (6-hourly, 7 days), units `ft`/`kcfs`. Observed series has 2,782 points; newest `19:30Z`, `138.02 ft` / `0.7 kcfs`, generated `19:41:31Z`, **36.9 min old**. NOAA stage (138.02 ft) and USGS gage height (138.01 ft) agree within 0.01 ft at nearly the same time, consistent with PLAN.md's shared-datum finding.
- `13:07` — **Outbound, other.** `https://github.com` → `200 0.217s`; `https://api.github.com/zen` → `200 0.090s`; `https://acme-v02.api.letsencrypt.org/directory` → `200 0.198s` (keys include `newAccount`, `newNonce`, `newOrder`, `renewalInfo`). **DNS:** `getent hosts <ip-with-dashes>.sslip.io` returns the VM's external IP (checked by script comparison, `DNS resolves to external IP: yes`); `dig @1.1.1.1` returns the same address.
- `13:07` — **Inbound probe.** `ss -ltn '( sport = :80 or sport = :443 )'` → no listeners; `/tmp/fl-probe` did not exist. Starting `sudo timeout 3600 python3 -m http.server 80 --directory /tmp/fl-probe` was **refused by the session's permission check** before anything ran (`ls /tmp/fl-probe` afterwards → `No such file or directory`). Not retried. See D-00.5.
- `13:07` — **Repository.** Clone at `~/trilemma-datathon`; `origin` = `https://github.com/agenticraptor/trilemma-datathon.git` (old name, redirected). On `stage-00-environment`; `git rev-list --left-right --count main...origin/main` → `0 0` (**`main` up to date** with `origin/main` at `b7b263e`). `gh repo view agenticraptor/trilemma-datathon --json …` resolves to `agenticraptor/trilemma-datathon-FloodLeadBC`, `viewerPermission: ADMIN`, `visibility: PUBLIC`, default branch `main`. References to the old name: `product.yaml:29`, `docs/build/prompts/STAGE-00-environment.md:66`, `docs/build/STAGE-00-human-setup.md:68`.
- `13:07` — **`.env`.** Did not exist. `git check-ignore -v .env` → `.gitignore:3:.env`. Created with `umask 077` and then `chmod 600` → `-rw------- prana prana 142 B`; keys `PUBLIC_HOSTNAME,POSTGRES_PASSWORD,ARCHIVE_DIR` (password from `openssl rand -hex 24`, 48 hex chars; value not printed). `ACME_EMAIL` left for the human. `git status --short` does not list `.env`.
- `13:07` — **Archive directory.** `/srv` existed and was empty, `/srv/floodlead` did not exist. `sudo install -d -m 755 -o prana -g prana /srv/floodlead /srv/floodlead/archive` → both owned by the worker user; write test (`touch`/`rm`) succeeded; `df -h /srv/floodlead/archive` → on `/dev/root`, 92G available. See D-00.4.
- `13:08` — Not run: `ruff check .` and `pytest`. This stage changes no code; neither tool is installed, and installing them is outside Stage 0's allowed changes. `tests/` holds only a README. The supervisor's independent run is unaffected.

## Measurements

Every number this stage measured, with how it was measured.

| What | Value | How measured | When |
|---|---|---|---|
| Machine class | e2-standard-2: 2 vCPU (Xeon @ 2.20 GHz, 1 core × 2 threads), 7.7 GiB RAM, 0 swap | GCE metadata `machine-type`, `lscpu`, `free -h` | 2026-10-07 20:04 UTC |
| Region | `northamerica-northeast2` (Toronto) → **Canada: yes** | GCE metadata `zone` | 20:04 UTC |
| OS / kernel | Ubuntu 24.04.5 LTS / 7.0.0-1011-gcp | `/etc/os-release`, `uname -r` | 20:04 UTC |
| Boot disk | pd-balanced, 100 GB (96 G ext4 root), 4.5 G used, **92 G free** | `gcloud compute disks describe`, `df -hT` | 20:04 UTC |
| Snapshot schedule on boot disk | **none**; 0 snapshots exist | `disks describe` → no `resourcePolicies`; `snapshots list` → empty | 20:04 UTC |
| External IP type | **ephemeral** (no reserved address in project) | `gcloud compute addresses list` → empty | 20:05 UTC |
| Load | load avg 0.33 / 0.29 / 0.13; CPU 90.9% idle; 6.8 GiB RAM available | `uptime`, `top -bn1`, `free -h` | 20:05 UTC |
| Ports free | 80 yes, 443 yes, 5432 yes, 8000 yes | `sudo ss -ltnp` | 20:05 UTC |
| Clock skew vs ECCC Datamart | in [−0.35, +0.11] s (0 s at 1 s resolution) | 5 HEAD requests, `Date` header vs request midpoint | 20:05 UTC |
| Clock skew vs NOAA NWPS | in [−0.42, +0.06] s (0 s at 1 s resolution) | same method | 20:05 UTC |
| Clock vs NTP | 0.0000044 s fast | `chronyc tracking` | 20:05 UTC |
| Datamart BC hourly listing | 200, 0.135 s, **429** `BC_*_hourly_hydrometric.csv` files, all stamped 19:31 UTC | `curl -w`, `grep` count | 20:06 UTC |
| 08MH001 hourly CSV | 200, 0.072 s, 701 rows, newest obs 18:20 UTC: 71.3 min old at file write, **106.7 min old** at fetch | `curl -w`, `tail`, Python delta | 20:06 UTC |
| ECCC OGC stations (BC) | 200, 0.078 s, `numberMatched` 2,324 | `curl -w`, `jq` | 20:06 UTC |
| USGS OGC collections | 200, **2.879 s**, 39 collections | `curl -w`, `jq` | 20:06 UTC |
| USGS NWIS IV 12210700 gage height | 200, 0.510 s, 0 redirects, newest 138.01 ft (P) at 19:15 UTC, **51.9 min old** | `curl -L -w`, Python delta | 20:06 UTC |
| NOAA NWPS NRKW1 stageflow | 200, 1.004 s; forecast issued 15:36 UTC (**4.5 h old**), **29 points** to Oct 14 18:00 UTC; newest observed 19:30 UTC (36.9 min old) | `curl -w`, `jq`, Python delta | 20:07 UTC |
| github.com / api.github.com / Let's Encrypt ACME | 200 0.217 s / 200 0.090 s / 200 0.198 s | `curl -w` | 20:07 UTC |
| sslip.io DNS | resolves to the VM's external IP | `getent hosts`, `dig @1.1.1.1` | 20:07 UTC |
| `du` of `/` | 4.5 G total; largest `/usr` 2.2 G, `/var` 1.1 G, `/home` 788 M | `sudo du -xh --max-depth=2 /` (9.4 s) | 20:05 UTC |

## Acceptance criteria

The prompt lists findings rather than numbered criteria; these ACs mirror its sections.

| AC | Result | Evidence |
|---|---|---|
| AC-1 Machine and region known; Canada stated | PASS | metadata → `e2-standard-2`, `northamerica-northeast2-a`; Canada: yes |
| AC-2 Disk, free space, snapshot schedule | PASS (finding: no schedule) | `disks describe` → pd-balanced 100 GB, no `resourcePolicies`; `df` → 92 G free |
| AC-3 Existing workload inventoried and untouched | PASS | `ss -ltnp` → only sshd, resolved, Ops Agent; no Docker, no app services, no crontabs. Nothing stopped or modified |
| AC-4 Clock synchronized, skew measured | PASS | `timedatectl` → synchronized: yes; skew ECCC [−0.35, +0.11] s, NOAA [−0.42, +0.06] s |
| AC-5 Tools ready for Stage 1 | **PARTIAL** | git, curl, jq, gh (authenticated), uv (installed), Python 3.12, claude, gcloud present. **Docker and Compose absent** (D-00.3), so Stage 1's Compose stack is blocked until the human decides |
| AC-6 Outbound to every Stage 1 source | PASS | all 9 endpoints `200`; DNS resolves; data ages 37–107 min (table above) |
| AC-7 Inbound reachability | **PARTIAL** | firewall `default-allow-http`/`-https` (0.0.0.0/0 → tags `http-server`/`https-server`) and the VM carries both tags. **Live probe not run**: refused by the permission check (D-00.5) |
| AC-8 Repository, push and PR rights | PASS | `main` = `origin/main` (`0 0`); `viewerPermission: ADMIN`; pushes succeed. Repo was renamed (D-00.6) |
| AC-9 `.env` and archive directory | PASS | `.env` 600, keys `PUBLIC_HOSTNAME,POSTGRES_PASSWORD,ARCHIVE_DIR`, gitignored; `/srv/floodlead/archive` owned by the worker user, writable |
| AC-10 Stage doc in git history, public-repo hygiene | PASS | doc touched in every commit on the branch; `grep` for project ID, project number, IPs and service-account domain → no matches |

## Contract files changed

| File | What changed | Why |
|---|---|---|
| (none) | — | Stage 0 is discovery only. `product.yaml` `repo:` is stale after the rename but was left for the human (D-00.6) |

## Open issues and handoff to next stage

**Blocking Stage 1**

1. **Docker is not installed.** Human decision: install Ubuntu's `docker.io` + `docker-compose-v2` (`sudo apt-get install -y docker.io docker-compose-v2`), or Docker's official `docker-ce` repo / `get.docker.com` as the old setup doc did. Then `sudo usermod -aG docker prana` and a re-login. Note that Docker adds its own iptables/nftables rules on install.

**Should be fixed before relying on the public URL or the archive**

2. **External IP is ephemeral.** A stop/start can change it and break the sslip.io hostname and certificate. Promote it to static in `northamerica-northeast2` (`gcloud compute addresses create floodlead-ip --addresses=<current-ip> --region=northamerica-northeast2`).
3. **No snapshot schedule on the boot disk**, and the archive lives on that disk. PLAN.md relies on daily snapshots as the off-machine copy. The only existing schedule (`default-schedule-1`) is in `us-central1` and cannot attach to a Toronto disk. Suggest a daily schedule created in `northamerica-northeast2` with `--storage-location=northamerica-northeast2` (keeps data in Canada), attached to the boot disk. Small extra cost.
4. **`ACME_EMAIL` missing from `.env`.** Caddy needs it for Let's Encrypt.
5. **Inbound probe not run.** If the supervisor wants proof before Stage 1, the human can run it (one hour, then it exits): `mkdir -p /tmp/fl-probe && openssl rand -hex 8 > /tmp/fl-probe/probe.txt && sudo timeout 3600 python3 -m http.server 80 --directory /tmp/fl-probe >/tmp/fl-probe.log 2>&1 &`, then fetch `http://<ip-with-dashes>.sslip.io/probe.txt` from outside.

**For the supervisor when writing Stage 1**

6. **Smaller machine than planned:** 2 vCPU / 7.7 GiB / no swap (the old setup doc assumed 4 vCPU / 16 GB). Fine for Postgres + API + Caddy + hourly pollers. For Stage 4 training, set Postgres memory limits and consider a swapfile (human call) to avoid the OOM killer.
7. **Repository renamed** to `agenticraptor/trilemma-datathon-FloodLeadBC`. Update `product.yaml:29`, the Stage 0 prompt and `git remote set-url origin` when convenient. The old URL still redirects.
8. **Datamart timestamps use a fixed `-08:00` offset** (standard time), not PDT. Parse offsets explicitly.
9. **Data latencies seen at 20:06 UTC:** ECCC 08MH001 71 min at file write (107 min just before the next rewrite), USGS 52 min, NOAA observed 37 min, NOAA forecast issued 4.5 h earlier. These match PLAN.md (ECCC ~1 h, USGS ~45 min). USGS OGC `collections` was slow (2.9 s), so use timeouts ≥ 10 s.
10. `architecture.md` still describes managed Postgres and S3-compatible object storage; PLAN.md now uses Postgres in Compose on the VM and a local-disk archive. Stage 1 should update it.
11. Another login account exists on this VM (uid 1002, empty home, no processes) and a project firewall rule `allow-bridge` opens tcp:9777 to a single source to all instances (nothing listens on it here). Both untouched. Mentioned so later stages do not use port 9777 by accident.
12. Git identity is not configured on the VM (D-00.1).
