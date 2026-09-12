# Lead Desk control

Version: 2026-09-12-gmail-bridge
Production path: Daniel speaks naturally to ChatGPT → ChatGPT interprets intent → ChatGPT sends a private Gmail control message from daniel@ → backend validates exact case/version/nonce/hash/freshness → `submit_desk_action`.

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

`submit_desk_action` authorizes only. The Gmail bridge may queue a Phase E send after a valid `approve_and_send_current`. It does not call `execute_action`.

Control mail must come from verified `daniel@btpestcontrol.com`. It is never a customer case, never Codex `external_untrusted`, and never shown to a customer. Copied control syntax from anyone else authorizes nothing.

## Office ownership

Brenda and Ally are office staff. Office-owned cases stay with the office. Do not silently take a case away from them or create duplicate AI outreach. Transfer only when Daniel explicitly reassigns.

## Live tonight

This is the Gmail control-bridge contract and unit tests. Ready for a real ChatGPT iPhone test on internal cases only. Conversational send is not a new live customer-send path.
