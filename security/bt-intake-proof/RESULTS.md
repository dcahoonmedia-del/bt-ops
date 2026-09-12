# B&T contactus intake proof

**Overall: BLOCKED** at Phase 1 Google setup.

Daniel authorized the four named Pub/Sub/watch creates, then said the Cloud project still has to be built. `<PUT_PROJECT_ID_HERE>` was rejected as a placeholder. No Desktop OAuth client JSON is present.

No Cloud project was created or chosen here, no billing was enabled, no `contactus@` consent was completed, and no mail was sent. Cursor Gmail MCP (`daniel@`, write-capable) was not used as a watch/Pub/Sub substitute.

Test 0 isolation is unchanged.

## Scorecard

| Gate | Result | Detail |
| --- | --- | --- |
| Gmail watch registration | BLOCKED | Waiting for Daniel to create/name a real GCP project and provide Desktop OAuth JSON |
| Pub/Sub delivery | BLOCKED | Dedicated topic/subscription not created |
| New-message automatic capture | BLOCKED | Upstream Google gate |
| Old-thread reply capture | BLOCKED | Upstream Google gate |
| State preservation | BLOCKED | Cannot prove unread/labels unchanged without live watch |
| Durable storage | BLOCKED | Live mailbox write blocked; local SQLite contract tests **PASS** (19/19) |
| Deduplication | BLOCKED | Live mailbox write blocked; local unique(mailbox, message id) tests **PASS** |
| Recovery after receiver downtime | BLOCKED | Upstream Google gate; local catch-up/dedup contract **PASS** |
| Codex ExternalMessage delivery | BLOCKED | Not started; Phase 4 waits for durable Gmail capture |

Stopped at: `phase_1_google_setup`.

## What was implemented without crossing the gate

- Read-only Gmail scope lock: `gmail.readonly` only; send/modify tokens fail closed
- Dedicated topic/subscription names: `bt-intake-proof-contactus` / `bt-intake-proof-contactus-sub`
- SQLite receipts with the required fields, cursor (`historyId` + expiration), and ack-after-commit
- Eligibility: only `daniel@btpestcontrol.com` → `contactus@btpestcontrol.com` with `BT-INTAKE-PROOF-*`
- Customer mail is not stored as body/raw/subject and is never dispatched to Codex
- Isolated Codex dispatch helper that reuses Test 0's container, volume, and `ExternalMessage(tool_name="lead_email_ingest", namespace="external_untrusted")`

Local command:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Result: `Ran 19 tests in 0.192s OK`.

## What I will not do until you reply

- Pick or modify an existing Google Cloud project
- Enable billing
- Authenticate as `contactus@` without your consent
- Send email, create drafts, or change labels
- Process real customer mail into Codex
- Build lead management, Fieldwork, LSA, CTM, scheduling, or approval UI

See `DANIEL_DECISIONS.md`.
