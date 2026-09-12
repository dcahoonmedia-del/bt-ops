#!/usr/bin/env bash
# Stage deploy artifacts locally. Does not SSH, install, or restart the host.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE="${ROOT}/results/deploy-stage"
mkdir -p "$STAGE/scripts"
cp -f "$ROOT/scripts/guarded_desk_roundtrip_deploy.sh" "$STAGE/scripts/"
cp -f "$ROOT/scripts/desk_roundtrip_health.sh" "$STAGE/scripts/"
cp -f "$ROOT/scripts/record_predeploy_revision.sh" "$STAGE/scripts/"
cp -f "$ROOT/scripts/rollback_to_predeploy.sh" "$STAGE/scripts/"
cp -f "$ROOT/scripts/prepare_fresh_desk_case.py" "$STAGE/scripts/"
cp -f "$ROOT/scripts/deliver_desk_case_packet.py" "$STAGE/scripts/"
cp -f "$ROOT/scripts/verify_daniel_sent_runtime.py" "$STAGE/scripts/"
cp -f "$ROOT/scripts/merge_desk_roundtrip_env.py" "$STAGE/scripts/"
cp -f "$ROOT/results/DESK_ROUNDTRIP.md" "$STAGE/"
cp -f "$ROOT/results/DESK_ORIGIN_EVIDENCE.md" "$STAGE/"
git -C "$(cd "$ROOT/../.." && pwd)" rev-parse HEAD > "$STAGE/REVIEWED_REVISION.txt"
cat > "$STAGE/README.md" <<EOF
Guarded desk-roundtrip stage. Do not run install_cloud_host.sh for this cutover.

On the VM, as root, after verifying the immutable tarball SHA256:

  sudo bash scripts/guarded_desk_roundtrip_deploy.sh

That preflights, quiesces the worker, writes a unique code/env/unit backup,
then copies. On failure it restores code/env/unit automatically and does not
touch SQLite. Manual rollback uses that unique backup, not an assumed SHA:

  sudo bash scripts/rollback_to_predeploy.sh

Then prepare the unused case and optionally deliver the CASE packet only.
Do not send BT-DESK-ROUNDTRIP-SEND-E9A8.
EOF
echo "staged=$STAGE"
