# Stage 0 prompt — Environment discovery and readiness

You are the FloodLead BC build worker. Read `CLAUDE.md` and `AGENTS.md` first. This stage is **discovery**: find out exactly what this VM is, what already runs on it, and whether it can do everything Stage 1 needs. The supervisor will use your report to adapt the Stage 1 prompt, so accuracy matters more than speed. Target: 20–30 minutes.

## Rules for this stage

- **Read-only by default.** You may only make the safe changes listed under "Allowed changes". Ask the human before anything else.
- **This VM may already host other work.** Do not stop, restart, modify or remove any existing container, service, file, firewall rule or cron job.
- **No secrets in output.** Never print secret values, tokens or `.env` contents. Report only whether a key exists.
- **Public repo hygiene.** The committed doc must not contain the GCP project ID, service-account emails, internal IPs or secrets. Put those only in the terminal report for the human.

## Allowed changes

1. Install missing tools only if absent: `git`, `curl`, `jq`, `gh`, `uv`. Use `apt-get` or the official installers. Docker: if it is missing, **stop and ask** instead of installing.
2. Create `~/trilemma-datathon/.env` if missing, with `PUBLIC_HOSTNAME=<external-ip-with-dashes>.sslip.io`, `POSTGRES_PASSWORD=<openssl rand -hex 24>` and `ARCHIVE_DIR=/srv/floodlead/archive`, then `chmod 600`. Leave `ACME_EMAIL` for the human, and list it under "Needs human". If `.env` already exists, only add missing keys.
3. Create `/srv/floodlead/archive` owned by your user (needs `sudo`), only if `/srv` exists and the path is free.
4. Run a temporary **inbound reachability probe** (step 7). It must exit on its own within 60 minutes.
5. Branch `stage-00-environment`, add `docs/stages/STAGE-00-environment.md`, open a PR. Do not merge.

## What to find out

Collect the real command output for each item. If a command fails or is not permitted, say so: that is useful information too.

**1. Machine**
- Hostname, OS release (`/etc/os-release`), kernel, CPU count and model, RAM (`free -h`), swap.
- From the GCE metadata server (`curl -s -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/...`): project ID, zone (and so region), machine type, network tags, external IP, service account and scopes.
- Is the region in Canada (`northamerica-northeast1` or `-northeast2`)? State it plainly; personal data must stay in Canada.

**2. Disk**
- `lsblk`, `df -hT`, disk type and size (from metadata or `gcloud compute disks describe` if permitted).
- The largest directories on the root filesystem (`sudo du -xh --max-depth=2 / 2>/dev/null | sort -h | tail -25`).
- Whether a snapshot schedule is attached to the boot disk (`gcloud compute disks describe … --format='value(resourcePolicies)'`, if `gcloud` exists and is permitted).

**3. What already runs here (do not touch it)**
- `docker ps -a`, `docker compose ls`, `docker volume ls`, `docker network ls`.
- `sudo ss -ltnp` (all listening ports, especially 80, 443, 5432, 8000).
- `systemctl list-units --type=service --state=running`, user and root crontabs, current CPU/RAM load (`uptime`, `top -bn1 | head -20`).
- Conclude: which ports and resources are free for FloodLead (`db`, `api`, `caddy` on 80/443), and any conflicts.

**4. Time**
- `timedatectl` (timezone, NTP synchronized?). Compare system UTC time with the `Date` header from `https://dd.weather.gc.ca/` and `https://api.water.noaa.gov/` and report the skew in seconds. The forecast ledger depends on correct time.

**5. Tools and versions**
- `docker --version`, `docker compose version`, whether your user can run `docker ps` without `sudo`, `git --version`, `gh --version`, `gh auth status`, `uv --version`, `python3 --version`, which Python versions `uv python list` can provide (3.12 needed), `claude --version`, `gcloud --version` and `gcloud auth list` if present.

**6. Outbound access to every source Stage 1 uses**

