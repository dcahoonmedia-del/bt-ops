#!/usr/bin/env bash
# Start isolated ChatGPT device-code login and leave the container waiting.
# Does not wipe prior preflight/network evidence.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS_DIR="${ROOT}/results/chatgpt-auth"
IMAGE="${IMAGE:-bt-ops-codex-isolation:0.154.0}"
NETWORK="${NETWORK:-codex-iso-net}"
SUBNET="${SUBNET:-172.28.154.0/24}"
CONTAINER="${CONTAINER:-codex-iso-chatgpt-login}"
VOLUME="${VOLUME:-codex-iso-chatgpt-home}"

mkdir -p "${RESULTS_DIR}"

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
elif sudo docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
else
  echo "docker daemon is not available" >&2
  exit 1
fi

echo "==> building isolated image ${IMAGE}"
"${DOCKER[@]}" build -t "${IMAGE}" "${ROOT}"

if ! "${DOCKER[@]}" network inspect "${NETWORK}" >/dev/null 2>&1; then
  "${DOCKER[@]}" network create --driver bridge --subnet "${SUBNET}" "${NETWORK}" >/dev/null
fi
"${DOCKER[@]}" volume create "${VOLUME}" >/dev/null
"${DOCKER[@]}" rm -f "${CONTAINER}" >/dev/null 2>&1 || true

echo "==> starting isolated ChatGPT device-code login"
"${DOCKER[@]}" run -d --name "${CONTAINER}" \
  --read-only \
  --tmpfs /tmp:rw,nosuid,size=128m \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --pids-limit 256 \
  --memory 2g \
  --cpus 2 \
  --network "${NETWORK}" \
  --user 1000:1000 \
  --env CODEX_HOME=/opt/codex-isolation/runtime/home \
  --env HOME=/opt/codex-isolation/runtime/user \
  --env OPENAI_API_KEY= \
  --env CODEX_API_KEY= \
  --env CODEX_TEST_RESULTS=/opt/codex-isolation/results \
  --mount "type=volume,src=${VOLUME},dst=/opt/codex-isolation/runtime" \
  --mount "type=bind,src=${RESULTS_DIR},dst=/opt/codex-isolation/results" \
  "${IMAGE}" --phase login-and-test0

echo "==> waiting for device-code challenge"
for i in $(seq 1 90); do
  if [[ -f "${RESULTS_DIR}/auth-challenge.json" ]]; then
    echo "AUTH_CHALLENGE_READY"
    cat "${RESULTS_DIR}/auth-challenge.json"
    echo
    echo "Container ${CONTAINER} is waiting for you to approve the device code."
    echo "It will run Test 0 automatically after login completes."
    exit 0
  fi
  if ! "${DOCKER[@]}" inspect -f '{{.State.Running}}' "${CONTAINER}" 2>/dev/null | grep -q true; then
    echo "container exited before publishing a device-code challenge" >&2
    "${DOCKER[@]}" logs "${CONTAINER}" >&2 || true
    exit 1
  fi
  sleep 1
done

echo "timed out waiting for auth-challenge.json" >&2
"${DOCKER[@]}" logs "${CONTAINER}" >&2 || true
exit 1
