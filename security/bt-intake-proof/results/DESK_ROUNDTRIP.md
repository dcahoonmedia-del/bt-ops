# Desk round-trip scorecard

Reviewed baseline: `378ffcf` / PR #14
This revision: `aa23690` on `cursor/bt-intake-roundtrip-e9a8` (do not treat as live).
Deployed revision: **UNKNOWN** (not read). Host `35.243.167.73` answered SSH this session; both recorded usernames returned `Permission denied (publickey)`. No command was run on the host.

Isolation: BT-INTAKE-PROOF on. Real-customer sends OFF. Broad/shadow capture OFF.
This milestone is **not** an approval row and does **not** reuse Phase E action 1 / `BT-PHASE-E-SEND-E9A8-C4F1`.

Evidence labels: **unit** / **fixture** / **runtime** / **real-phone**.

## Gates

| Gate | Result | Evidence |
| --- | --- | --- |
| Mixed DKIM/SPF method binding | **PASS** (unit) | Codex header now `accepted=False`. `tests/test_desk_origin.py` |
| Reversed / multiple DKIM+SPF | **PASS** (unit) | same |
| Lookalike domains / authserv | **PASS** (unit) | same |
| Malformed / duplicate AR | **PASS** (unit) | first AR only; ARC-AR ignored |
| Domain DKIM ≠ Daniel mailbox | **PASS** (unit + runtime) | domain DKIM does not authorize; Phase E inbound `1a094071c6be5dab` shows `header.i=@btpestcontrol.com` for contactus@ + `smtp.mailfrom=contactus@`. `results/DESK_ORIGIN_EVIDENCE.md` |
| Mailbox-bound SPF/DKIM authorize | **PASS** (unit) | `identity_level=mailbox_bound_provider_result`, `full_identity_pass=False` |
| Full identity PASS | **FAIL / not claimed** | domain or mailbox AR is not human identity; no daniel@ Sent cross-check on this agent |
| Quoted CTRL / From-only | **PASS** (unit) | existing bridge tests |
| Sequential replay / reopen | **PASS** (unit) | `test_sequential_replay_and_reopen` — not concurrency |
| Simultaneous nonce consume (2 connections) | **PASS** (unit) | `test_simultaneous_nonce_consume_two_connections` |
| Simultaneous execute + result delivery | **PASS** (unit) | `test_simultaneous_execute_and_result_delivery` |
| Crash after provider accept, before persist | **PASS** (unit) | send reconcile + outbox reconcile; no duplicate; no silent `sending`/`locked` stick |
| Hold / Brenda / Ally / no-response / revise / stale inbound | **PASS** (unit) | existing |
| Result + desk execute/verify (memory) | **PASS** (unit/fixture) | |
| Runtime Gmail result / CTRL / round-trip send | **PENDING** | no live delivery this revision |
| Narrowly approved internal send | **PENDING** | not requested while deploy/security were open |
| Real iPhone / Mac-off | **PENDING** | |
| Live deploy | **BLOCKED** | see handoff below |

**Unit:** `PYTHONPATH=src python3 -m unittest discover -s tests` → 144 passed, 1 skipped.

## Deployment handoff (this agent cannot deploy)

Failed read-only access checks this session:

- `security/bt-intake-proof/secrets/` absent (gitignored; no `bt-intake-cloud` key file)
- `~/.ssh` has `known_hosts` only (written by this session's SSH probe). No private keys.
- `gcloud` not on PATH; `~/.config/gcloud` absent
- GCE metadata not available (`metadata.google.internal` did not resolve)
- SSH to recorded host: `Permission denied (publickey)` as `btadmin` and as `bt-intake-cloud-e9a8`
- Host TCP/SSH at `35.243.167.73` **did** answer (key rejected). That is not a revision read.

Previously used route (from Phase B/E transcripts and `scripts/install_cloud_host.sh`):

- Project: `bt-intake-proof`
- VM: `bt-intake-cloud`
- Zone: `us-east1-c`
- Last recorded IP: `35.243.167.73` (re-verified reachable; identity of the process **unknown**)
- SSH users documented: `btadmin` (console key comment `bt-intake-cloud-e9a8`) and `bt-intake-cloud-e9a8`
- Key file previously: `security/bt-intake-proof/secrets/bt-intake-cloud` (do not paste)
- Install prefix: `/opt/bt-intake-proof`
- State: `/var/lib/bt-intake-proof/receipts.sqlite`
- Unit: `bt-intake-receiver`

Bounded deploy (after checkout of the reviewed revision on the VM, as root):

```
sudo bash /path/to/checkout/security/bt-intake-proof/scripts/install_cloud_host.sh
sudo systemctl status bt-intake-receiver --no-pager
```

The install script rsyncs code and restarts the unit. It does not create credentials.

Read the deployed revision before asserting it:

```
sudo git -C /opt/bt-intake-proof rev-parse HEAD
# or if that tree has no .git:
python3 -c 'import bt_intake_proof.desk_origin as m; print(m.__file__)'
```

Rollback: rsync the previous known-good tree (PR #14 / `378ffcf`) and rerun the same install script.

Codex on Daniel's Mac: no `~/.ssh`, no `gcloud`. Do not assume Codex can deploy.

## Next smallest unblock

1. Restore the existing SSH private key onto an already-authorized path (this agent or an operator that already has it). Do not mint a new key.
2. Read `/opt/bt-intake-proof` revision, then install this branch.
3. After deploy, collect runtime Gmail RESULT records. Only then consider the exact send approval and the phone test.

## Exact send packet

Prepared in the previous revision. Not sent. Do not ask Daniel to approve it until deploy and origin gates are live.
