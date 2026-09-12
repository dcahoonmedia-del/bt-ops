# One internal CASEMGR draft packet (not sent)

Isolation: `BT-INTAKE-PROOF-*` + daniel@ only. Customer sends OFF. Broad capture OFF.
This file is the reviewable packet and host procedure. **Do not send it from this
milestone.** Do not insert rows into production SQLite. Do not touch actions 1/2.

## What already exists (reuse, do not rebuild)

Host loop `cloud_host` already: receive → `process_cases` → `draft_pending_cases`.
A `BT-INTAKE-PROOF-CASEMGR-*` eligible receipt opens a case (`marker_kind=lead`).
If it is not Phase E / desk-roundtrip, `run_codex_draft` calls existing
`/opt/codex-external-isolation/scripts/host_case_draft.sh` (Docker image
`bt-ops-codex-isolation:0.154.0`, volume `codex-iso-chatgpt-home`).
Draft JSON is parsed and stored. Review email is written next to the store.
Desk control `revise_draft` / `office_owned` / `hold` already exist.
Proof console is `LeadDesk` / `lead-desk-packets`.

No new agent, queue, or drafting simulator is added.

## Missing connection (honest)

The live model path is **not proven in this Cursor run**. Phase C proved it once
on the host. This VM did not execute `host_case_draft` and must not treat
fixture drafts as a model PASS.

Review mail (`BT-INTAKE-PROOF-CASE-REVIEW-E9A8`) is formatted and saved as
`review-<case_id>-vN.json` beside the store. Current host loop does **not**
auto-send that file to daniel@. ChatGPT iPhone binding is on DESK-CASE packets
(`lead-desk-packets`, generate-only). Delivering a CASE packet is an existing
internal contactus→daniel path; it is not authorized from this file.

## Packet to send later (Daniel → contactus)

```
From: daniel@btpestcontrol.com
To: contactus@btpestcontrol.com
Subject: BT-INTAKE-PROOF-CASEMGR-DRAFT-E9A8 kitchen ants in Jacksonville

BT-INTAKE-PROOF-CASEMGR-DRAFT-E9A8

Hi, this is an internal B&T Lead Desk draft test only.
We got a note about ants in a kitchen in Jacksonville.
Please draft a reviewable reply I can look at.
Do not quote a price and do not book a time.

B&T office
```

Unique marker: `BT-INTAKE-PROOF-CASEMGR-DRAFT-E9A8`  
Not Phase E, not `BT-DESK-ROUNDTRIP-SEND-E9A8`.

## Expected capture / case / draft

| Step | Expected |
| --- | --- |
| Eligibility | `eligible=true` (daniel@, contactus recipient, CASEMGR marker) |
| Case | one case `BTC-contactus-<gmail_thread_id>`, `inbound_class=new_lead`, `stage=needs_draft` then `awaiting_review` |
| Model draft | `host_case_draft.sh` writes `/opt/codex-external-isolation/results/case-draft/case-draft.json` |
| Stored draft | `proposed_response` starts `DRAFT - NOT SENT`; `labeled_not_sent=1` |
| Review file | `/var/lib/bt-intake-proof/review-BTC-contactus-<thread>-v1.json` |
| Send | **no** `case_send_actions` row for this case; actions 1/2 unchanged |

Do not mark PASS from a prewritten fixture. PASS only if `case-draft.json` has a
real `turn.final_response` from that run.

## Where model execution is recorded / how failure surfaces

- Wire: `/opt/codex-external-isolation/results/case-draft/case-draft-wire.json` (`empty_user_input`, `content_in_user_input`)
- Result: `/opt/codex-external-isolation/results/case-draft/case-draft.json` (`thread_id`, `turn`, or `error`/`traceback`)
- Host log: `case_manager` / drafted `{status, reason}` (`draft_script_missing`, `codex_draft_failed`, `unparseable_draft`)
- Case event: `draft_failed` (case stays visible, `needs_draft`)
- Console: "Inbound is waiting on a draft."

If Docker, image, volume, or ChatGPT login inside `codex-iso-chatgpt-home` is
missing: **BLOCKED**. Refresh with existing
`/opt/codex-external-isolation/scripts/host_chatgpt_login.sh` (ChatGPT device
code in the isolated volume). **No new Gmail OAuth or scopes.**

## After a real model draft: shorter reply, then hold for Brenda

Existing bindings only. ChatGPT interprets speech; backend authorizes.

1. Generate packets (does not send):

```
sudo -u btintake python3 -m bt_intake_proof.cli lead-desk-packets \
  --store /var/lib/bt-intake-proof/receipts.sqlite \
  --case-id BTC-contactus-<thread> \
  --out /tmp/casemgr-draft-packets
```

2. Spoken: "Make that draft shorter."
   **[SIMULATED until the live walkthrough]** → `INTENT=revise_draft` with the
   shorter `DRAFT - NOT SENT` body in `NOTE`, plus the machine binding from
   `desk-case.txt` (do not read nonce/hash to Daniel).

3. Spoken: "Hold this for Brenda."
   → `INTENT=office_owned` `OWNER=brenda` with the **new** binding after revise.

4. Console / `LeadDesk.get_case` must say **Brenda owns this**, not
   "waiting on Daniel". `waiting_on_daniel=false`.

Control mail may appear in the Gmail/iPhone sent UI. That is not a failure
and is not hidden. Keep machine fields out of spoken summaries.

## Inspect destination / prove no customer or proof send

```
sudo -u btintake python3 - <<'PY'
from bt_intake_proof.lead_desk import LeadDesk
from bt_intake_proof.gates import store_path
desk = LeadDesk(store_path())
print(desk.get_case("BTC-contactus-<thread>"))
desk.close()
PY
```

Also: `case_send_actions` for that `case_id` empty; actions 1 and 2 unchanged;
no `BT-DESK-ROUNDTRIP-SEND-E9A8` / Phase E outbound; `would_resend_proof` false.

## Bounded host checks for Codex (no send)

```
test -x /opt/codex-external-isolation/scripts/host_case_draft.sh
docker image inspect bt-ops-codex-isolation:0.154.0
docker volume inspect codex-iso-chatgpt-home
systemctl is-active bt-intake-receiver
```

Do not send the packet. Do not reset SQLite. Do not recover `--execute`.
Do not repeat action 2 `--verify-recipient`.
