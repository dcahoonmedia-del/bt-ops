# Phase C — Case Manager + Daniel review

**Overall: PASS.** Phase B cloud intake is unchanged. A marked internal receipt became a durable case, isolated Codex drafted from trusted B&T rules, Daniel's iPhone review mail landed in Inbox, approval was recorded without sending, a same-thread reply superseded that approval, and a VM reboot kept the case, drafts, and decisions.

Live case: `BTC-contactus-1a093c210338340c` on contactus thread `1a093c210338340c`. Internal test only. Not a customer queue.

## Scorecard

| Gate | Result |
| --- | --- |
| Receipt becomes a case | PASS |
| Customer content stays external/untrusted | PASS |
| B&T rules stay trusted and separate | PASS |
| Codex bounded draft | PASS |
| Daniel can review on iPhone | PASS |
| Decisions persist | PASS |
| Approval does not send | PASS |
| New inbound invalidates old approval | PASS |
| VM restart preserves cases/drafts/decisions | PASS |

## Evidence

- Event-driven capture of `BT-INTAKE-PROOF-CASEMGR-NEW-E9A8` as receipt `1a093c210338340c`. Labels stayed `UNREAD` / `INBOX`.
- Phase B dispatch: `lead_email_ingest` / `external_untrusted`, `empty_user_input=true`, `content_in_user_input=false`, `authorization=false`.
- Case Manager draft: rules in developer context only (`rules_in_user_input=false`). Proposed reply starts with `DRAFT - NOT SENT`. Recurring PestGuard before one-time. No Fieldwork access; missing match flagged for Daniel.
- Review mail to `daniel@` (Cc `contactus@`), now in Inbox/UNREAD: subjects `... v1` and `... v5`. Open on iPhone Mail. Approval still does not send.
- Approve marker recorded with `send_triggered=0` and `next_action=none_do_not_send`. No customer outbound.
- Same-thread reply `1a093c4e969998bb` classified `reply`. Event `inbound_reopened` with `approval_superseded=true`. Draft v1 status `superseded`.
- VM `sudo reboot` at ~04:01:45Z. Receiver active again at 04:02Z with `gce_metadata`. Case still `awaiting_review` / draft v5 / 9 decision rows / `send_triggered` max 0.

## Baseline used

Four Daniel files only. The second identical handoff upload was a send error; the fourth file is `BT-ChatGPT-Lead-Management-Proposed-Architecture.md` (2026-09-11). Conflicts are in `knowledge/CONFLICTS.md`. Phase C (2026-09-12) wins over architecture send / Fieldwork / Auditor / scheduling.

## Notes (not silent choices)

- Early host loops re-applied the older inbound after the reply and minted extra draft versions 3–5. Fixed: each inbound message ID is applied once; an existing nonce is reused.
- The same approve receipt was written multiple times before idempotency. Later loops skip it (`already_recorded`). All rows stay `send_triggered=0`.
- The reply body quoted the original `CASEMGR-NEW` marker, so stored `test_marker` is NEW while Gmail classification is `reply`. Same-thread reopen still held.
- Phase B `CLOUD-*` receipts stay on disk and are no longer treated as Case Manager work.

Stop here. Do not process real customer mail. Do not send. Do not add Fieldwork, LSA, CTM, an Auditor, or a public review URL.
