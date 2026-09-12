#!/usr/bin/env bash
# Install the proven intake path as a reboot-persistent systemd service.
# Does not create a VM, enable APIs, or download a service-account JSON key.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${BT_INTAKE_PREFIX:-/opt/bt-intake-proof}"
STATE="${BT_INTAKE_STATE:-/var/lib/bt-intake-proof}"
ETC="${BT_INTAKE_ETC:-/etc/bt-intake-proof}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "run as root on the GCE VM" >&2
  exit 1
fi

id btintake >/dev/null 2>&1 || useradd --system --home "$STATE" --shell /usr/sbin/nologin btintake
mkdir -p "$PREFIX" "$STATE" "$ETC"
rsync -a --delete --exclude secrets --exclude results/live --exclude .git "$ROOT/" "$PREFIX/"
if [[ -d "$ROOT/secrets" ]]; then
  mkdir -p "$PREFIX/secrets"
  install -m 600 -o btintake -g btintake "$ROOT/secrets/contactus_gmail_readonly_token.json" "$PREFIX/secrets/" 2>/dev/null || true
  install -m 600 -o btintake -g btintake "$ROOT/secrets/gmail_oauth_client.json" "$PREFIX/secrets/" 2>/dev/null || true
fi
cat > "$ETC/env" <<EOF
PYTHONPATH=${PREFIX}/src
BT_INTAKE_STORE=${STATE}/receipts.sqlite
BT_GMAIL_TOKEN=${PREFIX}/secrets/contactus_gmail_readonly_token.json
BT_GMAIL_OAUTH_CLIENT=${PREFIX}/secrets/gmail_oauth_client.json
BT_INTAKE_INTERVAL=2
OPENAI_API_KEY=
CODEX_API_KEY=
EOF
chmod 640 "$ETC/env"
chown -R btintake:btintake "$PREFIX" "$STATE" "$ETC"
install -m 644 "$ROOT/systemd/bt-intake-receiver.service" /etc/systemd/system/bt-intake-receiver.service
systemctl daemon-reload
systemctl enable bt-intake-receiver.service
systemctl restart bt-intake-receiver.service
systemctl --no-pager --full status bt-intake-receiver.service || true
echo "installed. json_key_created=false"
