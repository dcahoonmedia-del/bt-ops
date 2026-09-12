#!/usr/bin/env bash
# Restore the unique pre-deploy code/env/unit backup. Does not revert SQLite.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"

if [[ "$(id -u)" -ne 0 && "${BT_INTAKE_REQUIRE_ROOT:-1}" != "0" ]]; then
  echo "run as root on the GCE VM" >&2
  exit 1
fi

if [[ $# -ge 1 ]]; then
  python3 -m bt_intake_proof.desk_deploy_txn rollback --backup-id "$1"
else
  python3 -m bt_intake_proof.desk_deploy_txn rollback
fi
