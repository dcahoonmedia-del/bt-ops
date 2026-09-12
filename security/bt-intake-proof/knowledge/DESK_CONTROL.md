# Lead Desk control

Version: 2026-09-12-action
Production path: Daniel speaks naturally to ChatGPT → ChatGPT interprets intent → backend receives a small structured action → backend validates exact case/version/payload/freshness and executes narrowly.

Daniel does not need case IDs, draft numbers, hashes, nonces, approval codes, or a magic phrase. ChatGPT holds the conversation. The Python backend does not model his speech.

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

`submit_desk_action` authorizes only. It does not send. A later execute still needs a stored Phase E action id.

## Office ownership

Brenda and Ally are office staff. Office-owned cases stay with the office. Do not silently take a case away from them or create duplicate AI outreach. Transfer only when Daniel explicitly reassigns.

## Live tonight

This is the control contract and unit tests. Conversational send is not a new live customer-send path.
