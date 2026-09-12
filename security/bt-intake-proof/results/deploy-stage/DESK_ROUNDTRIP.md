# Desk round-trip scorecard

Reviewed baseline: `378ffcf` / PR #14
This revision: worker + guarded deploy on `cursor/bt-intake-roundtrip-e9a8` (see `results/desk-roundtrip-release/`).
Installed host worker revision: **UNKNOWN** (not read this run). Codex installed OAuth helper `db53477` only. No worker restart observed.

Isolation: BT-INTAKE-PROOF on. Real-customer sends OFF. Broad/shadow capture OFF.
This milestone is **not** an approval row and does **not** reuse Phase E action 1 / `BT-PHASE-E-SEND-E9A8-C4F1`.
A generic go authorized prepare/deploy only. It is not `approve_send` and not approval of unseen content.

Evidence labels: **unit** / **fixture** / **runtime** / **real-phone**.

## Gates

| Gate | Result | Evidence |
| --- | --- | --- |
| Mixed DKIM/SPF method binding | **PASS** (unit) | Codex header `accepted=False`. `tests/test_desk_origin.py` |
| Reversed / multiple / lookalike / malformed AR | **PASS** (unit) | same |
| Domain DKIM ≠ Daniel mailbox | **PASS** (unit + runtime) | `DESK_ORIGIN_EVIDENCE.md` |
| Mailbox-bound AR is not authorization | **PASS** (unit) | `authenticate_control_origin` stays `accepted=False` |
| Exact daniel@ Sent corroboration | **PASS** (fixture) | recipient + canonical payload + timing + Message-ID |
| Missing / ambiguous / mismatched Sent | **PASS** (fixture) | fail closed |
| Pending replay / boolean / legacy flag | **PASS** (unit) | no `origin_already_authenticated`; versioned `desk-sent-v1` |
| Helper token format / path | **PASS** (unit) | `email`/`account` + `scopes`/`scope`; `ExistingDanielSentLookup` |
| Fresh case prepare does not approve/queue | **PASS** (unit) | `tests/test_desk_roundtrip_release.py` |
| Env merge preserves tokens / forces isolated | **PASS** (unit) | same |
| Host loop desk-execute only | **PASS** (unit) | `finish_desk_roundtrip`; no `execute_due_sends` |
| Deploy preflight fails before mutation | **PASS** (sandbox) | missing systemctl/source |
| Deploy failure after env/unit auto-rollback | **PASS** (sandbox) | `tests/test_desk_deploy_txn.py` |
| Rollback restores env/unit, not SQLite | **PASS** (sandbox) | unique backups; approvals preserved |
| Full identity PASS | **FAIL / not claimed** | Sent match is mailbox corroboration, not human identity |
| Runtime daniel@ Sent lookup | **BLOCKED** | token exists on host (Codex-observed); this VM cannot run as `btintake` |
| Runtime Gmail RESULT/CTRL/send | **PENDING** | worker not deployed from this run |
| Exact approved internal send | **PENDING** | awaiting Daniel's decision on the exact packet |
| Real iPhone / Mac-off | **PENDING** | do not claim |
| Live worker deploy | **BLOCKED** | no SSH key / no gcloud on this VM; `Permission denied (publickey)` to `35.243.167.73` |

**Unit:** `PYTHONPATH=src python3 -m unittest discover -s tests` → 178 passed, 1 skipped.

## Deployment

This VM cannot deploy. Do not invent SSH keys. Do not retry SSH. Codex runs the existing Google Cloud SSH-in-browser session.

Do **not** use `install_cloud_host.sh`.

Guarded transaction (`desk_deploy_txn.py`):

1. Preflight dependencies and release verification. No mutation on failure.
2. Stop/quiesce the receiver.
3. Unique protected backup of **code + env + unit** (presence, mode, ownership). Prior backups are kept.
4. Copy code excluding secrets. Merge env. Install unit.
5. Verify SQLite/WAL identity and token files unchanged. Then restore prior service state and health-check.
6. On failure after mutation: automatic restore of code/env/unit and prior service state. Reports `deployment=FAIL` and `rollback=PASS|FAIL` separately.
7. Rollback never reverts receipts, approvals, or tokens.

Exact Codex command: `results/desk-roundtrip-release/TRANSFER` (deploy only; no send).

## Fresh case / exact decision

Case id: `BTC-contactus-desk-roundtrip-e9a8-20260912`

Exact isolated send (**not sent**, **not approved**):

- From: `contactus@btpestcontrol.com`
- To: `daniel@btpestcontrol.com`
- CC: none
- Subject: `BT-DESK-ROUNDTRIP-SEND-E9A8 internal send test`
- Timing: `immediate_supervised`
- Body: see `results/desk-roundtrip-release/DECISION_PACKET.md`

Next user-facing step: Daniel sees that exact recipient/subject/body (via the CASE packet or this file) and decides naturally. ChatGPT may then send one structured control. Do not treat a generic go as that decision.

## Rollback

```
sudo bash /opt/bt-intake-proof/scripts/rollback_to_predeploy.sh
```

Uses the unique backup at `/var/lib/bt-intake-proof/predeploy-backups/` pointed to by `current-predeploy.json`. Restores code/env/unit only.
