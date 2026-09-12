# B&T contactus intake proof

Prove automatic intake from `contactus@btpestcontrol.com` using:

`Gmail users.watch` → dedicated Pub/Sub topic → Python receiver → SQLite receipt → isolated Codex `ExternalMessage`.

This is not a lead-management product. It does not send mail, create drafts, change labels, touch Fieldwork, LSA, CTM, scheduling, or approval UI.

Test 0 isolation stays unchanged. Codex delivery reuses `security/codex-external-isolation` with the same read-only sandbox and `lead_email_ingest` / `external_untrusted` boundary.

## Current gate

Phase A intake proof: **PASS.** Phase B cloud host: **PASS.** See `results/PHASEB.md`. Do not send more `BT-INTAKE-PROOF-*` mail.

The Cursor Gmail MCP is `daniel@btpestcontrol.com` and can send/modify mail; it is not used here.

## Local contracts (no Google)

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Live commands (only after gates are READY)

```bash
PYTHONPATH=src python3 -m bt_intake_proof.cli gate
PYTHONPATH=src python3 -m bt_intake_proof.cli setup
PYTHONPATH=src python3 -m bt_intake_proof.cli receive-once
```

Codex dispatch (Phase 4 only, after a durable eligible receipt exists):

```bash
bash ../codex-external-isolation/scripts/host_intake_dispatch.sh /path/to/payload.json
```
