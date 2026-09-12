# Phase F1 — read-only Lead Desk via Gmail packets

**Overall: PASS** for the iPhone-reachable Gmail bridge. Custom ChatGPT MCP is **not** the iPhone path and was not opened.

OpenAI custom MCP apps are web-only. This slice does not treat MCP as the Lead Desk. No public ingress. No new domain. No paid auth product.

The desk is three durable, backend-generated packets in `daniel@btpestcontrol.com`. ChatGPT on iPhone should answer from those Gmail messages, not from chat memory.

## Scorecard

| Gate | Result |
| --- | --- |
| Secure public MCP connection | not used (web-only; no public ingress) |
| ChatGPT custom MCP on iPhone | BLOCKED by OpenAI (not attempted) |
| iPhone availability via Gmail | PASS (packets in daniel@ INBOX, still UNREAD after inspect) |
| ChatGPT Gmail retrieval path | PASS (same connected daniel@ mailbox) |
| list / attention queue packet | PASS |
| read case packet | PASS |
| health packet | PASS |
| evidence accuracy vs SQLite | PASS |
| zero case mutations | PASS (store fingerprint unchanged) |
| zero Gmail label mutations on inspect | PASS (`UNREAD` kept) |
| unauthorized public access | PASS (no public endpoint exists) |

## How Daniel uses it on iPhone

In ChatGPT, with Gmail already connected, ask:

- “What came in?”
- “Show me the latest lead.”
- “Show me the Phase E test case.” / “What happened with that case?”
- “Did the message actually send?”
- “Is intake healthy?”

Tell ChatGPT to read the latest `BT-INTAKE-PROOF-DESK-*` emails and not to invent from memory.

| Ask | Packet subject |
| --- | --- |
| What came in? / latest lead | `BT-INTAKE-PROOF-DESK-QUEUE-E9A8 attention queue 2026-09-12T05:29` |
| Phase E case / what happened / did it send? | `BT-INTAKE-PROOF-DESK-CASE-E9A8 BTC-contactus-1a093f8e919b8787` |
| Is intake healthy? | `BT-INTAKE-PROOF-DESK-HEALTH-E9A8 intake ok 2026-09-12T05:29` |

## Live packets (daniel@ → daniel@, no CC)

Generated from `/var/lib/bt-intake-proof/receipts.sqlite` at `2026-09-12T05:29:15Z`. Fingerprint `f5652512b07ef4f0…` before and after. Receiver stayed active. Case/decision/send counts unchanged.

| Kind | Gmail id | Facts in the packet |
| --- | --- | --- |
| Queue | `1a09417e8285548a` | 6 cases. Latest lead is Phase E `BTC-contactus-1a093f8e919b8787`. 4 still waiting on Daniel. |
| Case | `1a09417ea542cb8a` | Phase E approved v1. Send `recipient_receipt_verified`, provider `1a094071738bb70f`, consumed. Fieldwork `FIELDWORK_NOT_ACCESSED` / blocked. |
| Health | `1a09417eaf52504c` | Overall **ok** from watch + last receipt + systemd, not from process existence alone. Watch current, 15 receipts, 0 unacked, 0 failed/unknown sends. |

An earlier short queue message `1a094178a69302ae` was incomplete. Use the later full queue.

## Not done

No public MCP. No approvals, draft revisions, ownership changes, customer sends, Fieldwork writes, LSA/CTM, scheduling, or Auditor. Read-only query helpers stay in-tree for a later web/debug MCP if Daniel wants that on ChatGPT web only.
