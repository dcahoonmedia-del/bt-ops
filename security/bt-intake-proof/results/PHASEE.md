# Phase E — exact approval → bounded Gmail send → independent verification

**Logic/negative-test overall: PASS.**  
**Live inbound → durable case → exact draft → iPhone review packet: PASS.**  
**Live contactus send / Sent verification / recipient receipt / VM restart of a live send: BLOCKED** until a dedicated `contactus@` `gmail.send` token exists and Daniel approves this exact packet. Intake readonly credentials were not used to send.

Live case: `BTC-contactus-1a093f8e919b8787` draft v1. Review mail id `1a093fa3665da401`. Internal B&T only.

No real-customer mail. No Fieldwork access or write. No LSA/CTM native send. No Independent Auditor.

## Scorecard

| Gate | Result |
| --- | --- |
| Exact approval binding (case, draft version, mailbox, recipient, thread, subject, body, no attachments/links, timing, latest inbound) | PASS |
| Stale / superseded approval rejection | PASS |
| Changed payload / recipient rejection | PASS |
| Single-use approval | PASS |
| Direct bounded Gmail send (separate sender; Codex has no send) | PASS (unit / memory transport). Live contactus send **BLOCKED** (`contactus_send_token_not_configured`) |
| No agent-to-agent send delegation | PASS |
| Sender cannot silently modify approved content | PASS |
| Independent Sent verification (not the sender API claim) | PASS (unit / memory). Live contactus Sent **BLOCKED** until a real send exists |
| Recipient receipt verification, unread preserved | PASS (unit / memory). Live daniel@ inspect **BLOCKED** until a real send exists |
| Duplicate prevention | PASS |
| Ambiguous-send / timeout does not auto-retry | PASS |
| Persistence across process restart (sqlite reopen) | PASS |
| Persistence across live VM restart after a real send | BLOCKED (no live send yet) |
| Zero real-customer communication | PASS |
| Zero Fieldwork activity | PASS |

## What this slice does

- Phase E inbound marker `BT-INTAKE-PROOF-CASEMGR-PHASEE-E9A8` installs a host-written exact draft. Codex does not invent the send body.
- The iPhone review packet shows the complete From/To/CC/BCC/subject/body/timing packet.
- Phase C approve still records `send_triggered=0` and does not queue a send.
- Phase E approve may queue one stored action. The host loop never executes it.
- `python3 -m bt_intake_proof phasee-execute <action_id>` is the only sender entry. It locks, re-reads, revalidates, submits the stored payload, and consumes the approval.
- Status after a provider accept is `attempted_verification_pending`, not `sent`.
- Timeout / ambiguous provider response is `unknown`, consumed, no automatic resend.
- `phasee-verify` searches contactus Sent with the existing **read-only** token and compares the actual message.

## Negative tests (no extra real mail)

1. Superseded draft cannot send
2. Altered body after approval cannot send
3. Changed recipient cannot send
4. New inbound invalidates the old approval
5. Consumed approval cannot send twice
6. Simulated timeout / `unknown` does not cause `execute_due_sends` to resend

## Live remaining

Live send from `contactus@` requires a dedicated send token at `secrets/contactus_gmail_send_token.json` (`gmail.send`, contactus@ only). The intake `gmail.readonly` token must stay read-only.

Do not send as daniel@ and claim it was contactus@.
