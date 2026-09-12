# Phase B — cloud-hosted intake proof

**Overall: PASS.** The proven Phase A path runs on GCE VM `bt-intake-cloud` with the Mac off. No JSON key. No public app ports. Unread and labels unchanged. Isolated Codex treated mail as `external_untrusted`.

| Test | Result |
| --- | --- |
| CLOUD-NEW | PASS — 6.19s event-driven, UNREAD/INBOX unchanged, Codex ExternalMessage PASS |
| CLOUD-REPLY | PASS — 3.6s on existing `BT-PILOT-0911-TEST02` thread `1a09243262a6a145`, classified `reply`, Codex PASS |
| CLOUD-RECOVERY | PASS — history catch-up from `6008220`→`6008282`, 1 row, no duplicate, Codex PASS |
| Watch renew | PASS — cursor stayed `6008282` |
| VM RESET | PASS — boot `03:39Z`, `bt-intake-receiver` enabled and active at `03:39:31Z`, identity `gce_metadata`, 4 receipts and cursor `6008282` still on disk |

Stop here. Do not process real customer mail. Do not send more `BT-INTAKE-PROOF-CLOUD-*` markers.
