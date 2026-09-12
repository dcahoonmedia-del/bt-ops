# Plus-address draft-save test

Overall: **BLOCKED**

This file records one earlier send and the offline contract. It is not
Cloud Work iPhone proof, not a GCE deploy, and not a saved live case.

Do not replay Gmail id `1a0979e37a0b0a94`.

## What actually sent the control

| Fact | Value |
| --- | --- |
| Tool | Cursor cloud-agent Gmail MCP `send_message` |
| Account | authenticated `daniel@btpestcontrol.com` in this Cursor run |
| Environment | Cursor cloud VM, not Daniel’s iPhone, not ChatGPT Lead Desk / Cloud Work |
| Time | `2026-09-12T21:55:23Z` |
| Gmail id | `1a0979e37a0b0a94` |
| From / To | `daniel@` → `daniel+lead-desk@` |
| Labels then | `SENT`, `UNREAD`, `B&T Lead Desk/Control` (not `INBOX`) |

A Cursor MCP send is only sent-message proof. It does not prove Cloud
Work or iPhone execution unless that path is independently evidenced.

## Separated claims

| Claim | Status |
| --- | --- |
| Sent-message proof (MCP send exists in Daniel SENT) | Observed earlier; do not replay |
| Offline authorization (unit tests / local inspect) | Implemented in this PR; not host runtime |
| Deployed on GCE | **No.** Deployment is held. “Backend accepts” means this branch’s code, not `/opt/bt-intake-proof` |
| Saved live case / new draft version | **No.** Host SQLite was not reached |
| Result delivery to Work | **None live.** Offline path writes one plus-result intent; live send needs a separate daniel@ send-only token and host activation |

## Required live checks from the earlier send

| Check | Result |
| --- | --- |
| One control appeared at the plus-address | Observed via Cursor MCP, not Cloud Work iPhone |
| Exactly one new draft version saved on the live case | **BLOCKED** |
| No customer message | Observed for that MCP send |
| No new `contactus@` control from that send | Observed (newest contactus CTRL remained `1a097742cdbbdb8b` at 21:09:28Z) |
| That control stayed out of Inbox | Observed then; filters were not changed |

## Remaining live blockers

1. Deployment is held. Host is not running this PR.
2. Automatic Daniel history discovery and the plus result sender exist
   in this PR. They are packaged disabled and are **not** running on
   the GCE host until project-lead activation.
3. Live result delivery needs a separate already-authorized daniel@
   `gmail.send`-only token at `BT_DANIEL_PLUS_RESULT_SEND_TOKEN`.
   Missing that token is an activation blocker and does not consume a
   new decision. Do not widen the readonly token.
4. `1a0979e37a0b0a94` must not be processed or timestamp-adjusted.
   First-processing freshness uses provider `internalDate` within 15
   minutes; that message is not grandfathered.
5. This VM still cannot open `/var/lib/bt-intake-proof/receipts.sqlite`.
