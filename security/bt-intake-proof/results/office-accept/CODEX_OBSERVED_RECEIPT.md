# Codex-observed action 2 receipt (not a Cursor unit test)

Recorded 2026-09-12 from project-lead acceptance of reporting artifact
`5af92d6e4e18627e2a0006f6702b3afddc5041b162601dff47c07424cffec5a0`.
This is **runtime evidence observed by Codex on the live host**, separate from
the isolated office-acceptance unit pack in this folder.

## Deploy
- Artifact SHA256: `5af92d6e4e18627e2a0006f6702b3afddc5041b162601dff47c07424cffec5a0`
- Guarded transaction: unchanged
- Backup: `20260912T175717Z-6c65ec24`
- Health: PASS
- Service: active
- DB / tokens: unchanged
- Customer sends: OFF
- Broad / shadow capture: OFF
- No proof resend

## Existing action 2
Command:

```
sudo -u btintake bash /opt/bt-intake-proof/scripts/report_desk_send_outcome.sh \
  --action-id 2 --case-id BTC-contactus-desk-roundtrip-e9a8-20260912 \
  --verify-recipient --enqueue-result
```

Observed:
- Contactus Sent exact count: 1
- Daniel mailbox exact count: 1
- Backend status recorded: `recipient_receipt_verified`
- Daniel inbox message id: `1a096afc63d60ab4`
- Outbox row 6 kind: `result_recipient_receipt_verified` (delivered)
- Independent Daniel read of final RESULT: `1a096c49ac2dd383` with an accurate receipt claim
- Restart + repeated report/enqueue: `already_reported=true`, `enqueued=false`, `status=sent`

Do not treat this file as a Cursor unit-test result. Do not reuse it as a
new send approval. Actions 1 and 2 stay preserved.
