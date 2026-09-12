# CASEMGR initial-review delivery

Isolation on. Customer sends OFF. Broad capture OFF. No Fieldwork writes.
Do not resend `BT-INTAKE-PROOF-CASEMGR-PHONE-7C92`. Do not touch
`BTC-contactus-1a096d60643b3b1a`. Actions 1 and 2 stay consumed.

## What changed

After a **successful normal** CASEMGR draft, `process_cases` records a durable
`case_initial_reviews` intent in the same SQLite transaction as `save_draft`,
then enqueues one current `BT-INTAKE-PROOF-DESK-CASE-E9A8` packet on the
existing `desk_result_outbox` (`kind=case_initial`, `control_gmail_id=<inbound>`).
`finish_desk_roundtrip` sends it the same way as control CASE/RESULT mail.

Phase E and desk-roundtrip drafts are unchanged (no initial CASE packet).
Control/result consolidation and binding gates are unchanged. A later control
CASE supersedes a still-pending initial packet for that inbound.

## Duplicate / crash / stale

| Event | Behavior |
| --- | --- |
| Repeat `process_cases` / restart | `INSERT OR IGNORE`; no second row |
| Crash after draft+intent, before outbox | `recover_pending_initial_reviews` enqueues current matching version |
| Failed model draft | no intent, no packet |
| `sent` / `unknown` / `blocked` | not reset to pending |
| Historical / completed / Brenda-owned without an intent | not scanned, not queued |
| Intent version ≠ current draft, or inbound changed | mark `stale`; do not enqueue old text |

## Live inquiry `1a096ffa404426f1`

Forward path does **not** mass-backfill already-drafted cases. If that inbound
already has a draft from the old host, use the explicit recovery command after
deploy review. Do not run it from deploy. Do not rerun the model.

See `RECOVERY.md`.

## Immutable release

- SHA256 `2627c2b3e4c9dd3f422ad159b79d5d77199f4ab49bb2c61187ec256801ff0855`
- Source `e670b3697279ec2b9c32d5b1e6907f0b963fda82`
- Artifact `cecc68c99a41dfb297a3e1cccd8edb7bf3736075`
- Tree `c29f4880d8151cbf7332e8c178a8a7b35b2a90de540cf1d83c4657f40a0f1045`
- RAW: https://raw.githubusercontent.com/dcahoonmedia-del/bt-ops/cecc68c99a41dfb297a3e1cccd8edb7bf3736075/security/bt-intake-proof/results/desk-roundtrip-release/bt-intake-desk-roundtrip.tar.gz

## Offline proof

`PYTHONPATH=src python3 -m unittest tests.test_casemgr_initial_review tests.test_desk_bridge tests.test_desk_control_codec`

`PYTHONPATH=src python3 -m unittest discover -s tests`

## Live host trace

**BLOCKED** from this VM (no gcloud / SSH key). Do not claim a diagnosis of
the live SQLite row for `1a096ffa404426f1`.
