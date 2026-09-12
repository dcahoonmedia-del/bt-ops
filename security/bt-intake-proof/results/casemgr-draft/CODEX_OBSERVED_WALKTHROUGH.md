# Codex-observed CASEMGR draft walkthrough

This is live host evidence. It is not a unit test and not a phone / Mac-off PASS.
Do not touch or replay case `BTC-contactus-1a096d60643b3b1a`.
Do not recover `--execute`. Do not repeat action 2 `--verify-recipient`.

## Deploy

- Artifact SHA256 `3eb86d3e961c6a3cd8d8c5ac700e2ba727a1f12bf96e35e75d9adbca26458e6e`
- Backup `20260912T181443Z-671f195c`
- Deploy PASS, health PASS
- Isolated harness still on. Customer sends OFF. Broad capture OFF.

## Inquiry

Daniel authorized the internal inquiry / revise / Brenda walkthrough, then
renewed authorization for the corrected short revision.

| Item | Value |
| --- | --- |
| Daniel Sent | `1a096d5f97109b99` |
| contactus receipt / thread | `1a096d60643b3b1a` |
| Eligible | true |
| Case | `BTC-contactus-1a096d60643b3b1a` |

## Actual model draft (not a fixture)

- Host model completed
- Isolation thread `01a096d6-63c5-7332-95a8-3a9a0bf649e8`
- Stored draft v1
- `case-draft.json` `turn.final_response` matched the stored draft
- Wire `empty_user_input=true`, `content_in_user_input=false`
- Draft asked for name / contact / address and ant details
- No price or appointment

This VM did not execute `host_case_draft`. Do not treat local fixtures as this PASS.

## Revision / hold

| Item | Value |
| --- | --- |
| First long revise (failed) | Daniel `1a096d7c880b70fb` / contactus `1a096d7f837799a5` |
| Failure | `sent_mailbox_evidence_mismatched` |
| Cause | Sent NOTE was one long line; delivered body hard-wrapped NOTE after `ants.` and `office`; `_FIELD` kept the first line only |
| Second revise (failed) | 63-character `PACKET_HASH` transcription error; `packet_hash_invalid` (correct reject) |
| Final short revise | Daniel control `1a096dc09f3fb922` saved v2 `DRAFT - NOT SENT` plus `Please share your service address and callback number.` |
| Brenda control | Daniel Sent `1a096dca5d664832` applied |

`LeadDesk.get_case` after Brenda:

- `owner=brenda`
- `draft_version=2`
- `waiting_on_daniel=false`
- `attention=Brenda owns this. Do not send a competing reply.`

## Send isolation

- Case send action count `0`
- Actions 1 and 2 remain `recipient_receipt_verified`, consumed `1`

Desktop-mediated live execution. Not phone / Mac-off proof.
