#!/usr/bin/env bash
# Pack a secrets-free immutable desk-roundtrip tree. Does not SSH or deploy.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "${ROOT}/../.." && pwd)"
DEST="${ROOT}/results/desk-roundtrip-release"
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
if [[ -e "${STAGE}/bt-intake-proof/secrets" ]]; then
  echo "refusing to pack secrets" >&2
  exit 1
fi

TREE_SHA="$(python3 "${ROOT}/scripts/verify_release.py" --hash-only "${STAGE}/bt-intake-proof" | python3 -c 'import json,sys; print(json.load(sys.stdin)["tree_sha256"])')"
cat > "${STAGE}/bt-intake-proof/RELEASE.json" <<EOF
{
  "package": "bt-intake-desk-roundtrip",
  "source_commit": "${COMMIT}",
  "tree_sha256": "${TREE_SHA}",
  "tree_hash_excludes": ["RELEASE.json", "secrets/", "*.pyc"],
  "isolation": "isolated_test",
  "customer_sends": "off",
  "broad_capture": "off",
  "proof_reply": "not_included_not_sent",
  "secrets_included": false
}
EOF
python3 "${ROOT}/scripts/verify_release.py" "${STAGE}/bt-intake-proof" >/dev/null

tar -C "$STAGE" -czf "${DEST}/bt-intake-desk-roundtrip.tar.gz" bt-intake-proof
TAR_SHA="$(sha256sum "${DEST}/bt-intake-desk-roundtrip.tar.gz" | awk '{print $1}')"
cp -f "${STAGE}/bt-intake-proof/RELEASE.json" "${DEST}/RELEASE.json"
python3 "${ROOT}/scripts/prepare_fresh_desk_case.py" --out "$DEST" >/dev/null

RAW="https://raw.githubusercontent.com/dcahoonmedia-del/bt-ops/${COMMIT}/security/bt-intake-proof/results/desk-roundtrip-release/bt-intake-desk-roundtrip.tar.gz"
cat > "${DEST}/TRANSFER" <<EOF
# Non-secret browser-SSH transfer card. No tokens or client JSON.

FILE=bt-intake-desk-roundtrip.tar.gz
SHA256=${TAR_SHA}
SOURCE_COMMIT=${COMMIT}
RAW=${RAW}
DEST=/tmp/bt-intake-desk-roundtrip.tar.gz

# On the VM (Google Cloud SSH-in-browser). Keep secrets on the host.
# Deploy transaction only. Do not send BT-DESK-ROUNDTRIP-SEND-E9A8.
# Do not reset SQLite. Do not prepare/deliver mail in this command.

curl -fsSLo /tmp/bt-intake-desk-roundtrip.tar.gz ${RAW}
echo "${TAR_SHA}  /tmp/bt-intake-desk-roundtrip.tar.gz" | sha256sum -c
rm -rf /tmp/bt-intake-desk-roundtrip-src
mkdir -p /tmp/bt-intake-desk-roundtrip-src
tar -xzf /tmp/bt-intake-desk-roundtrip.tar.gz -C /tmp/bt-intake-desk-roundtrip-src
test ! -e /tmp/bt-intake-desk-roundtrip-src/bt-intake-proof/secrets
python3 /tmp/bt-intake-desk-roundtrip-src/bt-intake-proof/scripts/verify_release.py /tmp/bt-intake-desk-roundtrip-src/bt-intake-proof
sudo bash /tmp/bt-intake-desk-roundtrip-src/bt-intake-proof/scripts/guarded_desk_roundtrip_deploy.sh

# Manual rollback restores code/env/unit only, never receipts or approvals:
# sudo bash /opt/bt-intake-proof/scripts/rollback_to_predeploy.sh

# After deploy + health PASS, inspect failed action 2 only (no send, no re-queue):
# sudo -u btintake bash /opt/bt-intake-proof/scripts/recover_failed_desk_send.sh \\
#   --action-id 2 --case-id BTC-contactus-desk-roundtrip-e9a8-20260912
#
# If dry-run reports recovery_authorized=true, omit_gmail_thread_id=true,
# sent_check exact_matches=0, and host_loop_would_select=false, one attempt:
# sudo -u btintake bash /opt/bt-intake-proof/scripts/recover_failed_desk_send.sh \\
#   --action-id 2 --case-id BTC-contactus-desk-roundtrip-e9a8-20260912 --execute
#
# Do not reset SQLite, reissue approval, mutate thread_id/payload_sha256, or
# set status back to queued. Do not send from Cursor/Gmail MCP.
EOF

echo "tarball=${DEST}/bt-intake-desk-roundtrip.tar.gz"
echo "sha256=${TAR_SHA}"
echo "source_commit=${COMMIT}"
echo "tree_sha256=${TREE_SHA}"
