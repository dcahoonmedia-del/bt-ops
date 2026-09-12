#!/usr/bin/env bash
# Install the proven intake path as a reboot-persistent systemd service.
# Does not create a VM, enable APIs, or download a service-account JSON key.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ISO_ROOT="$(cd "${ROOT}/../codex-external-isolation" && pwd)"
PREFIX="${BT_INTAKE_PREFIX:-/opt/bt-intake-proof}"
ISO_PREFIX="${BT_ISO_PREFIX:-/opt/codex-external-isolation}"
STATE="${BT_INTAKE_STATE:-/var/lib/bt-intake-proof}"
ETC="${BT_INTAKE_ETC:-/etc/bt-intake-proof}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "run as root on the GCE VM" >&2
  exit 1
fi

id btintake >/dev/null 2>&1 || useradd --system --home "$STATE" --shell /usr/sbin/nologin btintake
mkdir -p "$PREFIX" "$ISO_PREFIX" "$STATE" "$ETC"
rsync -a --delete --exclude secrets --exclude results/live --exclude .git "$ROOT/" "$PREFIX/"
if [[ -d "$ISO_ROOT" ]]; then
  rsync -a --delete --exclude results --exclude .git "$ISO_ROOT/" "$ISO_PREFIX/"
fi
if [[ -d "$ROOT/secrets" ]]; then
  mkdir -p "$PREFIX/secrets"
  install -m 600 -o btintake -g btintake "$ROOT/secrets/contactus_gmail_readonly_token.json" "$PREFIX/secrets/" 2>/dev/null || true
  install -m 600 -o btintake -g btintake "$ROOT/secrets/gmail_oauth_client.json" "$PREFIX/secrets/" 2>/dev/null || true
  install -m 600 -o btintake -g btintake "$ROOT/secrets/contactus_gmail_send_token.json" "$PREFIX/secrets/" 2>/dev/null || true
fi
cat > "$ETC/env" <<EOF
PYTHONPATH=${PREFIX}/src
BT_INTAKE_STORE=${STATE}/receipts.sqlite
BT_GMAIL_TOKEN=${PREFIX}/secrets/contactus_gmail_readonly_token.json
BT_GMAIL_OAUTH_CLIENT=${PREFIX}/secrets/gmail_oauth_client.json
BT_GMAIL_SEND_TOKEN=${PREFIX}/secrets/contactus_gmail_send_token.json
BT_INTAKE_INTERVAL=2
CODEX_CONTAINER_MEMORY=1g
OPENAI_API_KEY=
CODEX_API_KEY=
EOF
chmod 640 "$ETC/env"
getent group docker >/dev/null 2>&1 && usermod -aG docker btintake || true
mkdir -p "$ISO_PREFIX/results/intake-dispatch"
chmod 1777 "$ISO_PREFIX/results" "$ISO_PREFIX/results/intake-dispatch" || true
chown -R btintake:btintake "$PREFIX" "$ISO_PREFIX" "$STATE" "$ETC"
chmod 1777 "$ISO_PREFIX/results" "$ISO_PREFIX/results/intake-dispatch" || true
install -m 644 "$ROOT/systemd/bt-intake-receiver.service" /etc/systemd/system/bt-intake-receiver.service
systemctl daemon-reload
systemctl enable bt-intake-receiver.service
systemctl restart bt-intake-receiver.service
systemctl --no-pager --full status bt-intake-receiver.service || true
echo "installed. json_key_created=false"
