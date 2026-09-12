# Phase B — cloud-hosted intake proof

VM `bt-intake-cloud` is on-spec (e2-small, us-east1-c, receiver SA, 20 GB). No JSON key.

## CLOUD-NEW — PASS

Sent from Gmail (`daniel@` → `contactus@`), not from the Mac.

| Check | Result |
| --- | --- |
| Event-driven capture | PASS — 6.19s, marker `BT-INTAKE-PROOF-CLOUD-NEW-E9A8-7F3C` |
| Labels | UNREAD / INBOX unchanged |
| Isolated Codex ExternalMessage | PASS — `treated_as=external_untrusted`, no authorization |
| systemd dispatch | PASS after Docker uid/payload mode fix |

## Still needed

- CLOUD-REPLY on the existing internal `BT-PILOT-0911-TEST02` thread
- VM restart persistence (blocked until Edit → SSH keys Username=`btadmin`, Key without `btadmin:`)
- Recovery: stop receiver, send CLOUD-RECOVERY marker, start, no duplicate
