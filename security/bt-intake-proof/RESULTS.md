# B&T contactus intake proof

New-message and Codex are PASS. A live reply was captured in 15.54s, but on the new-message thread, not `BT-PILOT-0911-TEST02`.

## Scorecard

| Gate | Result |
| --- | --- |
| Gmail watch registration | PASS |
| Pub/Sub delivery | PASS |
| New-message automatic capture | PASS — 18.47s |
| Old-thread reply capture | BLOCKED — waiting for reply on `BT-PILOT-0911-TEST02` |
| State preservation | PASS |
| Durable storage | PASS |
| Deduplication | BLOCKED (local contract PASS) |
| Recovery after receiver downtime | BLOCKED |
| Codex ExternalMessage delivery | PASS |
