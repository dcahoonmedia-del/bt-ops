# Operator walkthrough (simulated interpretation)

This is a **simulation**. ChatGPT is not running. No phone or Mac-off proof is claimed.
The backend still does not parse Daniel's speech. Exact bound operations already exist.

Daniel talks naturally. ChatGPT chooses one structured intent and sends a
control email from daniel@ to contactus@. Keep technical fields (case id,
nonce, hash, draft version) out of spoken summaries. That is not a promise
that the transport is invisible: the iPhone Mail or Gmail app may still show
a sent-mail confirmation. Do not claim we can suppress that UI. The pack
below applies the same bound operation on a throwaway SQLite file.

## 1. New inquiry

Spoken: "There's a new email about ants in Jacksonville. Draft something I can review."

**[SIMULATED ChatGPT interpretation]** → capture inbound, draft a conservative reply.
Exact backend path: eligible receipt → `CaseLayer.upsert_from_receipt` → `save_draft`.

What Daniel sees (proof console / review artifact):
- Case open, owner Daniel, stage `awaiting_review`
- Draft labeled `DRAFT - NOT SENT`
- No price and no appointment

No message is sent.

## 2. Existing customer service issue

Spoken: "This is an existing customer. Mice are back. Don't drop it just because it isn't a new lead."

**[SIMULATED ChatGPT interpretation]** → disposition `existing_customer_service_issue`.
Exact backend path: `captured_event` + `classify_after_capture(suggested=existing_customer_service_issue)` → same case/draft path.

What Daniel sees:
- Disposition stays visible, not suppressed
- Reviewable draft treats it as office follow-up, not a new sales pitch

Live unmarked customer mail remains **BLOCKED** by the isolated harness.

## 3. Hold this for Brenda

Spoken: "Hold this for Brenda."

**[SIMULATED ChatGPT interpretation]** → `INTENT=office_owned` `OWNER=brenda`
Exact bound control:

```
BT-INTAKE-PROOF-DESK-CTRL-E9A8
INTENT=office_owned
OWNER=brenda
```

Backend: `process_control_mail` → `office_owned`. A later `approve_and_send_current` is blocked (`office_owned`). No send action is queued.

Spoken: "Leave it with Ally." → `OWNER=ally` (same intent).

Spoken: "Just hold it. Don't send." → `INTENT=hold`. A later send is blocked (`hold`).

Existing policy: `office_owned` needs Brenda or Ally by name. Generic "the office has this" is `hold`, not a new owner type.

## 4. Revise the response

Spoken: "Revise the response. Make it shorter and just ask for a callback number."

**[SIMULATED ChatGPT interpretation]** → `INTENT=revise_draft` with the exact new wording encoded for mail.
Do not put a long draft on a raw `NOTE=` line. Generate `desk-control.txt` (`CTRL-ENC=v1`) so MIME wrap cannot change the text.

Backend saves a new draft version. The previous version cannot authorize a send.

## 5. Repeat / restart

Spoken: "Approve that draft only." then the same control arrives again after a process restart.

Exact backend path: `apply_decision(..., gmail_message_id=...)` returns `skipped=already_recorded`.
The same control `gmail_message_id` replays the stored result (`replayed=true`) and does not create a second hold event or send action.

## What this is not
- Not a live iPhone or voice PASS
- Not a new magic-phrase list in Python
- Not authorization to send any customer or internal message
