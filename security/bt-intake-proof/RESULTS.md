# B&T contactus intake proof

**Overall: PASS.** Automatic intake from `contactus@` is proven on the laptop path (Phase A) and on GCE VM `bt-intake-cloud` with the Mac off (Phase B). No JSON key. Unread and labels unchanged. Isolated Codex treated mail as `external_untrusted`.

Phase B details: `results/PHASEB.md`.

## Scorecard

| Gate | Result |
| --- | --- |
| Gmail watch registration | PASS |
| Pub/Sub delivery | PASS |
| New-message automatic capture | PASS — 18.47s, event-driven |
| Old-thread reply capture | PASS — 14.69s on `Re: BT-PILOT-0911-TEST02` |
| State preservation | PASS — UNREAD/INBOX unchanged |
| Durable storage | PASS |
| Deduplication | PASS — recovery message stored once after history catch-up and later Pub/Sub notice |
| Recovery after receiver downtime | PASS — `BT-INTAKE-PROOF-RECOVERY-E9A8-7F3C` via history from cursor `6007981` |
| Codex ExternalMessage delivery | PASS — `lead_email_ingest` / `external_untrusted` |
