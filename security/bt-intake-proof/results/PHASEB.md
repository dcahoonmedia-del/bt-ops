# Phase B — cloud-hosted intake proof

VM `bt-intake-cloud` is on-spec (e2-small, us-east1-c, receiver SA, 20 GB). No JSON key. Mail is sent from Gmail, not the Mac.

| Test | Result |
| --- | --- |
| CLOUD-NEW | PASS — 6.19s event-driven, UNREAD/INBOX unchanged, Codex ExternalMessage PASS |
| CLOUD-REPLY | PASS — 3.6s on existing `BT-PILOT-0911-TEST02` thread `1a09243262a6a145`, classified `reply`, Codex PASS |

## Still needed

- Recovery: stop receiver, send CLOUD-RECOVERY, start, history catch-up, no duplicate
- VM restart persistence (blocked until Edit → SSH keys Username=`btadmin`, Key without `btadmin:`)
