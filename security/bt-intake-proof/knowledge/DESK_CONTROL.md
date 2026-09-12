# Natural-language Lead Desk control

Version: 2026-09-12-intent
Daniel operates the desk by talking, often iPhone dictation. He does not need case IDs, draft numbers, hashes, nonces, approval codes, or a magic phrase such as the literal words `send it`.

The conversational model infers intent from the full current conversation, the draft just shown, the question just asked, Daniel's complete newest utterance (including mid-sentence reversals), and current ownership/holds.

The backend authorizes execution. The model cannot bypass Phase E.

## Internal intents

- `approve_and_send_current`
- `approve_draft_only`
- `revise_draft`
- `hold`
- `office_owned`
- `no_response_needed`
- `request_information`
- `conditional_instruction`
- `ambiguous_needs_confirmation`

If the intent is materially ambiguous, ask one short natural question. Do not require a machine phrase.

Later contradictory language in the same dictated turn wins. "Send that - actually wait, make it shorter first" is revise, not send. "If she confirms, send it" is conditional, not send. "Don't send that" is no send even though it contains `send`.

## Send still binds

Any inferred send binds to the exact current case, draft version, recipient, channel, payload, and latest inbound. A newer inbound, changed draft, changed recipient, hold, office ownership, or stale displayed context blocks execution.

## Office ownership

Brenda and Ally are office staff. "Leave this with Brenda", "Ally is handling this", and "The office has this" are office-owned, no customer send. "Brenda or Ally" asks which one if that matters. Do not silently take a case away from them or create duplicate AI outreach. Transfer only when Daniel explicitly reassigns.

## Live tonight

This is the control contract and unit tests. Isolated Gmail review packets may still use CASE-APPROVE markers. Conversational send is not a new live customer-send path.
