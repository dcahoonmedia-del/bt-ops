#!/usr/bin/env bash
# Roll back to the revision recorded by record_predeploy_revision.sh.
# Fails closed if that file or snapshot is missing. Does not guess PR #14.
set -euo pipefail

PREFIX="${BT_INTAKE_PREFIX:-/opt/bt-intake-proof}"
STATE="${BT_INTAKE_STATE:-/var/lib/bt-intake-proof}"
RECORD="${STATE}/predeploy-revision.json"
SNAP="${STATE}/predeploy-tree"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "run as root on the GCE VM" >&2
  exit 1
fi
if [[ ! -f "$RECORD" ]]; then
  echo "missing $RECORD — run record_predeploy_revision.sh before install" >&2
  exit 1
fi
if [[ ! -d "$SNAP" ]]; then
  echo "missing snapshot $SNAP — cannot roll back without the recorded tree" >&2
  exit 1
fi

python3 - "$RECORD" <<'PY'
import json, sys
record = json.load(open(sys.argv[1], encoding="utf-8"))
revision = record.get("revision")
if not revision:
    raise SystemExit("predeploy record has no revision")
print(f"rolling back to {record.get('revision_source')} {revision}")
PY

rsync -a --delete --exclude secrets --exclude results/live --exclude .git "$SNAP/" "$PREFIX/"
systemctl daemon-reload
systemctl restart bt-intake-receiver.service
systemctl --no-pager --full status bt-intake-receiver.service || true
echo "rolled_back_to=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("revision"))' "$RECORD")"
