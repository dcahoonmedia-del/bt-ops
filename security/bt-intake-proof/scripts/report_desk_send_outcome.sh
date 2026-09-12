#!/usr/bin/env bash
# Inspect or enqueue an accurate action-2 result. Never resends the proof. Prints no secrets.
set -euo pipefail

PREFIX="${BT_INTAKE_PREFIX:-/opt/bt-intake-proof}"
ETC="${BT_INTAKE_ETC:-/etc/bt-intake-proof}"
export PYTHONPATH="${PREFIX}/src${PYTHONPATH:+:$PYTHONPATH}"
export BT_INTAKE_ENV="${BT_INTAKE_ENV:-${ETC}/env}"

if [[ -n "${BT_ALLOW_REAL_CUSTOMER_SENDS:-}" || -n "${BT_ALLOW_CUSTOMER_SEND:-}" ]]; then
  echo "refusing: customer sends are enabled" >&2
  exit 2
fi

exec python3 "${PREFIX}/scripts/report_desk_send_outcome.py" --live "$@"
