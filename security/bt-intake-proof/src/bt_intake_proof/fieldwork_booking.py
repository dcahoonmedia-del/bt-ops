"""Booking state is not identity. A proposed write is not a verified work order."""

from __future__ import annotations

from typing import Any

LABEL_FIXTURE = "FIELDWORK_FIXTURE_VERIFIED"
LABEL_LIVE = "LIVE_FIELDWORK_VERIFIED"

STATE_NONE = "no_work_order"
STATE_PENDING = "pending_write_not_verified"
STATE_SOLD = "sold"
STATE_SCHEDULED = "scheduled"
STATE_COMPLETED = "completed"

_COMPLETED = {"completed", "done", "finished"}
_SOLD = {"sold"}
_SCHEDULED = {"scheduled", "confirmed", "dispatched"}


def booking_state_from_records(
    work_orders: list[dict[str, Any]] | None,
    *,
    proposed_write: dict[str, Any] | None = None,
    snapshot_state: str | None = None,
) -> str:
    if snapshot_state in {STATE_NONE, STATE_PENDING, STATE_SOLD, STATE_SCHEDULED, STATE_COMPLETED}:
        if snapshot_state == STATE_PENDING or (proposed_write and not work_orders):
            return STATE_PENDING
        if snapshot_state == STATE_NONE and not work_orders:
            return STATE_NONE
    for wo in work_orders or []:
        status = str(wo.get("status") or wo.get("state") or "").lower()
        if status in _COMPLETED or wo.get("completed") is True:
            return STATE_COMPLETED
    for wo in work_orders or []:
        status = str(wo.get("status") or wo.get("state") or "").lower()
        if status in _SCHEDULED or wo.get("scheduled") is True:
            return STATE_SCHEDULED
    for wo in work_orders or []:
        status = str(wo.get("status") or wo.get("state") or "").lower()
        if status in _SOLD or wo.get("sold") is True:
            return STATE_SOLD
    if proposed_write:
        return STATE_PENDING
    return STATE_NONE


def verified_work_order(work_orders: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    for wo in work_orders or []:
        status = str(wo.get("status") or wo.get("state") or "").lower()
        if status in _COMPLETED | _SCHEDULED | _SOLD or wo.get("id"):
            return {
                "id": wo.get("id"),
                "status": wo.get("status") or wo.get("state"),
                "starts_at": wo.get("starts_at") or wo.get("start_time"),
                "ends_at": wo.get("ends_at"),
                "technician": wo.get("technician"),
                "amount": wo.get("amount"),
                "sold": bool(wo.get("sold") or status in _SOLD),
                "scheduled": bool(wo.get("scheduled") or status in _SCHEDULED),
                "completed": bool(wo.get("completed") or status in _COMPLETED),
            }
    return None


def operational_context(evidence: dict[str, Any]) -> dict[str, Any]:
    wos = list(evidence.get("upcoming_work_orders") or [])
    if evidence.get("last_service"):
        wos.append(evidence["last_service"])
    proposed = evidence.get("proposed_write")
    state = evidence.get("booking_state") or booking_state_from_records(
        wos, proposed_write=proposed, snapshot_state=evidence.get("snapshot_booking_state")
    )
    pipeline = evidence.get("pipeline") or {}
    return {
        "source_label": evidence.get("source_label") or LABEL_FIXTURE,
        "live": False,
        "identity_kind": evidence.get("identity_kind") or ("pipeline_lead" if pipeline else "customer"),
        "customer_id": evidence.get("customer_id"),
        "pipeline_lead_id": pipeline.get("lead_id"),
        "opportunity_id": pipeline.get("opportunity_id"),
        "pipeline_stage": pipeline.get("stage"),
        "setup_checklist": pipeline.get("setup_checklist"),
        "booking_state": state,
        "verified_work_order": verified_work_order(wos) if state not in {STATE_NONE, STATE_PENDING} else None,
        "proposed_write": proposed,
        "customer_email_reported_sent": bool(evidence.get("customer_email_reported_sent")),
        "sold": state == STATE_SOLD,
        "scheduled": state == STATE_SCHEDULED,
        "completed": state == STATE_COMPLETED,
    }


def draft_booking_guidance(evidence: dict[str, Any]) -> dict[str, Any]:
    ops = operational_context(evidence)
    state = ops["booking_state"]
    label = ops["source_label"]
    if state in {STATE_NONE, STATE_PENDING}:
        return {
            "source_label": label,
            "may_confirm_booking": False,
            "may_cite_work_order": False,
            "do_not_infer_customer_confirmation": True,
            "treat_pending_write_as_verified": False,
            "reason": "proposed_or_missing_write_is_not_verified_booking",
            "booking_state": state,
            "sold": False,
            "scheduled": False,
            "completed": False,
            "draft_must_not": [
                "say the customer is booked",
                "treat a sent customer email as booking proof",
                "treat a proposed Fieldwork write as a work order",
            ],
        }
    return {
        "source_label": label,
        "may_confirm_booking": state in {STATE_SCHEDULED, STATE_COMPLETED},
        "may_cite_work_order": True,
        "do_not_infer_customer_confirmation": False,
        "treat_pending_write_as_verified": False,
        "reason": "verified_work_order_present",
        "booking_state": state,
        "sold": ops["sold"],
        "scheduled": ops["scheduled"],
        "completed": ops["completed"],
        "draft_must_not": [
            "collapse sold/scheduled/completed",
            "call a scheduled job completed",
        ],
        "verified_work_order": ops["verified_work_order"],
    }
