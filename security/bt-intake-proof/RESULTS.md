# B&T contactus intake proof

**Gmail `users.watch`: PASS.** Receiver pull: **BLOCKED** pending project-owner Cloud login.

No service-account JSON key was created. This VM cannot impersonate without a source Cloud identity.

## Watch registration

| Field | Value |
| --- | --- |
| Project | `bt-intake-proof` |
| Mailbox | `contactus@btpestcontrol.com` |
| Topic | `projects/bt-intake-proof/topics/bt-intake-proof-contactus` |
| Subscription | `projects/bt-intake-proof/subscriptions/bt-intake-proof-contactus-sub` |
| historyId | `6007776` |
| Expiration | `2026-09-19T01:52:34Z` |

## Scorecard

| Gate | Result |
| --- | --- |
| Gmail watch registration | PASS |
| Pub/Sub delivery | BLOCKED — waiting for Cloud impersonation source (no JSON key) |
| New-message automatic capture | BLOCKED |
| Old-thread reply capture | BLOCKED |
| State preservation | BLOCKED |
| Durable storage | BLOCKED (local contract PASS) |
| Deduplication | BLOCKED (local contract PASS) |
| Recovery after receiver downtime | BLOCKED |
| Codex ExternalMessage delivery | BLOCKED |
