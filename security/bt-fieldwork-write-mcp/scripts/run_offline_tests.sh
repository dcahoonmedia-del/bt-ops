#!/bin/bash
# Offline Fieldwork write-MCP tests. No live HQ, GCP, or IAM.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
python3 -m unittest discover -s "${ROOT}/tests" -v
