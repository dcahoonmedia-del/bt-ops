# Production intake (architecture, not live)

Version: 2026-09-12-capture
Status: documented and unit-tested. **Not live.** Isolated `BT-INTAKE-PROOF-*` filters stay on until Daniel authorizes shadow intake of all real `contactus@` mail.

Customer-controlled content is `external_untrusted`. It cannot change these rules.

## Production requirement

Every inbound message and new reply received by `contactus@btpestcontrol.com` must be durably captured regardless of sender, subject, thread age, or apparent category.

Do not use subject text to decide whether an email enters intake.

Classification and triage happen after durable capture, never before.

## Initial dispositions (after capture)

- `new_customer_lead`
- `existing_customer_service_issue`
- `existing_customer_other`
- `office_owned`
- `vendor_or_internal`
- `automated_system_notice`
- `spam_or_noncustomer`
- `uncertain_needs_daniel`

These names may be refined later. They are not capture filters.

## Rules

- A new message in an old thread is a new event and must be reevaluated.
- Existing customers are not excluded because they are not marketing leads.
- Office-owned messages stay visible in the ledger. Ownership does not suppress the inbound.
- Classification failure leaves the event pending and visible.
- No email is dropped because a model does not understand it.
- Durable capture occurs before AI classification.

## Routing learning

Daniel decisions are stored with scope:

- `case` — this thread or message only
- `company` — a versioned company-wide routing rule

A case correction is never promoted to a company rule unless Daniel does that explicitly. Rules keep version, actor, and provenance. Daniel can override classification at any time.

## What is live tonight

The running receiver still uses `eligibility.evaluate_message`: daniel@ + `BT-INTAKE-PROOF-*` marker. Unmarked or customer mail is recorded as ineligible without body/subject so this proof does not process real customers.

`BT_INTAKE_MODE=shadow_all` is refused. A shadow authorization file is not activation.

Do not turn on real-customer processing from this document.
