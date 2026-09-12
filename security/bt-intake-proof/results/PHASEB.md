# Phase B — cloud-hosted intake proof

VM `bt-intake-cloud` is on-spec (e2-small, us-east1-c, receiver SA, 20 GB). No JSON key. Test mail was sent from Gmail, not the Mac.

| Test | Result |
| --- | --- |
| CLOUD-NEW | PASS — 6.19s event-driven, UNREAD/INBOX unchanged, Codex ExternalMessage PASS |
| CLOUD-REPLY | PASS — 3.6s on existing `BT-PILOT-0911-TEST02` thread `1a09243262a6a145`, classified `reply`, Codex PASS |
| CLOUD-RECOVERY | PASS — receiver stopped (3 rows, cursor `6008220`); after start, history recovered 1 row (`6008220`→`6008282`); Pub/Sub leftover acked with 0 new; no duplicate; Codex PASS |
| Watch renew | PASS — cursor stayed `6008282`, not rewound |

## Still needed

VM restart persistence. Blocked until Edit → SSH keys uses Username `btadmin` and Key **without** `btadmin:`. Then RESET the VM. I will confirm the service comes back on its own.
