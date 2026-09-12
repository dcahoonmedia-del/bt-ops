#!/usr/bin/env bash
# Dispatch one durable intake receipt into the already-validated isolated Codex runtime.
# Mounts only the payload JSON. No Gmail, Fieldwork, or host Codex home.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${IMAGE:-bt-ops-codex-isolation:0.154.0}"
CONTAINER="${CONTAINER:-codex-iso-intake-dispatch}"
VOLUME="${VOLUME:-codex-iso-chatgpt-home}"
PAYLOAD="${1:?usage: host_intake_dispatch.sh /path/to/payload.json}"
RESULTS_DIR="${ROOT}/results/intake-dispatch"

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
elif sudo docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
else
  echo "docker daemon is not available" >&2
  exit 1
fi

mkdir -p "${RESULTS_DIR}"
# Container runs as uid 1000; the GCE service user is btintake (999).
# Sticky dir bits are not enough if a prior result file is 0644 owned by 999.
chmod a+rwxt "${RESULTS_DIR}" || true
chmod a+rw "${RESULTS_DIR}"/* 2>/dev/null || true
PAYLOAD="$(cd "$(dirname "${PAYLOAD}")" && pwd)/$(basename "${PAYLOAD}")"
STAGE="${RESULTS_DIR}/$(basename "${PAYLOAD}")"
cp "${PAYLOAD}" "${STAGE}"
chmod a+r "${STAGE}"
PAYLOAD="${STAGE}"
DISPATCH_SCRIPT="${ROOT}/scripts/run_intake_dispatch.py"

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
  --mount "type=bind,src=${DISPATCH_SCRIPT},dst=/tmp/run_intake_dispatch.py,ro=true" \
  --entrypoint python3 \
  "${IMAGE}" /tmp/run_intake_dispatch.py
