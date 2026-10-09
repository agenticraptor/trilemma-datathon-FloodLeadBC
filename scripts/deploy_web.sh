#!/bin/sh
# Deploy the static app (web/) to the directory Caddy serves (Stage 3, D-03.11). Run from a branch with an open PR.
# rsync --delete updates files in place and keeps the target directory itself, so Caddy's bind mount stays valid.
set -eu
cd "$(dirname "$0")/.."
dest="${WEB_DIR:-/srv/floodlead/web}"
rsync -a --delete web/ "$dest/"
printf '%s\n' "$(git rev-parse HEAD)" > "$dest/.deployed-commit"
echo "deployed web/ at $(git rev-parse --short HEAD) to $dest"
