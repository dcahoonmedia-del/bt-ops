# Plus-address draft-save test

Overall: **BLOCKED**

The backend contract is implemented and offline-proven. One internal
control was sent. The live host SQLite is not reachable from this VM,
so a live draft version was not saved.

## Required checks

| Check | Result |
| --- | --- |
| Cloud Work sent one control to `daniel+lead-desk@btpestcontrol.com` | **PASS** |
| Exactly one new draft version saved on the live case | **BLOCKED** |
| No customer message sent | **PASS** |
| No new `contactus@` traffic created by this test | **PASS** |
| Control stayed out of Daniel’s normal Inbox | **PASS** |

## Sent control

- Gmail id: `1a0979e37a0b0a94`
- Time: `2026-09-12T21:55:23Z`
- From: `daniel@btpestcontrol.com`
- To: `daniel+lead-desk@btpestcontrol.com`
- Subject: `BT-INTAKE-PROOF-DESK-CTRL-E9A8`
- Intent: `revise_draft` bound to current packet `BTC-contactus-1a096ffa404426f1` v3
- Labels: `SENT`, `UNREAD`, `B&T Lead Desk/Control`
- Inbox query `in:inbox subject:BT-INTAKE-PROOF-DESK-CTRL-E9A8 newer_than:1d`: empty
- Newest `contactus@` control remains `1a097742cdbbdb8b` at `2026-09-12T21:09:28Z` (before this send)

Gmail filters were not changed.

## Why draft-save is BLOCKED

Live receipts live on the GCE host at
`/var/lib/bt-intake-proof/receipts.sqlite`. This VM has no SSH and no
copy of that store. Plus-address processing is
`desk-plus-control --message-id 1a0979e37a0b0a94` after deploy.

The sent message authorizes on the plus path locally
(`sender_ok=True`, `plus_address_sent_mailbox_match`, intent
`revise_draft`). Applying it still needs the host case/version/nonce
row.

Offline: `tests/test_desk_plus_control.py` saves exactly one version on
the plus path and rejects spoofed / missing-SENT / customer copies.
Full suite: 255 passed, 1 skipped.
