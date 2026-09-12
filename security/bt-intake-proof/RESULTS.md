# B&T contactus intake proof

**Gmail `users.watch`: PASS.** **Pub/Sub pull: PASS.** Impersonation used Token Creator. No JSON key was created.

Pulled one Gmail watch envelope for `contactus@btpestcontrol.com` (`historyId` `6007776`, message id `21177054176054382`). It was **not** acked and Gmail history was **not** fetched, so no customer mail was processed.

## Scorecard

| Gate | Result |
| --- | --- |
| Gmail watch registration | PASS |
| Pub/Sub delivery | PASS |
| New-message automatic capture | BLOCKED — waiting for marked internal mail |
| Old-thread reply capture | BLOCKED |
| State preservation | BLOCKED |
| Durable storage | BLOCKED (local contract PASS) |
| Deduplication | BLOCKED (local contract PASS) |
| Recovery after receiver downtime | BLOCKED |
| Codex ExternalMessage delivery | BLOCKED |
