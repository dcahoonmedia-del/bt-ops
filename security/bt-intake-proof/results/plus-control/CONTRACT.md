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

Discovery is limited to the existing `B&T Lead Desk/Control` label
(resolved by **name** to the current ID) plus the exact sender/recipient
subset. Recovery search uses supported `q` syntax (`in:sent to:… after:…`)
and API `labelIds`. Opaque `Label_…` IDs are never placed in `q`.
Results mailbox/label and `BT-INTAKE-PROOF-PLUS-RESULT-E9A8` are
excluded to prevent loops.

History is paginated. Every recoverable history/recovery id is
checkpointed **before** the cursor advances. The Daniel cursor key is
`daniel@btpestcontrol.com/plus-control`. Repeated or reordered events
are deduped in `plus_control_seen`. After history expiration, recovery
paginates over the 15-minute freshness window. Ordinary mail without
Control stays `awaiting_label` and is never raw-fetched. The Control
subset is revalidated from metadata before every execution.

Processing leases expire after two minutes so a crash cannot leave a
row `processing` forever. Committed outcomes replay without a second
consume.

## Atomic save and one result

Schema setup is initialized **outside** the revise transaction
(`execute()`, never `executescript()`). A successful revise consumes
the nonce and writes **one** durable `plus_combined` result intent in
the same SQLite transaction. A failure inside result persistence rolls
back draft, nonce, and result together. Retries do not save twice. The
result combines the spoken outcome, the updated draft, and the fresh
backend packet binding. It is not a contactus result plus a separate
CASE email.

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

An RFC `Message-ID` is persisted before send and included in MIME.
Gmail `users.messages.send` is not exactly-once from the client view.
Unknown, timeout, empty, delayed, mismatched, or duplicate SENT
lookups stay `unknown` and are never blindly retried. Reconciliation
uses Daniel **readonly** SENT, verifies live account, sole results
recipient, payload digest, and the durable RFC id. Caller-supplied
subject/marker lists are not authoritative. Blocked (known-unsent)
rows may return to pending only after live sender identity is proven
usable. This path does not claim exactly-once delivery.

Sender readiness refreshes the send credential and proves email plus
effective scopes through `tokeninfo`. Token-file metadata is not live
proof. Known-unusable credentials fail closed.

## Preflight

`python3 -m bt_intake_proof desk-plus-preflight` reports the live
Daniel profile, required labels where listable, filter accessibility
without requesting `gmail.settings`, discovery readiness, sender
readiness, and activation blockers. READY requires both Control and
Results labels by name and a successful label list. It does not
recreate or change Daniel's filters, routing, labels, or permissions.

## Offline proof

Focused plus-loop + plus-control + deploy unit tests, then the full
`unittest discover -s tests` suite. Counts are recorded on the
regenerated release after this correction. GCE and iPhone proof remain
unrun.

See `tests/test_desk_plus_loop.py` for the six review regressions:
implicit-commit rollback, lost-discovery checkpoint, lease reclaim,
authoritative SENT reconcile, private-subset revalidation, and live
sender/preflight fail-closed. Deploy installs the plus timer
**disabled**.

## What this assignment does not do

- No live mail send
- No GCE deploy
- No new OAuth grant
- No Fieldwork / LSA / CTM / scheduling / customer send / Grok cutover
