# Bounded recovery for `1a096ffa404426f1` only

Do **not** run this from deploy. Do **not** resend the inquiry.
Do **not** rerun the model. Do **not** edit the stored draft.
Do **not** consume controls. Does **not** send until the host loop drains
the outbox after `--enqueue`.

Allow-list is hardcoded: `1a096ffa404426f1`. Any other Gmail id is refused.

## After deployment review (Codex on the VM)

Dry-run (default):

```
sudo -u btintake python3 -m bt_intake_proof.cli recover-initial-case-review \
  --gmail-id 1a096ffa404426f1 \
  --store /var/lib/bt-intake-proof/receipts.sqlite
```

Expect `ok=true`, `execute=false`, `model_rerun=false`, `reason=dry_run`.
Confirm `case_id` / `draft_version` and that the stored proposed response is
unchanged. If `draft_missing_do_not_redraft`, stop — do not invent a draft.

Enqueue only (still no send from this command):

```
sudo -u btintake python3 -m bt_intake_proof.cli recover-initial-case-review \
  --gmail-id 1a096ffa404426f1 \
  --store /var/lib/bt-intake-proof/receipts.sqlite \
  --enqueue
```

The next `finish_desk_roundtrip` cycle delivers one CASE packet contactus →
daniel if the outbox row is `pending`. `sent` / `unknown` are not retried.

If the inbound is still `needs_draft` (never drafted), do **not** use this
command. The forward path will draft once, then enqueue. That is a new draft,
not this recovery.
