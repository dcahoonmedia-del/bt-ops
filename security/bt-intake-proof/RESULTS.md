# B&T contactus intake proof

**Gmail `users.watch`: PASS.** Receiver pull: **BLOCKED** — IAM API is disabled.

Cloud owner login succeeded and was stored. No JSON key was created. Creating `bt-intake-proof-receiver` requires enabling the IAM API.

## Scorecard

| Gate | Result |
| --- | --- |
| Gmail watch registration | PASS |
| Pub/Sub delivery | BLOCKED — IAM API disabled; no pull yet |
| New-message automatic capture | BLOCKED |
| Old-thread reply capture | BLOCKED |
| State preservation | BLOCKED |
| Durable storage | BLOCKED (local contract PASS) |
| Deduplication | BLOCKED (local contract PASS) |
| Recovery after receiver downtime | BLOCKED |
| Codex ExternalMessage delivery | BLOCKED |
