# LIVE-FW-READ-1 — bounded Fieldwork identity/context read

Offline matcher/adapter/runner: **PASS** (`PYTHONPATH=src python3 -m unittest discover -s tests` → 274 passed, 1 skipped).  
Live Fieldwork on this Cursor VM: **BLOCKED**.  
Always-on receiver: **unchanged** (still `grok_bot_client()` fixture only).  
Draft / enqueue / send: **not invoked**.  
Credential minting: **removed** from this milestone.

This is not a live HQ pass. Fixture results stay `FIELDWORK_FIXTURE_VERIFIED` / `live=false`. They are never relabeled live. Synthetic fixture paths are labeled `synthetic_fixture` and are not independent inbound matching proof.

## Coverage

| Layer | Offline fixture | Live from this VM |
| --- | --- | --- |
| Identity (manifest customer/property vs matcher vs direct read) | PASS on synthetic catalog | **BLOCKED** — no host credential |
| Context (notes / agreement / estimates / appointments / recent service, with date window) | PASS on synthetic catalog | **BLOCKED** |
| Provenance (`live` / source label cannot be confused) | PASS | **BLOCKED** |
| Independent inbound matching proof (`source_evidence`) | not claimed | **BLOCKED** until a private source-evidence manifest exists on the host |

Date window is retrieve-time ± `date_window_days` (default 365). Work-order customer filter is unsupported on the live API client; that component is INCOMPLETE/unsupported, never a zero PASS.

## Offline scorecard

| Scenario | Result | Notes |
| --- | --- | --- |
| Receipt construction refuses invented live identifiers | PASS | Missing data → insufficient, not `14 Fixture Lane` |
| compare_to_direct rejects missing property and agreement false positives | PASS | Expected manifest IDs required |
| Failed direct read / wrong IDs / disagreement both ways | PASS | BLOCKED / FAIL / INCOMPLETE as specified |
| Full-name query zero is not “case absent”; name alone is not identity | PASS | Surname aliases still require corroboration |
| Multi-identifier synthetic cases + selected property | PASS | Fixture catalog only |
| Ambiguity probes abstain | PASS | Identifiers come from the scenario, not `locations[0]` |
| Synthetic no-match after complete searches | PASS | Creates no record |
| Auth / schema / truncated / unscoped WO | PASS | blocked / incomplete / omitted |
| Private artifacts created 0600 / 0700 | PASS | `os.open` 0600, dir 0700 at creation |
| `live-fw-issue-key` removed | PASS | |
| Live preflight from this VM | **BLOCKED** | no existing host credential consumed |

## Host execution (only after project-lead provisioning)

See `PROVISIONING.md`. Do not run these until the existing authorized key file and private source-evidence manifest are on the host.

```bash
export BT_FIELDWORK_LIVE_READ=1
export FIELDWORK_API_KEY_FILE=<project-lead-0600-path>
export PYTHONPATH=src
cd /opt/bt-intake-proof

python3 -m bt_intake_proof.cli live-fw-preflight --mode live
python3 -m bt_intake_proof.cli live-fw-read --mode live \
  --manifest /var/lib/bt-intake-proof/live-fw-read/manifest.json \
  --out /var/lib/bt-intake-proof/live-fw-read/evidence
```

`live-fw-resolve` may fill native IDs only after source-evidence identifiers are present on the labels. A unique name is not identity. Full-name zero is not absence.

Offline fixture:

```bash
PYTHONPATH=src python3 -m bt_intake_proof.cli live-fw-preflight --mode fixture
PYTHONPATH=src python3 -m bt_intake_proof.cli live-fw-read --mode fixture \
  --manifest config/live_fw_read_manifest.example.json \
  --out /tmp/live-fw-read-fixture
```

## Remaining limitations

- Live work-order search has no documented `filter[customer_id]`. That field is unsupported / INCOMPLETE on live, not an empty history PASS.
- Provider token permission is not independently verified as read-only. The adapter enforces GET + allowlist + no other-host credential redirects.
- Connector search evidence is not this API client and is not treated as host integration proof.
- The always-on receiver is not switched to live Fieldwork.
- No scheduling, notes, estimates, customers, or mail writes.
- Missing digital agreements are not inferred into contract terms.

## Overall

| Layer | Result |
| --- | --- |
| Offline implementation + unit tests | **PASS** (274 passed, 1 skipped) |
| Live bounded read from this VM | **BLOCKED** |
| Milestone LIVE-FW-READ-1 live proof | **BLOCKED** until project-lead provisioning and a private host manifest exist |
