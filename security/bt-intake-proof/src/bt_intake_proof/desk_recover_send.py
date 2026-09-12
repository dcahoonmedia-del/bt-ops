"""One-shot recovery for the failed isolated desk send. Does not re-queue or auto-send."""

from __future__ import annotations

import os
from typing import Any

from .bounded_send import execute_action
from .cases import APPROVAL_APPROVED, CaseLayer
from .constants import DESK_SEND_SUBJECT, MAILBOX
from .desk_fresh_case import FRESH_THREAD_ID, PHASE_E_CASE_ID, exact_proof_payload, fresh_case_id
from .intake_mode import MODE_ISOLATED_TEST, requested_mode
from .phasee_constants import STATUS_FAILED
from .send_bind import (
    QUEUED_BY_DESK,
    QUEUED_BY_PHASEE,
    action_row,
    binding_from_action,
    ensure_send_tables,
    payload_sha256,
    provider_gmail_thread_id,
    revalidate_action,
)
from .send_verify import count_exact_outbound

RECOVERY_ACTION_ID = 2
RECOVERY_CASE_ID = fresh_case_id()
RECOVERY_EVENT = "desk_send_recovery_authorized"
ALLOWED_FAILED_DETAILS = frozenset({"http_400", "invalid_gmail_thread_id"})
KNOWN_NO_SEND = frozenset({"failed", "blocked", "rejected"})
UNKNOWN_OR_ACCEPTED = frozenset({"unknown", "attempted", "recovered"})


def isolation_blockers() -> list[str]:
    blockers = []
    if os.environ.get("BT_ALLOW_REAL_CUSTOMER_SENDS") or os.environ.get("BT_ALLOW_CUSTOMER_SEND"):
        blockers.append("customer_sends_enabled")
    if requested_mode() != MODE_ISOLATED_TEST:
        blockers.append("intake_mode_not_isolated")
    return blockers


