# Phone control handoff scorecard

| Item | Result | Notes |
| --- | --- | --- |
| Handoff derived from deployed `c41404e` / `2ec51860` | **PASS** | No runtime change |
| CASE packet supplies case/version/nonce/hash | **PASS** | Copy `PACKET_HASH`; do not recompute |
| CTRL-ENC contract on delivered CASE mail | **BLOCKED** | Not printed; this handoff is the smallest fix |
| Control-binding expiry field | **N/A** | Not a runtime field; use newest packet |
| `mailbox` printed for hash recompute | **BLOCKED** (optional) | Copy hash instead; do not invent a field this milestone |
| Offline vector vs production parser | **PASS** (unit) | `tests.test_phone_handoff` |
| Portable stdlib checker | **PASS** | `python3 offline_ctrl_enc.py` |
| Encoded live mail / Mac-off | **BLOCKED** | Not this milestone |
| Completed Brenda case / actions 1–2 | **untouched** | No send, no deploy |

Document: `PHONE-CONTROL-HANDOFF.md`
