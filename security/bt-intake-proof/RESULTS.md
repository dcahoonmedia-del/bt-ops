# B&T contactus intake proof

**Gmail `users.watch`: PASS.** Receiver pull: **BLOCKED** — Token Creator for `daniel@` on `bt-intake-proof-receiver` is not effective yet.

No JSON key was created. Steps 1 and 2 (SA + subscription Subscriber) are done. Impersonation still returns `iam.serviceAccounts.getAccessToken` denied.

## Scorecard

| Gate | Result |
| --- | --- |
| Gmail watch registration | PASS |
| Pub/Sub delivery | BLOCKED — waiting for console-created receiver SA + impersonation |
| New-message automatic capture | BLOCKED |
| Old-thread reply capture | BLOCKED |
| State preservation | BLOCKED |
| Durable storage | BLOCKED (local contract PASS) |
| Deduplication | BLOCKED (local contract PASS) |
| Recovery after receiver downtime | BLOCKED |
| Codex ExternalMessage delivery | BLOCKED |
