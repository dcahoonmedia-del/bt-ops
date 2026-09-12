# CTRL-ENC verification (no send, no case mutation)

Isolation stays on. Do not send mail. Do not insert rows. Do not reset SQLite.
Do not touch `BTC-contactus-1a096d60643b3b1a`. Do not recover `--execute`.
Do not repeat action 2 `--verify-recipient`.

## Local tests

```
cd security/bt-intake-proof
PYTHONPATH=src python3 -m unittest tests.test_desk_control_codec tests.test_desk_bridge tests.test_desk_sent_proof
PYTHONPATH=src python3 -m unittest discover -s tests
```

`tests.test_desk_control_codec` reconstructs the Sent-vs-delivered NOTE wrap
(after `ants.` and `office`) and proves the old simple `NOTE=` form fails
closed. It does not mark the live case PASS.

## Host generate-only (read-only store)

Existing packet path. Copies the 64-character hash from JSON. Does not send.

```
sudo -u btintake python3 -m bt_intake_proof.cli lead-desk-packets \
  --store /var/lib/bt-intake-proof/receipts.sqlite \
  --case-id BTC-contactus-1a096d60643b3b1a \
  --out /tmp/ctrl-enc-packets
```

Inspect only:

- `/tmp/ctrl-enc-packets/desk-control.json` → `binding.packet_hash` length 64
- `generate_only: true`
- Store fingerprint unchanged
- `case_send_actions` for that case still 0
- Actions 1 and 2 still `recipient_receipt_verified` consumed 1

Optional exact revise body (still generate-only):

```
sudo -u btintake python3 -m bt_intake_proof.cli lead-desk-packets \
  --store /var/lib/bt-intake-proof/receipts.sqlite \
  --case-id BTC-contactus-1a096d60643b3b1a \
  --control-intent revise_draft \
  --control-note-file /tmp/exact-note.txt \
  --out /tmp/ctrl-enc-packets
```

That writes `desk-control.txt`. Do not send it at this step.

## What a later live wrap check must show

Sent mailbox and contactus delivered body may differ in line breaks.
`parse_control_mail` / `canonical_control_payload` must match.
`PACKET_HASH` stays an exact 64-character compare.
Quoted `>` copies still do not authorize.
