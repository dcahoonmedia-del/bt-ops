"""Daniel iPhone review packet. Approval is recorded state only. No customer send."""

from __future__ import annotations

from typing import Any

from .cases import MARKER_APPROVE, MARKER_CHANGES, MARKER_NONE, MARKER_REVIEW, _loads


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
    body = f"""B&T Case Manager review (internal). {MARKER_REVIEW}

CASE={case_id} DRAFT={version}

This email is for Daniel's iPhone review. Approval does not send anything to a customer.

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

Approval is recorded only. It will not send a customer message.
"""
    return {
        "to": "daniel@btpestcontrol.com",
        "cc": "contactus@btpestcontrol.com",
        "subject": f"{MARKER_REVIEW} {case_id} v{version}",
        "body": body,
    }
