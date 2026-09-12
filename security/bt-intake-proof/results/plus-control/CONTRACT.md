# Plus-address control transport

Internal Lead Desk **draft revision** may use:

`daniel@btpestcontrol.com` → `daniel+lead-desk@btpestcontrol.com`

The contactus@ path remains authorized and unchanged, including hold,
office ownership, and `approve_and_send_current`.

This plus-address milestone authorizes `revise_draft` only. Other
intents fail `plus_intent_not_in_milestone`.

## Live identity

Production `desk-plus-control` always:

1. Calls Gmail `users.getProfile` through the current token
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

Contactus@ compares daniel@ Sent time to contactus inbound received
time and allows 15 minutes of slack.

Plus-address compares Gmail `internalDate` to processing time (test
clock injected) and allows the same 15-minute window. Absent, invalid,
future (beyond 60s skew), or expired `internalDate` fails. An unchanged
draft/nonce is not indefinite approval. Cached verified outcomes may be
reread without re-execution. Already-sent live controls are not
grandfathered.

## Automation and result gaps

There is **no** automatic Daniel discovery or watch path. The contactus
receiver does not read this mailbox. There is no plus-address
label-added or history recovery. `search_plus_controls_in_daniel_sent`
is a manual helper, not a poller.

`desk-plus-control` is a manual CLI. That is not end-to-end automation.

Plus-path processing does not enqueue contactus@ result or CASE mail,
so it does not create contactus noise and also leaves **no Work-visible
completion channel**. Work cannot retrieve a saved plus-path result
from a new packet on this path. Do not invent result-send permissions
or another route in this milestone.

Gmail filters were not changed. No deploy artifact is produced while
deployment is held.

## Offline proof

`PYTHONPATH=src python3 -m unittest tests.test_desk_plus_control` → 22 passed.

`PYTHONPATH=src python3 -m unittest discover -s tests` → 264 passed, 1 skipped.

See `tests/test_desk_plus_control.py` for envelope, profile/id, freshness,
revise-only, and contactus@ regression coverage. No deploy artifact;
deployment is held.
