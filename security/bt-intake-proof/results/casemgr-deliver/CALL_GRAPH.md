# Call graph: why the phone inquiry had no CASE packet

Derived from deployed source `c41404e75bbc768d034814a5ec3bca90ad927b6e`.
This is a **source-path** confirmation. Live host stages are **BLOCKED** from this VM
(no gcloud, no SSH private key, no new access requested).

## Host loop (existing)

`cloud_host.run_once` / `serve`:

1. recover / watch / `receive_once`
2. `dispatch_pending`
3. `process_cases`
4. `finish_desk_roundtrip` → `deliver_pending_desk_mail` + desk-queued sends

## process_cases (before this change)

1. `sync_cases` → `CaseLayer.sync_eligible_receipts`
2. `process_pending_controls` (RESULT / control CASE consolidation)
3. `draft_pending_cases`
4. `queue_approved_phasee_sends` (Phase E only)

`BT-INTAKE-PROOF-CASEMGR-PHONE-7C92` is a normal CASEMGR lead (`marker_kind=lead`).
Eligibility accepts daniel@ → contactus@ with that marker.

## draft_pending_cases (before this change)

- Phase E / desk-roundtrip: install exact send draft, no model
- **Normal CASEMGR:** `run_codex_draft` → `save_draft` → write
  `review-<case>-vN.json` beside the store
- **No call** to `enqueue_on_demand_case` or `desk_result_outbox`

So a successful model draft can exist on disk / in SQLite with **zero** CASE mail.

## What already existed (reused)

- `desk_packets.format_case_email` + `compute_packet_binding` / `format_binding_block`
- `desk_bridge._fresh_case_email`
- `desk_result_outbox` unique `(control_gmail_id, kind)`
- `deliver_pending_desk_mail` (contactus → daniel, unknown does not retry)
- `finish_desk_roundtrip` drains that outbox

## Live ID `1a096ffa404426f1`

| Stage | This VM |
| --- | --- |
| Receipts / dispatch / case / draft / events / outbox | **BLOCKED** — no authorized host access |
| Inquiry resend | **not done** |
| Explicit recovery | **not executed** |

If the host already drafted that inbound, the new forward path will **not**
backfill it. Use the bounded recovery command after deploy review.
