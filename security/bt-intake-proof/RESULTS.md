# B&T contactus intake proof

**Overall: BLOCKED** at Desktop OAuth client + `contactus@` consent.

Authorized project: **bt-intake-proof**. The four named Pub/Sub/watch creates are authorized later in that project only. No billing account was linked. No OAuth client JSON is in this environment, so no Gmail OAuth URL has been issued. No mail was sent. `daniel@` Gmail MCP was not used.

Test 0 isolation is unchanged.

## Scorecard

| Gate | Result | Detail |
| --- | --- | --- |
| Gmail watch registration | BLOCKED | Waiting for Desktop OAuth client JSON, then contactus@ read-only consent |
| Pub/Sub delivery | BLOCKED | Topic/subscription not created; no Cloud admin credential here |
| New-message automatic capture | BLOCKED | Upstream Google gate |
| Old-thread reply capture | BLOCKED | Upstream Google gate |
| State preservation | BLOCKED | Cannot prove unread/labels unchanged without live watch |
| Durable storage | BLOCKED | Live mailbox write blocked; local SQLite contract tests PASS |
| Deduplication | BLOCKED | Live mailbox write blocked; local unique(mailbox, message id) PASS |
| Recovery after receiver downtime | BLOCKED | Upstream Google gate |
| Codex ExternalMessage delivery | BLOCKED | Phase 4 waits for durable Gmail capture |

Stopped at: `phase_1_google_setup` / Desktop OAuth client.

See `OAUTH_CLIENT_GUIDE.md`.
