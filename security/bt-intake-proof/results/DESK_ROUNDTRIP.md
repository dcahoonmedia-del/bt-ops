# Desk round-trip scorecard

Reviewed baseline: `378ffcf` / PR #14
This revision: `b8b31b3` on `cursor/bt-intake-roundtrip-e9a8` (do not treat as live).
Deployed revision: **UNKNOWN** (not read). Existing-path SSH/gcloud blocker accepted; no further SSH retries this revision.

Isolation: BT-INTAKE-PROOF on. Real-customer sends OFF. Broad/shadow capture OFF.
This milestone is **not** an approval row and does **not** reuse Phase E action 1 / `BT-PHASE-E-SEND-E9A8-C4F1`.

Evidence labels: **unit** / **fixture** / **runtime** / **real-phone**.

## Gates

| Gate | Result | Evidence |
| --- | --- | --- |
| Mixed DKIM/SPF method binding | **PASS** (unit) | Codex header `accepted=False`. `tests/test_desk_origin.py` |
| Reversed / multiple / lookalike / malformed AR | **PASS** (unit) | same |
| Domain DKIM ≠ Daniel mailbox | **PASS** (unit + runtime) | `DESK_ORIGIN_EVIDENCE.md` |
| Mailbox-bound AR is not authorization | **PASS** (unit) | `authenticate_control_origin` stays `accepted=False`; `inspect_inbound` does not authorize from AR |
| Exact daniel@ Sent corroboration | **PASS** (fixture) | recipient + canonical payload + timing + Message-ID. `tests/test_desk_sent_proof.py` |
| Missing / ambiguous / mismatched Sent | **PASS** (fixture) | fail closed |
| Pending replay / boolean / legacy flag | **PASS** (unit) | `origin_already_authenticated` removed; legacy `origin_authenticated` does not authorize; versioned `desk-sent-v1` proof is bound to this control message |
| Full identity PASS | **FAIL / not claimed** | Sent match is mailbox corroboration, not human identity |
| Runtime daniel@ Sent lookup | **BLOCKED** | token not written; bootstrap staged only |
| Daniel readonly OAuth bootstrap | **STAGED** | `scripts/daniel_readonly_oauth.py`; consent not started |
| Sequential replay / reopen | **PASS** (unit) | not concurrency |
| Simultaneous nonce + execute/deliver | **PASS** (unit) | two connections/threads |
| Crash after accept, before persist | **PASS** (unit) | reconcile; no duplicate / silent stick |
| Hold / Brenda / Ally / revise / stale | **PASS** (unit) | existing |
| Result + desk execute/verify (memory) | **PASS** (unit/fixture) | |
| Runtime Gmail RESULT/CTRL/send | **PENDING** | |
| Exact approved internal send | **PENDING** | do not ask Daniel yet |
| Real iPhone / Mac-off | **PENDING** | |
| Live deploy | **BLOCKED** | existing-path blocker accepted; artifacts staged only |

**Unit:** `PYTHONPATH=src python3 -m unittest discover -s tests` → 160 passed, 1 skipped.

## Two remaining access dependencies

1. **Deploy SSH (accepted blocker).** Existing private key for `btadmin` / `bt-intake-cloud-e9a8` on `35.243.167.73` (project `bt-intake-proof`, VM `bt-intake-cloud`, zone `us-east1-c`). File previously `security/bt-intake-proof/secrets/bt-intake-cloud`. Do not mint a new key. Codex Mac: no `~/.ssh`, no `gcloud`.
2. **daniel@ Sent readonly (origin gate).** Daniel approved this separate `gmail.readonly` consent. Bootstrap is staged; Codex runs it on the host using the existing Desktop client. Token dest: `/opt/bt-intake-proof/secrets/daniel_gmail_readonly_token.json`. See `results/DANIEL_READONLY_OAUTH.md`. No send/modify. Contactus tokens stay untouched.

## Deployment handoff (staged, not executed)

Failed read-only checks (accepted; not retried this revision):

- `security/bt-intake-proof/secrets/` absent
- `~/.ssh` has `known_hosts` only; no private keys
- `gcloud` not on PATH; no ADC; no GCE metadata
- SSH to `35.243.167.73` previously `Permission denied (publickey)`

Install prefix `/opt/bt-intake-proof`. State `/var/lib/bt-intake-proof/receipts.sqlite`. Unit `bt-intake-receiver`.

Staged artifacts: `security/bt-intake-proof/results/deploy-stage/` (scripts + scorecard). Do not deploy while origin Sent proof is incomplete.

On the VM, as root, **before** install — record the actual live tree (do not assume PR #14):

```
sudo bash /path/to/checkout/security/bt-intake-proof/scripts/record_predeploy_revision.sh
sudo bash /path/to/checkout/security/bt-intake-proof/scripts/install_cloud_host.sh
sudo systemctl status bt-intake-receiver --no-pager
```

Rollback uses the recorded pre-deploy revision and snapshot, not an assumed SHA:

```
sudo bash /path/to/checkout/security/bt-intake-proof/scripts/rollback_to_predeploy.sh
```

Read the deployed revision before asserting it:

```
sudo cat /var/lib/bt-intake-proof/predeploy-revision.json
sudo git -C /opt/bt-intake-proof rev-parse HEAD
```

## Next smallest unblock

1. Codex transfers and runs `scripts/daniel_readonly_oauth.py` on the live host (see `results/DANIEL_READONLY_OAUTH.md`). Daniel only completes the Google read-only screen.
2. Do not deploy the new worker or restart the receiver until that token exists and this branch is reviewed.
3. Then runtime Gmail RESULT evidence. Only then the exact send approval and phone test.

## Exact send packet

Prepared earlier. Not sent. Do not ask Daniel to approve it until deploy and origin gates are live.
