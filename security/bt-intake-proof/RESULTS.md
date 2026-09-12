# B&T contactus intake proof

**Overall: BLOCKED** waiting for `contactus@btpestcontrol.com` to approve Gmail read-only.

- Project: `bt-intake-proof`
- Desktop OAuth client: present, `installed`, project match
- Scope requested: `https://www.googleapis.com/auth/gmail.readonly` only
- Authorization URL: issued and shown to Daniel
- Client secret: not committed
- Billing: not linked
- Pub/Sub topic/subscription: not created yet
- `users.watch`: not registered
- Mail: not sent
- `daniel@` Gmail MCP: unused

## Scorecard

| Gate | Result |
| --- | --- |
| Gmail watch registration | BLOCKED |
| Pub/Sub delivery | BLOCKED |
| New-message automatic capture | BLOCKED |
| Old-thread reply capture | BLOCKED |
| State preservation | BLOCKED |
| Durable storage | BLOCKED (local contract PASS) |
| Deduplication | BLOCKED (local contract PASS) |
| Recovery after receiver downtime | BLOCKED |
| Codex ExternalMessage delivery | BLOCKED |
