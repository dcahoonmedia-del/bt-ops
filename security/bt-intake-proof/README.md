# B&T contactus intake proof

Prove automatic intake from `contactus@btpestcontrol.com` using:

`Gmail users.watch` → dedicated Pub/Sub topic → Python receiver → SQLite receipt → isolated Codex `ExternalMessage`.

This is not a lead-management product. It does not send mail, create drafts, change labels, touch Fieldwork, LSA, CTM, scheduling, or approval UI.

Test 0 isolation stays unchanged. Codex delivery reuses `security/codex-external-isolation` with the same read-only sandbox and `lead_email_ingest` / `external_untrusted` boundary.

## Current gate

Phase A intake proof: **PASS.** Phase B cloud host: **PASS.** Phase C Case Manager: **PASS** (`results/PHASEC.md`). Phase D matching/context: **PASS**; live Fieldwork **BLOCKED**. Phase E exact-approval send: **PASS** (`results/PHASEE.md`). Phase F1 Lead Desk: **PASS** via Gmail packets (`results/PHASEF1.md`). Production capture-then-classify is documented and tested (`knowledge/PRODUCTION_INTAKE.md`) but **not live**. Isolated `BT-INTAKE-PROOF-*` filters stay on. Lead Desk control is ChatGPT Gmail control mail → structured action → Phase E binding (`knowledge/DESK_CONTROL.md`, `knowledge/CHATGPT_LEAD_DESK.md`); the Python utterance helper is fallback only. Custom ChatGPT MCP is web-only and was not opened. Customer sending remains off except the one internal Phase E test.

The Cursor Gmail MCP is `daniel@btpestcontrol.com` and can send/modify mail. Phase C used it only to send marked internal tests and Daniel's review packets. It is not a watch/Pub/Sub substitute.

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
