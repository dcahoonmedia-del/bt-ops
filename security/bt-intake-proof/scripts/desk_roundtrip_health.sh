#!/usr/bin/env bash
# Host health for isolated desk-roundtrip. Prints no secrets.
set -euo pipefail

PREFIX="${BT_INTAKE_PREFIX:-/opt/bt-intake-proof}"
STATE="${BT_INTAKE_STATE:-/var/lib/bt-intake-proof}"
ETC="${BT_INTAKE_ETC:-/etc/bt-intake-proof}"
export PYTHONPATH="${PREFIX}/src${PYTHONPATH:+:$PYTHONPATH}"

if [[ ! -f "${ETC}/env" ]]; then
  echo "missing ${ETC}/env" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
. "${ETC}/env"
set +a

systemctl is-active --quiet bt-intake-receiver.service
echo "receiver=active"

python3 - <<'PY'
import json, os, pathlib, sys
from bt_intake_proof.intake_mode import describe_mode, require_isolated_live_receiver
from bt_intake_proof.cloud_host import run_once, serve
import inspect

mode = require_isolated_live_receiver()
desc = describe_mode()
src = inspect.getsource(run_once) + inspect.getsource(serve)
if "execute_due_sends(" in src:
    raise SystemExit("cloud_host calls execute_due_sends")
if desc.get("real_customer_processing") is not False:
    raise SystemExit("real_customer_processing is not false")
if os.environ.get("BT_INTAKE_MODE", "isolated_test") != "isolated_test":
    raise SystemExit("BT_INTAKE_MODE is not isolated_test")
if os.environ.get("BT_ALLOW_REAL_CUSTOMER_SENDS"):
    raise SystemExit("BT_ALLOW_REAL_CUSTOMER_SENDS is set")
print(json.dumps({
    "mode": mode,
    "describe": desc,
    "broad_capture": "off",
    "customer_sends": "off",
    "desk_execute_only": True,
}, indent=2))
PY

DANIEL="${BT_DANIEL_GMAIL_TOKEN:-${PREFIX}/secrets/daniel_gmail_readonly_token.json}"
if [[ ! -f "$DANIEL" ]]; then
  echo "missing daniel readonly token at $DANIEL" >&2
  exit 1
fi
python3 - "$DANIEL" <<'PY'
import os, stat, sys
path = sys.argv[1]
st = os.stat(path)
mode = stat.S_IMODE(st.st_mode)
if mode != 0o600:
    raise SystemExit(f"daniel token mode {oct(mode)} != 0o600")
print(f"daniel_token_present=true mode=600 uid={st.st_uid}")
PY

if [[ ! -f "${STATE}/receipts.sqlite" ]]; then
  echo "missing ${STATE}/receipts.sqlite" >&2
  exit 1
fi
echo "sqlite_present=true"

if command -v sudo >/dev/null 2>&1 && id btintake >/dev/null 2>&1 && [[ "$(id -u)" -eq 0 ]]; then
  sudo -u btintake env PYTHONPATH="${PREFIX}/src" BT_INTAKE_ENV="${ETC}/env" \
    python3 "${PREFIX}/scripts/verify_daniel_sent_runtime.py"
else
  python3 "${PREFIX}/scripts/verify_daniel_sent_runtime.py"
fi

echo "health=PASS"
