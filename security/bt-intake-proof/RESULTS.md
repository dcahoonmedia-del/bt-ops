# B&T contactus intake proof

New-message, old-thread reply, and isolated Codex are PASS. Recovery is next.

## Scorecard

| Gate | Result |
| --- | --- |
| Gmail watch registration | PASS |
| Pub/Sub delivery | PASS |
| New-message automatic capture | PASS — 18.47s |
| Old-thread reply capture | PASS — 14.69s on `Re: BT-PILOT-0911-TEST02` |
| State preservation | PASS |
| Durable storage | PASS |
| Deduplication | BLOCKED (local contract PASS; live proof is recovery) |
| Recovery after receiver downtime | BLOCKED |
| Codex ExternalMessage delivery | PASS |
