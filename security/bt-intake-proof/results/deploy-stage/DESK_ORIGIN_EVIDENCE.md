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

Mailbox-bound AR (correct SPF/DKIM bound to daniel@) now returns `accepted=False`, `mailbox_bound=True`, `reason=mailbox_bound_provider_result_not_authorization`. `inspect_inbound` authorizes only after exact daniel@ Sent corroboration.

## Domain DKIM is not Daniel's mailbox

Runtime Gmail (daniel@ inbox, Phase E recipient copy, provider id `1a094071c6be5dab`, 2026-09-12T05:11:29Z, still UNREAD):

- First `Authentication-Results` authserv-id is `mx.google.com`.
- It sits after Gmail `Received` / `X-Received` / ARC headers and is the first header named `Authentication-Results` (ARC-Authentication-Results is a different name).
- `dkim=permerror header.i=@btpestcontrol.com` — organizational DKIM, and it did not pass.
- `spf=pass smtp.mailfrom=contactus@btpestcontrol.com` — envelope mailbox is contactus@, not daniel@.

Same `@btpestcontrol.com` DKIM identity would appear for contactus@, brenda@, ally@, or daniel@. A domain DKIM pass therefore does not prove Daniel's mailbox.

## Gmail-inserted header boundary

We trust the first `Authentication-Results` on a message fetched via the contactus Gmail API because Gmail inserts its AR on ingest. The daniel@ inbound above is evidence of that order on Gmail's inbound path. It is **not** a contactus-fetched control mail. This agent cannot read contactus@. authserv-id must be exactly `mx.google.com`.

## Sender-mailbox corroboration (required)

Authorization requires exactly one authenticated daniel@ Sent message matching:

- RFC Message-ID (necessary, not sufficient)
- recipient exactly `contactus@btpestcontrol.com` (no extra To/Cc)
- canonical structured control payload (`INTENT`, `OWNER`, `NOTE`, `CASE_ID`, `DRAFT_VERSION`, `NONCE`, `PACKET_HASH`)
- timing within 15 minutes

Missing, ambiguous, or mismatched evidence fails closed. A versioned `desk-sent-v1` row may re-attest that same control message only. `origin_already_authenticated` and legacy `origin_authenticated` do not authorize.

This is mailbox corroboration, not human-identity PASS.

## Required connection (do not mint)

Already-authorized `gmail.readonly` for `daniel@btpestcontrol.com`:

- Env: `BT_DANIEL_GMAIL_TOKEN`
- File: `security/bt-intake-proof/secrets/daniel_gmail_readonly_token.json`
- Query: `in:sent rfc822msgid:<Message-ID>`
- Scope: `https://www.googleapis.com/auth/gmail.readonly` only

contactus@ tokens cannot read daniel@ Sent. Cursor Gmail MCP is not the host path. This runtime: token file absent → **BLOCKED**. Tests use fixtures only. Do not request new OAuth.
