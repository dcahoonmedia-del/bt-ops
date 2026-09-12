# Isolated proof-console review (synthetic)

Generated from `LeadDesk` over a throwaway SQLite file. Not live mail.
Interpretation of spoken requests is simulated in OPERATOR_WALKTHROUGH.md.

Pack ok: True

- new_inquiry_reviewable_draft: **PASS** — Conservative draft has no price or appointment. Invented contrast stayed reviewable and was not sent.
- existing_customer_service_issue_not_discarded: **PASS** — Existing-service inbound stayed visible and received a reviewable draft.
- office_ownership_and_hold_block_send: **PASS** — Hold, Brenda, and Ally each blocked approve-and-send and left no queued action. Console names the owner or hold instead of waiting on Daniel.
- new_inbound_or_changed_draft_invalidates_authorization: **PASS** — New inbound superseded the old approval. Version 1 can no longer authorize.
- repeat_decision_and_restart_no_duplicate_action: **PASS** — Same control/decision ids stayed skipped after restart. No send action was created.

## Cases

- `BTC-contactus-thr-office-exist` owner=Daniel Cahoon stage=approved draft=True attention=Approved as recorded state. No customer send for this case type.
- `BTC-contactus-thr-office-new` owner=Daniel Cahoon stage=awaiting_review draft=True attention=Draft is waiting on Daniel.
- `BTC-contactus-thr-office-repeat` owner=office stage=awaiting_review draft=True attention=Held. Nothing will send.
  hold/office: {'kind': 'hold', 'source': 'desk_control'}
- `BTC-contactus-thr-office-stale` owner=Daniel Cahoon stage=awaiting_review draft=True attention=Draft is waiting on Daniel.
- `BTC-contactus-thr-office-ally` owner=ally stage=awaiting_review draft=True attention=Ally owns this. Do not send a competing reply.
  hold/office: {'kind': 'office_owned', 'owner': 'ally', 'source': 'desk_control'}
- `BTC-contactus-thr-office-brenda` owner=brenda stage=awaiting_review draft=True attention=Brenda owns this. Do not send a competing reply.
  hold/office: {'kind': 'office_owned', 'owner': 'brenda', 'source': 'desk_control'}
- `BTC-contactus-thr-office-hold` owner=office stage=awaiting_review draft=True attention=Held. Nothing will send.
  hold/office: {'kind': 'hold', 'source': 'desk_control'}

## Scenario table

| Scenario | Result |
| --- | --- |
| new_inquiry_reviewable_draft | PASS |
| existing_customer_service_issue_not_discarded | PASS |
| office_ownership_and_hold_block_send | PASS |
| new_inbound_or_changed_draft_invalidates_authorization | PASS |
| repeat_decision_and_restart_no_duplicate_action | PASS |

## Unsupported / blocked

- `live_unmarked_customer_mail` **BLOCKED**: Live receiver still uses BT-INTAKE-PROOF-* + daniel@. Unmarked real customer service mail is ineligible and stripped. This pack does not enable shadow intake.
- `generic_office_owner_without_name` **UNSUPPORTED**: Existing office_owned intent requires Brenda or Ally. Generic hold covers 'leave it with the office'. No new ownership policy was added.
- `backend_price_phrase_parser` **UNSUPPORTED**: Backend does not parse Codex drafts for invented prices. This pack uses a local reviewer check and conservative fixtures. ChatGPT still interprets; backend still binds.
- `codex_live_draft_model` **BLOCKED**: host_case_draft / live Codex drafting was not invoked. Drafts here are synthetic local fixtures.
- `live_voice_or_phone` **BLOCKED**: No live voice or Mac-off proof. Operator walkthrough is simulated interpretation only.
