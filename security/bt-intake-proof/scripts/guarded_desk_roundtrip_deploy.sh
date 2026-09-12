#!/usr/bin/env bash
# Replace /opt/bt-intake-proof with this reviewed tree after recording the
# actual live revision. Does not copy secrets, reset SQLite, or send mail.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${BT_INTAKE_PREFIX:-/opt/bt-intake-proof}"
STATE="${BT_INTAKE_STATE:-/var/lib/bt-intake-proof}"
ETC="${BT_INTAKE_ETC:-/etc/bt-intake-proof}"
RECORD_SH="${ROOT}/scripts/record_predeploy_revision.sh"
MERGE_PY="${ROOT}/scripts/merge_desk_roundtrip_env.py"
HEALTH_SH="${ROOT}/scripts/desk_roundtrip_health.sh"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "run as root on the GCE VM" >&2
  exit 1
fi
if [[ ! -d "${ROOT}/src/bt_intake_proof" ]]; then
  echo "refusing deploy: missing ${ROOT}/src/bt_intake_proof" >&2
  exit 1
fi
if [[ -e "${ROOT}/secrets" ]] && find "${ROOT}/secrets" -type f -name '*.json' | grep -q .; then
  echo "refusing deploy: source tree contains secrets; keep tokens on the host" >&2
  exit 1
fi
if grep -R --include='*.py' -n "execute_due_sends(" "${ROOT}/src/bt_intake_proof/cloud_host.py" >/dev/null; then
  echo "refusing deploy: cloud_host still calls execute_due_sends" >&2
  exit 1
fi

echo "recording actual installed revision (do not assume PR #14)"
bash "$RECORD_SH"

export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
BEFORE="$(python3 - <<PY
import json
from pathlib import Path
from bt_intake_proof.desk_deploy_env import protected_fingerprints
print(json.dumps(protected_fingerprints(Path("${PREFIX}"), Path("${STATE}"))))
PY
)"

rsync -a --delete \
  --exclude secrets \
  --exclude results/live \
  --exclude .git \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  "${ROOT}/" "${PREFIX}/"

python3 "$MERGE_PY" --env "${ETC}/env" --prefix "$PREFIX" --state "$STATE" --write
chmod 640 "${ETC}/env"
if id btintake >/dev/null 2>&1; then
  chown root:btintake "${ETC}/env" 2>/dev/null || chown root:root "${ETC}/env"
  chown -R btintake:btintake "$PREFIX"
  # rsync excluded secrets; restore owner if the directory exists
  if [[ -d "${PREFIX}/secrets" ]]; then
    chown -R btintake:btintake "${PREFIX}/secrets"
    find "${PREFIX}/secrets" -type f -name '*.json' -exec chmod 600 {} \;
  fi
  if [[ -d "$STATE" ]]; then
    chown btintake:btintake "$STATE" "${STATE}/receipts.sqlite" 2>/dev/null || true
  fi
fi

AFTER="$(python3 - <<PY
import json
from pathlib import Path
from bt_intake_proof.desk_deploy_env import protected_fingerprints
print(json.dumps(protected_fingerprints(Path("${PREFIX}"), Path("${STATE}"))))
PY
)"
python3 - "$BEFORE" "$AFTER" <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path("${ROOT}") / "src"))
from bt_intake_proof.desk_deploy_env import protected_unchanged
before = json.loads(sys.argv[1])
after = json.loads(sys.argv[2])
changed = protected_unchanged(before, after)
if changed:
    raise SystemExit("protected host files changed during deploy: " + ",".join(changed))
print("protected_files_unchanged=true")
PY

if [[ -f "${ROOT}/systemd/bt-intake-receiver.service" ]]; then
  install -m 644 "${ROOT}/systemd/bt-intake-receiver.service" /etc/systemd/system/bt-intake-receiver.service
fi
systemctl daemon-reload
systemctl restart bt-intake-receiver.service
sleep 2
systemctl is-active --quiet bt-intake-receiver.service
echo "receiver=active"
bash "$HEALTH_SH"
echo "deployed_from=${ROOT}"
echo "rollback=sudo bash ${PREFIX}/scripts/rollback_to_predeploy.sh"
