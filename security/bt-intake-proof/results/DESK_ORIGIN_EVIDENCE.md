# Desk origin evidence (not a full-identity PASS)

## Reproduced defect (pure function, no mail sent)

`authenticate_control_origin` on the pre-fix parser with Codex's header:

```
mx.google.com; dkim=fail header.i=@btpestcontrol.com; dkim=pass header.i=@attacker.test; spf=fail smtp.mailfrom=attacker@attacker.test
From: daniel@btpestcontrol.com
fetched_via=contactus_gmail_api gmail_message_id=synthetic-review-only
```

returned `accepted=True`, `dkim_ok=True`, `reason=gmail_ar_pass` because `_DKIM_PASS` and `_DKIM_I` searched the whole header independently.

The parser now binds each `method=result` to its own `header.i` / `smtp.mailfrom`. That input is rejected (`provider_auth_failed`).

## Domain DKIM is not Daniel's mailbox

Runtime Gmail (daniel@ inbox, Phase E recipient copy, provider id `1a094071c6be5dab`, 2026-09-12T05:11:29Z, still UNREAD):

- First `Authentication-Results` authserv-id is `mx.google.com`.
- It sits after Gmail `Received` / `X-Received` / ARC headers and is the first header named `Authentication-Results` (ARC-Authentication-Results is a different name).
- `dkim=permerror header.i=@btpestcontrol.com` — organizational DKIM, and it did not pass.
- `spf=pass smtp.mailfrom=contactus@btpestcontrol.com` — envelope mailbox is contactus@, not daniel@.

Same `@btpestcontrol.com` DKIM identity would appear for contactus@, brenda@, ally@, or daniel@. A domain DKIM pass therefore does not prove Daniel's mailbox. This module records it as `domain_dkim_not_mailbox_identity` and does not authorize.

Mailbox-bound authorization requires `spf=pass` with `smtp.mailfrom=daniel@btpestcontrol.com` or `dkim=pass` with `header.i=daniel@btpestcontrol.com` on that same method spec. That is a mailbox-bound provider result, not full identity.

## Gmail-inserted header boundary

We trust the first `Authentication-Results` on a message fetched via the contactus Gmail API because Gmail inserts its AR on ingest. The daniel@ inbound above is evidence of that order on Gmail's inbound path. It is **not** a contactus-fetched control mail. This agent cannot read contactus@; the live host's readonly token is the path that would dump that header list.

authserv-id must be exactly `mx.google.com`. Lookalikes (`mx.google.com.evil`) fail.

## Missing capability (do not weaken the gate)

A Message-ID match against daniel@ Sent would independently prove the control was submitted from that mailbox. That token is not on this agent VM. Until it exists, do not claim full identity PASS.
