# Plus-address private-control loop

Internal Lead Desk **draft revision** may use:

`daniel@btpestcontrol.com` → `daniel+lead-desk@btpestcontrol.com`

After a later host activation, Cloud Work reads one combined result at:

`daniel+lead-desk-results@btpestcontrol.com`

The contactus@ path remains authorized and unchanged, including hold,
office ownership, and `approve_and_send_current`. Plus-path traffic
never uses contactus@ for control or result mail.

This plus-address milestone authorizes `revise_draft` only. Other
intents fail `plus_intent_not_in_milestone`.

## Live identity

Production fetch always:

1. Calls Gmail `users.getProfile` through the current Daniel readonly token
2. Requires the profile email to be exactly `daniel@btpestcontrol.com`
3. Fetches the requested message
4. Requires the returned Gmail id to equal the requested id

Token-file `email` metadata is not identity. Caller-supplied evidence
and `fixture_daniel_plus_control` are test injection only.

## Envelope

Every From/To/Cc/Bcc occurrence on the raw provider mail is checked.
From must be only daniel@. To must be only `daniel+lead-desk@`.
Cc and Bcc must add no other recipients.

## Freshness

Plus-address compares Gmail `internalDate` to processing time (test
clock injected) and allows 15 minutes. Absent, invalid, future
(beyond 60s skew), or expired `internalDate` fails. Cached verified
outcomes may be reread. Already-sent live controls are not
grandfathered. Never process `1a0979e37a0b0a94`.

## Automatic discovery

A small systemd **timer/oneshot**, installed **disabled**, polls Daniel
Gmail history with `messageAdded` and `labelAdded`. It uses the
existing Daniel readonly credential only. It does not add Pub/Sub and
does not change contactus `users.watch` / `watch_cursors`.

Discovery is limited to the existing `B&T Lead Desk/Control` label plus
the exact sender/recipient subset. Search is `in:sent` plus that label;
archive/filtering must not hide controls. Results mailbox/label and
`BT-INTAKE-PROOF-PLUS-RESULT-E9A8` are excluded to prevent loops.

History is paginated. The Daniel cursor key is
`daniel@btpestcontrol.com/plus-control`. Repeated or reordered events
are deduped in `plus_control_seen`. After history expiration, a bounded
SENT+Control reconcile (25 messages) runs. Unrelated bodies are not
stored.

Each candidate is independently re-checked (raw envelope, live profile,
message id, freshness, case/version/body/inbound, single-use) before
execution.

## Atomic save and one result

A successful revise consumes the nonce and writes **one** durable
`plus_combined` result intent in the same SQLite transaction. Retries
do not save twice. The result combines the spoken outcome, the updated
draft, and the fresh backend packet binding. It is not a contactus
result plus a separate CASE email.

If the plus-result sender is not configured, processing is blocked and
the decision is not consumed.

## Result sender

From `daniel@btpestcontrol.com`, sole To
`daniel+lead-desk-results@btpestcontrol.com`, no Cc/Bcc, backend
content only. Credential reference:
`BT_DANIEL_PLUS_RESULT_SEND_TOKEN` /
`secrets/daniel_plus_result_send_token.json`.

That file is not created by this assignment. The readonly token is not
widened. contactus send/readonly tokens are not fallbacks.

Gmail `users.messages.send` is not exactly-once from the client view.
Unknown or timeout outcomes stay `unknown` until provider SENT records
are reconciled. This path does not claim exactly-once delivery.

## Preflight

`python3 -m bt_intake_proof desk-plus-preflight` reports the live
Daniel profile, required labels where listable, filter accessibility
without requesting `gmail.settings`, discovery readiness, sender
readiness, and activation blockers. It does not recreate or change
Daniel's filters, routing, labels, or permissions.

## Offline proof

`PYTHONPATH=src python3 -m unittest tests.test_desk_plus_control tests.test_desk_plus_loop` → 39 passed.

`PYTHONPATH=src python3 -m unittest discover -s tests` → 281 passed, 1 skipped.

See `tests/test_desk_plus_loop.py` for history, label-added, expired
recovery, stale controls, envelope, intents, concurrency, rollback,
crash recovery, uncertain send, result loops, missing credentials,
and zero contactus traffic.

## What this assignment does not do

- No live mail send
- No GCE deploy
- No new OAuth grant
- No Fieldwork / LSA / CTM / scheduling / customer send / Grok cutover
