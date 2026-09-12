#!/usr/bin/env bash
# Isolated Case Manager draft. Mounts payload JSON only. No Gmail send, no Fieldwork.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${IMAGE:-bt-ops-codex-isolation:0.154.0}"
CONTAINER="${CONTAINER:-codex-iso-case-draft}"
VOLUME="${VOLUME:-codex-iso-chatgpt-home}"
PAYLOAD="${1:?usage: host_case_draft.sh /path/to/payload.json}"
RESULTS_DIR="${ROOT}/results/case-draft"

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
elif sudo docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
else
  echo "docker daemon is not available" >&2
  exit 1
fi

mkdir -p "${RESULTS_DIR}"
# Container uid 1000 cannot overwrite 0644 files owned by btintake (999).
chmod a+rwxt "${RESULTS_DIR}" || true
chmod a+rw "${RESULTS_DIR}"/* 2>/dev/null || true
PAYLOAD="$(cd "$(dirname "${PAYLOAD}")" && pwd)/$(basename "${PAYLOAD}")"
STAGE="${RESULTS_DIR}/$(basename "${PAYLOAD}")"
cp "${PAYLOAD}" "${STAGE}"
chmod a+r "${STAGE}"
PAYLOAD="${STAGE}"
DISPATCH_SCRIPT="${ROOT}/scripts/run_case_draft.py"

"${DOCKER[@]}" rm -f "${CONTAINER}" >/dev/null 2>&1 || true
"${DOCKER[@]}" run --rm --name "${CONTAINER}" \
  --read-only \
  --tmpfs /tmp:rw,nosuid,size=128m \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --pids-limit 256 \
  --memory "${CODEX_CONTAINER_MEMORY:-1g}" \
  --cpus 2 \
  --network bridge \
  --user 1000:1000 \
  --env CODEX_HOME=/opt/codex-isolation/runtime/home \
  --env HOME=/opt/codex-isolation/runtime/user \
  --env OPENAI_API_KEY= \
  --env CODEX_API_KEY= \
  --env CODEX_TEST_RESULTS=/opt/codex-isolation/results \
  --env BT_INTAKE_PAYLOAD=/tmp/intake-payload.json \
  --mount "type=volume,src=${VOLUME},dst=/opt/codex-isolation/runtime" \
  --mount "type=bind,src=${RESULTS_DIR},dst=/opt/codex-isolation/results" \
  --mount "type=bind,src=${PAYLOAD},dst=/tmp/intake-payload.json,ro=true" \
  --mount "type=bind,src=${DISPATCH_SCRIPT},dst=/tmp/run_case_draft.py,ro=true" \
  --entrypoint python3 \
  "${IMAGE}" /tmp/run_case_draft.py
