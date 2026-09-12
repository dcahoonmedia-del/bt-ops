# B&T contactus intake proof

**Gmail `users.watch`: PASS.** **Pub/Sub pull: PASS.** **New-message capture: PASS** in 18.47s, event-driven.

No JSON key. Unread and labels unchanged. Codex dispatch is still pending.

## Scorecard

| Gate | Result |
| --- | --- |
| Gmail watch registration | PASS |
| Pub/Sub delivery | PASS |
| New-message automatic capture | PASS — 18.47s, event-driven, marker `BT-INTAKE-PROOF-NEW-E9A8-7F3C` |
| Old-thread reply capture | BLOCKED |
| State preservation | PASS — UNREAD/INBOX unchanged |
| Durable storage | PASS |
| Deduplication | BLOCKED (local contract PASS) |
| Recovery after receiver downtime | BLOCKED |
| Codex ExternalMessage delivery | BLOCKED |
