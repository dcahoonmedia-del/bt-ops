# Desk round-trip scorecard

Reviewed baseline: `378ffcf` / PR #14
This revision: see git commit on `cursor/bt-intake-roundtrip-e9a8`
Isolation: BT-INTAKE-PROOF on. Real-customer sends OFF. Broad/shadow capture OFF.
This milestone is **not** an approval row and does **not** reuse Phase E action 1 / `BT-PHASE-E-SEND-E9A8-C4F1`.

Evidence labels: **unit** (unittest), **fixture** (in-memory Gmail/send), **runtime** (live Gmail/VM), **real-phone** (Daniel iPhone, Mac off).

## Gates

| Gate | Result | Evidence |
| --- | --- | --- |
| Provider-backed origin (fail closed) | **PASS** (unit) | `tests/test_desk_roundtrip.py` spoofed From / forged AR / missing evidence; `desk_origin.py` threat model |
| Quoted / copied control syntax | **PASS** (unit) | quoted `>` CTRL does not authorize |
| Replay / concurrency | **PASS** (unit) | same Gmail id returns cached result; new id + consumed nonce is rejected |
| Restart between accept / execute / verify | **PASS** (unit) | reopen store; desk-queued execute then verify; no second send |
| Hold | **PASS** (unit) | existing `test_desk_bridge.py` + execute-time hold recheck |
| Brenda ownership | **PASS** (unit) | `test_office_ownership_brenda_and_ally` |
| Ally ownership | **PASS** (unit) | same |
| no_response_needed | **PASS** (unit) | `test_no_response_and_packet_binding_roundtrip` |
| revise_draft | **PASS** (unit) | new version; old approval cannot send |
| Stale / new-inbound rejection | **PASS** (unit) | packet hash / inbound change blocks; no queue |
| Bad binding | **PASS** (unit) | wrong nonce / hash / intent |
| Result + fresh case packet delivery | **PASS** (unit/fixture) | outbox UNIQUE + MemorySendTransport. **Runtime Gmail:** no `DESK-RESULT` / `DESK-CTRL` / `BT-DESK-ROUNDTRIP-SEND` threads on daniel@ as of 2026-09-12 search. Pre-existing F1 queue/case/health ids `1a09417e8285548a` / `1a09417ea542cb8a` / `1a09417eaf52504c` (2026-09-12T05:29Z) are **not** this milestone's delivery and are **not** a phone PASS. Live result delivery **BLOCKED** until VM deploy |
| Desk-only execute + independent verify | **PASS** (unit/fixture) | `queued_by=desk_control` only; Phase E leftovers stay queued; unknown does not retry |
| Narrowly approved internal send | **PENDING** | exact packet prepared below; not sent; not a reused Phase E approval |
| Live VM deploy / deployed revision | **BLOCKED** | this agent VM has no `security/bt-intake-proof/secrets/bt-intake-cloud` SSH key |
| Real ChatGPT iPhone / Mac-off | **PENDING** | packets in Gmail would not be a phone PASS; wait for Daniel |

## Exact internal send packet (needs Daniel's conversational approval)

Do not send until Daniel approves this exact version.

- From: `contactus@btpestcontrol.com`
- To: `daniel@btpestcontrol.com`
- CC / BCC / attachments / links: none
- Subject: `BT-DESK-ROUNDTRIP-SEND-E9A8 internal send test`
- Timing: `immediate_supervised`
- Body:

```
BT-DESK-ROUNDTRIP-SEND-E9A8

This is an isolated internal Lead Desk round-trip send test only.
It is not customer mail and does not book, price, or promise service.

B&T office
```

## Remaining risks

- Gmail AR is the strongest origin proof available with current access. A daniel@ Sent cross-check on the live VM would be an extra control; do not weaken this gate to skip it.
- Case packets embed the draft body, so Sent search is filtered by the exact send subject.
- ChatGPT iPhone may show a sent-mail confirmation for the control message. The backend cannot hide that UI.
- Without SSH deploy, the live host still runs the reviewed Gmail-bridge revision and will not deliver results or execute desk-queued sends.

## Phone-test script

See `results/DESK_ROUNDTRIP_PHONE.md`.
