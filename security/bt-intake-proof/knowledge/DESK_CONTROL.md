# Lead Desk control

Version: 2026-09-12-roundtrip
Production path: Daniel speaks naturally to ChatGPT → ChatGPT interprets intent → ChatGPT sends a private Gmail control message from daniel@ → backend authenticates origin with Gmail-fetched Authentication-Results → validates exact case/version/nonce/hash/freshness → `submit_desk_action` → durable result/case packets to daniel@ → desk-queued bounded execute + independent verify.

Daniel does not need case IDs, draft numbers, hashes, nonces, approval codes, or a magic phrase. ChatGPT holds the conversation. The Python backend does not model his speech.

iPhone transport is Gmail, not custom MCP. See `CHATGPT_LEAD_DESK.md`.

`normalize_desk_intent` is a temporary fallback only. Do not grow its phrase lists.

## Structured action

ChatGPT submits one of:

- `approve_and_send_current`
- `approve_draft_only`
- `revise_draft`
- `hold`
- `office_owned`
- `no_response_needed`
- `request_information`
- `conditional_instruction`
- `ambiguous_needs_confirmation`

Optional fields: `owner`, `note`, `reassign_to_daniel`. Unknown or missing intent is rejected. If the intent is materially ambiguous, ChatGPT asks one short natural question. Do not require a machine phrase from Daniel.

The isolated Gmail review packets may still use CASE=/DRAFT= markers. That is not the intended production conversational UX.

## Send still binds

Any send still binds to the exact current case, draft version, recipient, channel, payload, and latest inbound. A newer inbound, changed draft, changed recipient, hold, office ownership, or stale displayed context blocks execution. ChatGPT meaning "send" does not bypass Phase E.

`submit_desk_action` authorizes only. The Gmail bridge may queue a desk-roundtrip send after a valid `approve_and_send_current`. The host executes only `queued_by=desk_control` actions. Phase E leftovers stay queued and are not executed. Ambiguous/unknown sends must reconcile before any retry.

Control origin is fail-closed. From: and PACKET_HASH are not identity. Domain DKIM for `@btpestcontrol.com` is not Daniel's mailbox. Mailbox-bound SPF/DKIM on the first Gmail-fetched `Authentication-Results` (`mx.google.com`) is a prerequisite, not authorization. Authorization requires an exact authenticated daniel@ Sent match (recipient, canonical control payload, timing, and Message-ID). Quoted `>` copies do not authorize. Pending replay cannot skip that proof. This is not a full-identity PASS. See `desk_origin.py`, `desk_sent_proof.py`, and `results/DESK_ORIGIN_EVIDENCE.md`.

Control mail is never a customer case, never Codex `external_untrusted`, and never shown to a customer. Result/case/queue/health packets inbound to contactus are loop-guarded and do not become cases.

## Office ownership

Brenda and Ally are office staff. Office-owned cases stay with the office. Do not silently take a case away from them or create duplicate AI outreach. Transfer only when Daniel explicitly reassigns.

## Live tonight

Internal conversational control round trip is implemented in code: origin auth, durable result/case delivery, desk-only execute + independent verify. Real-phone PASS stays pending until Daniel runs the iPhone script with his Mac off. The isolated internal send still needs a fresh exact version-bound approval; this milestone is not that approval and does not reuse Phase E's consumed row.