def _attempts(layer: CaseLayer, action_id: int) -> list[dict[str, Any]]:
    rows = layer.conn.execute(
        "SELECT id, at, result, provider_message_id, detail FROM case_send_attempts WHERE action_id = ? ORDER BY id",
        (action_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _recovery_events(layer: CaseLayer, case_id: str) -> list[dict[str, Any]]:
    rows = layer.conn.execute(
        "SELECT id, at, event_type FROM case_events WHERE case_id = ? AND event_type = ? ORDER BY id",
        (case_id, RECOVERY_EVENT),
    ).fetchall()
    return [dict(row) for row in rows]


def _payload_blockers(action: dict[str, Any]) -> list[str]:
    proof = exact_proof_payload()
    blockers = []
    if action.get("from_addr") != proof["from"] or action.get("from_addr") != MAILBOX:
        blockers.append("from_changed")
    if action.get("to_addr") != proof["to"]:
        blockers.append("to_changed")
    if action.get("subject") != DESK_SEND_SUBJECT or action.get("subject") != proof["subject"]:
        blockers.append("subject_changed")
    if str(action.get("body") or "").strip() != str(proof["body"] or "").strip():
        blockers.append("body_changed")
    if (action.get("cc_json") or "[]") not in ("[]", "null"):
        blockers.append("cc_present")
    if (action.get("bcc_json") or "[]") not in ("[]", "null"):
        blockers.append("bcc_present")
    if action.get("thread_id") != FRESH_THREAD_ID:
        blockers.append("thread_id_changed")
    return blockers


def inspect_failed_desk_send(
    layer: CaseLayer,
    *,
    action_id: int = RECOVERY_ACTION_ID,
    case_id: str = RECOVERY_CASE_ID,
) -> dict[str, Any]:
    """Validate failed action 2 can be retried once. Does not send or mutate."""
    ensure_send_tables(layer)
    blockers = isolation_blockers()
    action = action_row(layer, action_id)
    case = layer.get_case(case_id)
    attempts = _attempts(layer, action_id) if action else []
    events = _recovery_events(layer, case_id)
    if action_id == 1 or case_id == PHASE_E_CASE_ID:
        blockers.append("phase_e_leftover_forbidden")
    if not action:
        blockers.append("unknown_action")
        return _inspection(action_id, case_id, None, case, attempts, events, blockers)
    if str(action.get("case_id") or "") != case_id:
        blockers.append("case_mismatch")
    if str(action.get("queued_by") or "") == QUEUED_BY_PHASEE:
        blockers.append("phase_e_leftover_forbidden")
    elif str(action.get("queued_by") or "") != QUEUED_BY_DESK:
        blockers.append("not_desk_control")
    if str(action.get("status") or "") != STATUS_FAILED:
        blockers.append("status_not_failed")
    if int(action.get("consumed") or 0):
        blockers.append("already_consumed")
    if action.get("locked_at"):
        blockers.append("action_locked")
    if not case:
        blockers.append("unknown_case")
    elif case.get("approval_state") != APPROVAL_APPROVED:
        blockers.append("not_approved")
    blockers.extend(_payload_blockers(action))
    blockers.extend(revalidate_action(layer, action))
    if payload_sha256(binding_from_action(action)) != action.get("payload_sha256"):
        blockers.append("payload_hash_mismatch")
    if events:
        blockers.append("recovery_already_authorized")
    if not attempts:
        blockers.append("missing_failed_attempt")
    for attempt in attempts:
        result = str(attempt.get("result") or "")
        detail = str(attempt.get("detail") or "")
        if attempt.get("provider_message_id"):
            blockers.append("provider_message_id_present")
        if result in UNKNOWN_OR_ACCEPTED:
            blockers.append("provider_or_unknown_outcome")
        if result not in KNOWN_NO_SEND:
            blockers.append("unexpected_attempt_result")
        if result == "failed" and detail not in ALLOWED_FAILED_DETAILS:
            blockers.append("unexpected_fail_reason")
    if attempts and not any(
        str(item.get("result") or "") == "failed"
        and str(item.get("detail") or "") in ALLOWED_FAILED_DETAILS
        for item in attempts
    ):
        blockers.append("missing_allowlisted_failure")
    if len([item for item in attempts if str(item.get("result") or "") == "failed"]) > 1:
        blockers.append("prior_recovery_attempt")
    unique = []
    for item in blockers:
        if item not in unique:
            unique.append(item)
    return _inspection(action_id, case_id, action, case, attempts, events, unique)


def _inspection(
    action_id: int,
    case_id: str,
    action: dict[str, Any] | None,
    case: dict[str, Any] | None,
    attempts: list[dict[str, Any]],
    events: list[dict[str, Any]],
    blockers: list[str],
) -> dict[str, Any]:
    binding = binding_from_action(action) if action else None
    provider_thread = provider_gmail_thread_id((action or {}).get("thread_id"))
    return {
        "ok": not blockers,
        "mode": "inspect",
        "executed": False,
        "recovery_authorized": not blockers,
        "action_id": action_id,
        "case_id": case_id,
        "status": (action or {}).get("status"),
        "consumed": int((action or {}).get("consumed") or 0),
        "queued_by": (action or {}).get("queued_by"),
        "draft_version": (action or {}).get("draft_version"),
        "control_gmail_id": (action or {}).get("control_gmail_id"),
        "approval_state": (case or {}).get("approval_state"),
        "owner": (case or {}).get("owner"),
        "hold": int((case or {}).get("hold") or 0),
        "payload_sha256": (action or {}).get("payload_sha256"),
        "thread_id": (action or {}).get("thread_id"),
        "gmail_request_includes_thread_id": bool(provider_thread),
        "omit_gmail_thread_id": provider_thread is None,
        "host_loop_would_select": str((action or {}).get("status") or "") == "queued"
        and str((action or {}).get("queued_by") or "") == QUEUED_BY_DESK
        and int((action or {}).get("consumed") or 0) == 0,
        "attempts": [
            {
                "id": item.get("id"),
                "at": item.get("at"),
                "result": item.get("result"),
                "detail": item.get("detail"),
                "provider_message_id": item.get("provider_message_id"),
            }
            for item in attempts
        ],
        "recovery_events": len(events),
        "exact_user_visible": exact_proof_payload() if action else None,
        "binding_thread_id_unchanged": (action or {}).get("thread_id") == FRESH_THREAD_ID,
        "blockers": blockers,
        "existing_approval_reused": True,
        "rebinding_required": False,
        "customer_sends": "off",
    }


def recover_failed_desk_send(
    layer: CaseLayer,
    *,
    action_id: int = RECOVERY_ACTION_ID,
    case_id: str = RECOVERY_CASE_ID,
    execute: bool = False,
    send_transport: Any | None = None,
    verify_transport: Any | None = None,
) -> dict[str, Any]:
    """Dry-run by default. --execute calls execute_action once and never re-queues."""
    inspection = inspect_failed_desk_send(layer, action_id=action_id, case_id=case_id)
    snapshot = {
        "payload_sha256": inspection.get("payload_sha256"),
        "thread_id": inspection.get("thread_id"),
        "attempt_ids": [item.get("id") for item in inspection.get("attempts") or []],
        "approval_state": inspection.get("approval_state"),
    }
    sent_check = None
    if verify_transport is not None and inspection.get("payload_sha256"):
        action = action_row(layer, action_id)
        sent_check = count_exact_outbound(binding_from_action(action), verify_transport)
        inspection["sent_check"] = {
            "subject_hits": sent_check["subject_hits"],
            "exact_matches": sent_check["exact_matches"],
            "ambiguous": sent_check["ambiguous"],
        }
    elif execute:
        inspection["blockers"] = list(inspection.get("blockers") or [])
        if "verify_unavailable" not in inspection["blockers"]:
            inspection["blockers"].append("verify_unavailable")
        inspection["ok"] = False
        inspection["recovery_authorized"] = False
    if sent_check is not None and (sent_check["exact_matches"] or sent_check["subject_hits"] or sent_check["ambiguous"]):
        inspection["blockers"] = list(inspection.get("blockers") or [])
        inspection["blockers"].append("provider_send_or_unknown_outbound")
        inspection["ok"] = False
        inspection["recovery_authorized"] = False
    inspection["preserved"] = snapshot
    if not execute:
        inspection["mode"] = "dry_run"
        inspection["would_execute"] = bool(inspection["ok"])
        return inspection
    if not inspection["ok"]:
        inspection["mode"] = "execute_blocked"
        inspection["executed"] = False
        return inspection
    if send_transport is None:
        inspection["ok"] = False
        inspection["mode"] = "execute_blocked"
        inspection["blockers"] = list(inspection.get("blockers") or []) + ["send_transport_missing"]
        inspection["recovery_authorized"] = False
        return inspection
    layer.add_event(
        case_id,
        RECOVERY_EVENT,
        action_id=action_id,
        payload_sha256=snapshot["payload_sha256"],
        thread_id=snapshot["thread_id"],
        existing_approval_reused=True,
        requeued=False,
    )
    executed = execute_action(layer, action_id, send_transport, owner="desk-recover-once")
    from .desk_bridge import enqueue_send_followup

    enqueue_send_followup(layer, executed)
    after = action_row(layer, action_id)
    inspection["mode"] = "execute"
    inspection["executed"] = True
    inspection["execute_result"] = {
        "ok": executed.get("ok"),
        "reason": executed.get("reason"),
        "status": executed.get("status"),
        "unknown": executed.get("unknown"),
        "provider_message_id": executed.get("provider_message_id"),
        "consumed": executed.get("consumed"),
    }
    inspection["ok"] = bool(executed.get("ok"))
    inspection["binding_preserved"] = bool(
        after
        and after.get("payload_sha256") == snapshot["payload_sha256"]
        and after.get("thread_id") == snapshot["thread_id"]
        and after.get("subject") == DESK_SEND_SUBJECT
    )
    inspection["requeued"] = str((after or {}).get("status") or "") == "queued"
    inspection["host_loop_would_select"] = False
    inspection["attempts"] = [
        {
            "id": item.get("id"),
            "at": item.get("at"),
            "result": item.get("result"),
            "detail": item.get("detail"),
            "provider_message_id": item.get("provider_message_id"),
        }
        for item in _attempts(layer, action_id)
    ]
    return inspection


def configured_contactus_sent_verify():
    """Readonly contactus Sent lookup. Fail closed if unavailable. Does not send."""
    try:
        from .live_google import contactus_gmail
        from .send_verify import ContactusReadonlySentVerify

        return ContactusReadonlySentVerify(contactus_gmail())
    except Exception:
        return None
