#!/usr/bin/env bash
# Quiesced desk-roundtrip deploy. Backs up code/env/unit only. Never prints secrets.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"

if [[ "$(id -u)" -ne 0 && "${BT_INTAKE_REQUIRE_ROOT:-1}" != "0" ]]; then
  echo "run as root on the GCE VM" >&2
  exit 1
fi

python3 -m bt_intake_proof.desk_deploy_txn deploy --source "$ROOT"
echo "rollback=sudo bash ${BT_INTAKE_PREFIX:-/opt/bt-intake-proof}/scripts/rollback_to_predeploy.sh"
