"""Daniel iPhone review packet. Phase C approval does not send. Phase E shows the exact send packet."""

from __future__ import annotations

from typing import Any

from .cases import MARKER_APPROVE, MARKER_CHANGES, MARKER_NONE, MARKER_REVIEW, _loads
from .phasee import review_footer
from .phasee_constants import PHASEE_FROM, PHASEE_SUBJECT, PHASEE_TO
from .send_bind import is_phasee_body


def format_review_email(packet: dict[str, Any]) -> dict[str, str]:
    case = packet["case"]
    draft = packet.get("draft") or {}
    inbound = packet.get("inbound") or {}
    case_id = case["case_id"]
    version = int(draft.get("version") or case.get("draft_version") or 0)
    facts = _loads(draft.get("known_facts_json") or [])
    missing = _loads(draft.get("missing_info_json") or [])
    if isinstance(facts, str):
        facts = [facts]
    if isinstance(missing, str):
        missing = [missing]
    fact_lines = "\n".join(f"- {item}" for item in facts) or "- (none listed)"
    missing_lines = "\n".join(f"- {item}" for item in missing) or "- (none listed)"
    proposed = draft.get("proposed_response") or "(no draft yet)"
    phasee = is_phasee_body(proposed)
    intro = (
        "This email is for Daniel's iPhone review. Approval of this exact version authorizes one bounded internal send from contactus@ to daniel@ only. It does not send customer mail."
        if phasee
        else "This email is for Daniel's iPhone review. Approval does not send anything to a customer."
    )
    phasee_block = (
        f"""
--- Exact Phase E send packet ---
From: {PHASEE_FROM}
To: {PHASEE_TO}
CC: (none)
BCC: (none)
Subject: {PHASEE_SUBJECT}
Attachments: none
Links: none
Timing: immediate supervised test
Gmail thread: {case.get("thread_id") or "(none)"}
Latest inbound: {case.get("latest_inbound_message_id") or "(none)"}
Draft version: {version}

Exact body:
{proposed}
"""
        if phasee
        else ""
    )
    fw = packet.get("fieldwork") or {}
    fw_evidence = _loads(fw.get("evidence_json") or {})
    if not isinstance(fw_evidence, dict):
        fw_evidence = {}
    fw_status = fw.get("match_status") or fw_evidence.get("status") or "not_run"
    fw_label = fw_evidence.get("source_label") or "FIELDWORK_FIXTURE_VERIFIED"
    fw_block = f"""--- Fieldwork (read-only fixture) ---
Label: {fw_label}
Not live Fieldwork. Fixture label only.
Match: {fw_status}
Confidence: {fw.get("confidence") or fw_evidence.get("confidence")}
{fw_label} customer ID: {fw.get("customer_id") or "(none)"}
{fw_label} location ID: {fw.get("location_id") or "(none)"}
Identity: {fw_evidence.get("identity_kind") or "(none)"}
Pipeline lead: {(fw_evidence.get("pipeline") or {}).get("lead_id") if isinstance(fw_evidence.get("pipeline"), dict) else "(none)"}
Booking state: {fw_evidence.get("booking_state") or "(none)"}
Active agreement: {fw.get("active_agreement_json") or fw_evidence.get("active_agreement") or "(none)"}
Upcoming work orders: {fw.get("upcoming_work_orders_json") or fw_evidence.get("upcoming_work_orders") or "[]"}
Last service: {fw.get("last_service_json") or fw_evidence.get("last_service") or "(none)"}
Office/hold: {fw_evidence.get("office_context") or "(none)"}
Retrieved: {fw.get("retrieved_at") or fw_evidence.get("retrieved_at") or "(none)"}
Write attempted: {fw.get("write_attempted", 0)}
A proposed Fieldwork write is not a verified booking. Distinguish {fw_label} from CUSTOMER REPORTED from AI INFERENCE.
"""
    body = f"""B&T Case Manager review (internal). {MARKER_REVIEW}

CASE={case_id} DRAFT={version}

{intro}

--- Case ---
Case ID: {case_id}
Stage: {case.get("stage")}
Approval state: {case.get("approval_state")}
Inbound class: {case.get("inbound_class")}
Thread: {case.get("thread_id")}
Latest inbound: {case.get("latest_inbound_message_id")}
Draft version: {version}
Next action: {case.get("next_action")}

--- Original inbound ---
From: {inbound.get("sender")}
Subject: {inbound.get("subject")}
Received: {inbound.get("gmail_received_at")}
Classification: {inbound.get("classification")}

{inbound.get("body_text") or "(body not stored)"}

{fw_block}
--- Codex summary ---
Classification: {draft.get("classification")}
Channel: {draft.get("channel")}
Recommended next step: {draft.get("recommended_next_step")}
Needs Daniel judgment: {draft.get("judgment_needed")}
Reasoning: {draft.get("reasoning_summary")}

Known facts:
{fact_lines}

Still missing:
{missing_lines}

--- Exact proposed reply ---
{proposed}
{phasee_block}

--- Decisions (reply to contactus@ and keep the marker) ---
Approve:
  {MARKER_APPROVE}
  CASE={case_id} DRAFT={version}

Request changes (add your notes under the marker):
  {MARKER_CHANGES}
  CASE={case_id} DRAFT={version}

No response needed:
  {MARKER_NONE}
  CASE={case_id} DRAFT={version}

{review_footer(phasee)}
"""
    return {
        "to": "daniel@btpestcontrol.com",
        "cc": "contactus@btpestcontrol.com",
        "subject": f"{MARKER_REVIEW} {case_id} v{version}",
        "body": body,
    }
