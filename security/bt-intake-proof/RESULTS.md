# B&T contactus intake proof

**Gmail `users.watch` : PASS**

Daniel's Console screenshot showed subscription `bt-intake-proof-contactus-sub` already exists on topic `bt-intake-proof-contactus`. I did not create a second subscription. I registered `users.watch` with the existing `contactus@` read-only token.

## Watch registration

| Field | Value |
| --- | --- |
| Project | `bt-intake-proof` |
| Mailbox | `contactus@btpestcontrol.com` |
| Topic | `projects/bt-intake-proof/topics/bt-intake-proof-contactus` |
| Subscription | `projects/bt-intake-proof/subscriptions/bt-intake-proof-contactus-sub` |
| historyId | `6007776` |
| Expiration | `2026-09-19T01:52:34.594000+00:00` (`1789782754594`) |

## Scorecard

| Gate | Result | Detail |
| --- | --- | --- |
| Gmail watch registration | PASS | historyId 6007776, expires 2026-09-19T01:52:34Z |
| Pub/Sub delivery | BLOCKED | Watch implies Gmail can publish; this receiver still cannot pull the subscription with Gmail read-only |
| New-message automatic capture | BLOCKED | Waiting to start receiver pull |
| Old-thread reply capture | BLOCKED | Upstream |
| State preservation | BLOCKED | Upstream |
| Durable storage | BLOCKED | Local contract PASS |
| Deduplication | BLOCKED | Local contract PASS |
| Recovery after receiver downtime | BLOCKED | Upstream |
| Codex ExternalMessage delivery | BLOCKED | Phase 4 waits for durable capture |
