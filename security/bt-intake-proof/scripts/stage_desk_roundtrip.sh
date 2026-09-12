#!/usr/bin/env bash
# Stage deploy artifacts locally. Does not SSH, install, or restart the host.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE="${ROOT}/results/deploy-stage"
mkdir -p "$STAGE/scripts"
cp -f "$ROOT/scripts/install_cloud_host.sh" "$STAGE/scripts/"
cp -f "$ROOT/scripts/record_predeploy_revision.sh" "$STAGE/scripts/"
cp -f "$ROOT/scripts/rollback_to_predeploy.sh" "$STAGE/scripts/"
cp -f "$ROOT/results/DESK_ROUNDTRIP.md" "$STAGE/"
cp -f "$ROOT/results/DESK_ORIGIN_EVIDENCE.md" "$STAGE/"
git -C "$(cd "$ROOT/../.." && pwd)" rev-parse HEAD > "$STAGE/REVIEWED_REVISION.txt"
cat > "$STAGE/README.md" <<EOF
Staged only. Origin Sent corroboration is incomplete without the daniel@
readonly token. Do not deploy until that gate is live.

On the VM, as root, before install:
  sudo bash scripts/record_predeploy_revision.sh
  sudo bash scripts/install_cloud_host.sh

Rollback uses the recorded pre-deploy revision, not an assumed SHA:
  sudo bash scripts/rollback_to_predeploy.sh
EOF
echo "staged=$STAGE"
