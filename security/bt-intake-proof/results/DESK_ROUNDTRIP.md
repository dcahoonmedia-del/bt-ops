# Desk round-trip scorecard

Reviewed baseline: `378ffcf` / PR #14
This revision: outcome reporting on `cursor/bt-intake-desk-notify-e9a8` (PR #16), stacked on the send-repair artifact `a2f534bb…`.
Installed host worker (Codex-observed): send-repair `a2f534bb…`; backup `20260912T173409Z-83e59a2e`. This notify artifact is not live until Codex deploys it.

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
| Runtime Gmail RESULT/CTRL/send | **PASS** (runtime) | Action 2 provider `1a096afc3df71472`; Sent 1 / Daniel 1 |
| Exact approved internal send | **PASS** (runtime) | Existing approval reused once; no further send authorized |
| Backend recipient receipt | **FAIL / not recorded** | Inbox copy observed; status remains `sent_verified` |
| Outcome reporting deploy | **BLOCKED** | this VM; Codex deploys PR #16 artifact |
| Real iPhone / Mac-off | **PENDING** | do not claim |
| Live worker deploy | **BLOCKED** | no SSH key / no gcloud on this VM |

**Unit:** `PYTHONPATH=src python3 -m unittest discover -s tests` → 203 passed, 1 skipped.

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
