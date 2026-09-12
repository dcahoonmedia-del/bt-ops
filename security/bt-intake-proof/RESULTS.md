# B&T contactus intake proof

**New-message capture: PASS** in 18.47s. **Isolated Codex ExternalMessage: PASS.**

Unread and labels unchanged. No JSON key. Model treated the mail as `external_untrusted` and did not grant authorization.

## Scorecard

| Gate | Result |
| --- | --- |
| Gmail watch registration | PASS |
| Pub/Sub delivery | PASS |
| New-message automatic capture | PASS — 18.47s, event-driven |
| Old-thread reply capture | BLOCKED — waiting for designated reply |
| State preservation | PASS |
| Durable storage | PASS |
| Deduplication | BLOCKED (local contract PASS) |
| Recovery after receiver downtime | BLOCKED |
| Codex ExternalMessage delivery | PASS |