For each URL below, report the HTTP status, total time (`curl -s -o /dev/null -w '%{http_code} %{time_total}s'`) and, where it is a data file, the newest timestamp in it:
- `https://dd.weather.gc.ca/today/hydrometric/csv/BC/hourly/` (listing; count the `BC_*_hourly_hydrometric.csv` files)
- `https://dd.weather.gc.ca/today/hydrometric/csv/BC/hourly/BC_08MH001_hourly_hydrometric.csv` (last row's timestamp and its age in minutes)
- `https://api.weather.gc.ca/collections/hydrometric-stations/items?f=json&PROV_TERR_STATE_LOC=BC&limit=1`
- `https://api.waterdata.usgs.gov/ogcapi/v0/collections`
- `https://waterservices.usgs.gov/nwis/iv/?sites=12210700&parameterCd=00065&period=PT2H&format=json` (follow redirects; newest value and its age)
- `https://api.water.noaa.gov/nwps/v1/gauges/NRKW1/stageflow` (forecast `issuedTime`, number of forecast points)
- `https://github.com`, `https://acme-v02.api.letsencrypt.org/directory`
- DNS: `getent hosts <external-ip-with-dashes>.sslip.io` must return the external IP.

**7. Inbound reachability (so the supervisor can test from outside)**
- If ports 80 and 443 are free: create `/tmp/fl-probe/` containing `probe.txt` with a random token (`openssl rand -hex 8`), then run `sudo timeout 3600 python3 -m http.server 80 --directory /tmp/fl-probe >/tmp/fl-probe.log 2>&1 &`.
- Verify locally with `curl -s http://localhost/probe.txt`. Report the public URL `http://<external-ip-with-dashes>.sslip.io/probe.txt` and the token, so the supervisor can fetch it from outside within the hour.
- If port 80 is taken, do not run the probe. Report what holds the port.
- Also list the firewall rules if `gcloud` is permitted (`gcloud compute firewall-rules list --format='table(name,sourceRanges.list(),allowed[].map().firewall_rule().list(),targetTags.list())'`) and the instance's network tags.

**8. Repository**
- Location of the clone, `git remote -v`, current branch, `git log -1 --oneline`, and whether `main` is up to date with `origin/main`.
- Push and PR rights: `gh repo view agenticraptor/trilemma-datathon --json viewerPermission,visibility`.
- `.env`: list key names only, and confirm it is gitignored (`git check-ignore .env`).

## The stage doc (`docs/stages/STAGE-00-environment.md`)

Use `docs/stages/_TEMPLATE.md`. Include machine class, region (Canada yes/no), OS, disk size and free space, the tool versions, outbound results (status and timing, no IPs), port availability, clock skew, and decisions (for example the archive directory location and why). Leave out the project ID, service account, IP addresses and secrets.

## Final output: STAGE 0 REPORT (print in the terminal; do not commit)

```text
STAGE 0 REPORT — Environment
Machine:        <machine type>, <vCPU>, <RAM>, OS <...>, zone <...> (Canada: yes/no)
Project:        <project id>
External IP:    <ip> → <ip-with-dashes>.sslip.io (DNS resolves: yes/no)
Disk:           <type> <size>, <free> free; snapshot schedule: <none|name>
Already running: <containers/services/ports, or "nothing">
Ports free:     80 <y/n>, 443 <y/n>, 5432 <y/n>, 8000 <y/n>
Clock:          NTP <synced?>, skew vs ECCC <s>, vs NOAA <s>
Tools:          docker <v> (no-sudo: y/n), compose <v>, git <v>, gh <v> (<auth status>), uv <v>, python <v> (3.12 available: y/n), claude <v>, gcloud <v|absent>
Outbound:       <one line per source: status, time, newest data age>
Inbound probe:  http://<host>/probe.txt token=<token> (expires <time UTC>) | not run because <reason>
Firewall:       <rules allowing 80/443 to this VM's tags, or "unknown (no permission)">
Repo:           <path>, branch <...>, <sha>, push permission <...>, .env keys <names>
PR:             <url>
Changes made:   <everything installed or created>
Needs human:    <e.g. ACME_EMAIL, firewall rule, Docker install, snapshot schedule>
```
