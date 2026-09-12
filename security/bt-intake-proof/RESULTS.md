# B&T contactus intake proof

**Overall: BLOCKED** after successful `contactus@` read-only consent. Pub/Sub create needs a Cloud admin path I do not have.

## Consent

| Check | Result |
| --- | --- |
| Project | `bt-intake-proof` |
| Mailbox | `contactus@btpestcontrol.com` |
| Scope | `https://www.googleapis.com/auth/gmail.readonly` only |
| Refresh token | present (not committed) |
| daniel@ used | no |
| Billing linked | no |

## Scorecard

| Gate | Result | Detail |
| --- | --- | --- |
| Gmail watch registration | BLOCKED | Topic does not exist; Gmail readonly cannot CreateTopic |
| Pub/Sub delivery | BLOCKED | ACCESS_TOKEN_SCOPE_INSUFFICIENT; no Cloud admin credential |
| New-message automatic capture | BLOCKED | Upstream |
| Old-thread reply capture | BLOCKED | Upstream |
| State preservation | BLOCKED | Upstream |
| Durable storage | BLOCKED | Local contract PASS |
| Deduplication | BLOCKED | Local contract PASS |
| Recovery after receiver downtime | BLOCKED | Upstream |
| Codex ExternalMessage delivery | BLOCKED | Phase 4 waits for durable capture |

See `DANIEL_DECISIONS.md`.
