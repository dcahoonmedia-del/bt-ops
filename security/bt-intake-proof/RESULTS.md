# B&T contactus intake proof

**Gmail `users.watch`: PASS.** Receiver pull: **BLOCKED** — cannot create the service account via API.

No JSON key was created. `iam.serviceAccounts.create` returned permission denied. Daniel can create the SA and two grants in Cloud Console.

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
