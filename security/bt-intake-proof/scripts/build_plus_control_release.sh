#!/usr/bin/env bash
# Pack a secrets-free immutable plus-control tree. Does not SSH or deploy.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "${ROOT}/../.." && pwd)"
DEST="${ROOT}/results/plus-control-release"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

COMMIT="$(git -C "$REPO" rev-parse HEAD)"
mkdir -p "$DEST" "${STAGE}/bt-intake-proof"

cp -a "${ROOT}/src" "${ROOT}/scripts" "${ROOT}/systemd" "${ROOT}/tests" "${STAGE}/bt-intake-proof/"
if [[ -d "${ROOT}/config" ]]; then
  cp -a "${ROOT}/config" "${STAGE}/bt-intake-proof/"
fi
find "${STAGE}/bt-intake-proof" -type d -name __pycache__ -prune -exec rm -rf {} +
find "${STAGE}/bt-intake-proof" -type f -name '*.pyc' -delete
rm -rf "${STAGE}/bt-intake-proof/secrets" "${STAGE}/bt-intake-proof/results"
for item in src scripts systemd tests; do
  [[ -d "${STAGE}/bt-intake-proof/${item}" ]] || { echo "missing $item" >&2; exit 1; }
done
[[ -f "${STAGE}/bt-intake-proof/systemd/bt-plus-control-poll.service" ]] || { echo "missing plus service" >&2; exit 1; }
[[ -f "${STAGE}/bt-intake-proof/systemd/bt-plus-control-poll.timer" ]] || { echo "missing plus timer" >&2; exit 1; }
if [[ -e "${STAGE}/bt-intake-proof/secrets" ]]; then
  echo "refusing to pack secrets" >&2
  exit 1
fi

TREE_SHA="$(python3 "${ROOT}/scripts/verify_release.py" --hash-only "${STAGE}/bt-intake-proof" | python3 -c 'import json,sys; print(json.load(sys.stdin)["tree_sha256"])')"
cat > "${STAGE}/bt-intake-proof/RELEASE.json" <<EOF
{
  "package": "bt-intake-plus-control",
  "source_commit": "${COMMIT}",
  "tree_sha256": "${TREE_SHA}",
  "tree_hash_excludes": ["RELEASE.json", "secrets/", "*.pyc"],
  "isolation": "isolated_test",
  "customer_sends": "off",
  "broad_capture": "off",
  "plus_poller": "installed_disabled",
  "plus_result_send": "not_included_not_sent",
  "secrets_included": false
}
EOF
python3 "${ROOT}/scripts/verify_release.py" "${STAGE}/bt-intake-proof" >/dev/null

tar -C "$STAGE" -czf "${DEST}/bt-intake-plus-control.tar.gz" bt-intake-proof
TAR_SHA="$(sha256sum "${DEST}/bt-intake-plus-control.tar.gz" | awk '{print $1}')"
cp -f "${STAGE}/bt-intake-proof/RELEASE.json" "${DEST}/RELEASE.json"

RAW="https://raw.githubusercontent.com/dcahoonmedia-del/bt-ops/${COMMIT}/security/bt-intake-proof/results/plus-control-release/bt-intake-plus-control.tar.gz"
cat > "${DEST}/TRANSFER" <<EOF
# Non-secret browser-SSH transfer card. No tokens or client JSON.

FILE=bt-intake-plus-control.tar.gz
SHA256=${TAR_SHA}
SOURCE_COMMIT=${COMMIT}
TREE_SHA256=${TREE_SHA}
RAW=${RAW}
DEST=/tmp/bt-intake-plus-control.tar.gz

# On the VM (Google Cloud SSH-in-browser). Keep secrets on the host.
# This Cursor VM does not have /var/lib/bt-intake-proof/receipts.sqlite.
# Deploy copies code/env/units only. Plus timer/service stay disabled
# until the project lead enables them after preflight.
# Do not send live mail. Do not reset SQLite. Do not mint credentials.

curl -fsSLo /tmp/bt-intake-plus-control.tar.gz ${RAW}
echo "${TAR_SHA}  /tmp/bt-intake-plus-control.tar.gz" | sha256sum -c
rm -rf /tmp/bt-intake-plus-control-src
mkdir -p /tmp/bt-intake-plus-control-src
tar -xzf /tmp/bt-intake-plus-control.tar.gz -C /tmp/bt-intake-plus-control-src
test ! -e /tmp/bt-intake-plus-control-src/bt-intake-proof/secrets
python3 /tmp/bt-intake-plus-control-src/bt-intake-proof/scripts/verify_release.py /tmp/bt-intake-plus-control-src/bt-intake-proof
sudo bash /tmp/bt-intake-plus-control-src/bt-intake-proof/scripts/guarded_desk_roundtrip_deploy.sh

# Confirm plus units are present and disabled:
# systemctl is-enabled bt-plus-control-poll.timer || true
# systemctl is-enabled bt-plus-control-poll.service || true

# Manual rollback restores code/env/unit only, never receipts or approvals:
# sudo bash /opt/bt-intake-proof/scripts/rollback_to_predeploy.sh

# Do not process 1a0979e37a0b0a94.
# Do not touch BTC-contactus-1a096d60643b3b1a.
# Do not resend BT-INTAKE-PROOF-CASEMGR-PHONE-7C92 / 1a096ffa404426f1.
# Keep customer sends and broad capture OFF.
EOF
cat > "${DEST}/MANIFEST.json" <<EOF
{
  "package": "bt-intake-plus-control",
  "sha256": "${TAR_SHA}",
  "source_commit": "${COMMIT}",
  "tree_sha256": "${TREE_SHA}",
  "isolation": "isolated_test",
  "customer_sends": "off",
  "broad_capture": "off",
  "plus_poller": "installed_disabled",
  "plus_result_send": "activation_blocker_until_separate_token",
  "secrets_included": false,
  "tests": "PYTHONPATH=src python3 -m unittest discover -s tests"
}
EOF

echo "tarball=${DEST}/bt-intake-plus-control.tar.gz"
echo "sha256=${TAR_SHA}"
echo "source_commit=${COMMIT}"
echo "tree_sha256=${TREE_SHA}"
