"""Honest send-stage reporting. Provider accept is not Sent or recipient proof."""

from __future__ import annotations

from typing import Any

from .phasee_constants import (
    STATUS_ATTEMPTED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RECEIPT_VERIFIED,
    STATUS_REJECTED,
    STATUS_SENT_VERIFIED,
    STATUS_UNKNOWN,
)

STAGE_QUEUED = "queued"
STAGE_FAILED = "failed"
STAGE_UNKNOWN = "unknown"
STAGE_PROVIDER_ACCEPTED = "provider_accepted"
STAGE_SENT_VERIFIED = "sent_verified"
STAGE_RECIPIENT_RECEIPT = "recipient_receipt_verified"

HUMAN = {
    STAGE_FAILED: "The isolated internal send did not complete. Nothing further was retried.",
    STAGE_UNKNOWN: "The isolated internal send outcome is unknown. It will not be retried automatically.",
    STAGE_PROVIDER_ACCEPTED: (
        "Gmail accepted that isolated internal message. "
        "Contactus Sent is not yet independently verified. This is not recipient receipt."
    ),
    STAGE_SENT_VERIFIED: (
        "Contactus Sent independently verified that exact isolated message once. "
        "This is not recipient-inbox proof."
    ),
    STAGE_RECIPIENT_RECEIPT: (
        "Daniel's mailbox independently verified that exact isolated message once."
    ),
    STAGE_QUEUED: "That version is approved and queued. This is not a send result.",
}


def action_send_stage(action: dict[str, Any] | None, *, executed: dict[str, Any] | None = None) -> str:
    status = str((action or {}).get("status") or "")
    if status == STATUS_RECEIPT_VERIFIED:
        return STAGE_RECIPIENT_RECEIPT
    if status == STATUS_SENT_VERIFIED:
        return STAGE_SENT_VERIFIED
    if status == STATUS_UNKNOWN or (executed or {}).get("unknown"):
        return STAGE_UNKNOWN
    if status in {STATUS_FAILED, STATUS_REJECTED}:
        return STAGE_FAILED
    if status == STATUS_ATTEMPTED or (executed or {}).get("ok"):
        return STAGE_PROVIDER_ACCEPTED
    if status == STATUS_QUEUED:
        return STAGE_QUEUED
    if executed and not executed.get("ok") and not executed.get("unknown"):
        return STAGE_FAILED
    return STAGE_UNKNOWN if status else STAGE_QUEUED


def stage_claims(stage: str) -> dict[str, bool]:
    return {
        "provider_accepted": stage in {STAGE_PROVIDER_ACCEPTED, STAGE_SENT_VERIFIED, STAGE_RECIPIENT_RECEIPT},
        "sent_verified": stage in {STAGE_SENT_VERIFIED, STAGE_RECIPIENT_RECEIPT},
        "recipient_receipt_verified": stage == STAGE_RECIPIENT_RECEIPT,
    }


def outcome_payload(
    action: dict[str, Any],
    *,
    executed: dict[str, Any] | None = None,
    nonce: str | None = None,
) -> dict[str, Any]:
    stage = action_send_stage(action, executed=executed)
    claims = stage_claims(stage)
    executed = executed or {}
    ok = stage in {STAGE_PROVIDER_ACCEPTED, STAGE_SENT_VERIFIED, STAGE_RECIPIENT_RECEIPT}
    return {
        "ok": ok,
        "intent": "approve_and_send_current",
        "case_id": action.get("case_id"),
        "draft_version": action.get("draft_version"),
        "control_gmail_id": action.get("control_gmail_id"),
        "nonce": nonce,
        "send_queued": True,
        "execute_send": True,
        "send_stage": stage,
        "send_status": action.get("status") or executed.get("status") or executed.get("reason"),
        "provider_message_id": executed.get("provider_message_id") or _latest_provider_id(action),
        "provider_accepted": claims["provider_accepted"],
        "sent_verified": claims["sent_verified"],
        "recipient_receipt_verified": claims["recipient_receipt_verified"],
        "reason": executed.get("reason") or "",
        "human": HUMAN[stage],
    }


def _latest_provider_id(action: dict[str, Any]) -> str | None:
    return action.get("provider_message_id")


def inspect_verifications(layer: Any, action_id: int) -> list[dict[str, Any]]:
    rows = layer.conn.execute(
        """
        SELECT id, at, kind, result, provider_message_id
        FROM case_send_verifications
        WHERE action_id = ?
        ORDER BY id
        """,
        (action_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def inspect_action_outcome(layer: Any, action_id: int) -> dict[str, Any]:
    from .send_bind import action_row

    action = action_row(layer, action_id)
    if not action:
        return {"ok": False, "reason": "unknown_action", "action_id": action_id}
    stage = action_send_stage(action)
    claims = stage_claims(stage)
    return {
        "ok": True,
        "action_id": action_id,
        "case_id": action.get("case_id"),
        "status": action.get("status"),
        "consumed": int(action.get("consumed") or 0),
        "send_stage": stage,
        "provider_accepted": claims["provider_accepted"],
        "sent_verified": claims["sent_verified"],
        "recipient_receipt_verified": claims["recipient_receipt_verified"],
        "control_gmail_id": action.get("control_gmail_id"),
        "payload_sha256": action.get("payload_sha256"),
        "verifications": inspect_verifications(layer, action_id),
        "would_resend_proof": False,
        "customer_sends": "off",
    }
