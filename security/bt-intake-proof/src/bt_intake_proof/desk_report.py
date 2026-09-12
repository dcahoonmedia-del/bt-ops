"""Inspect or enqueue an accurate send-stage result. Does not resend the proof."""

from __future__ import annotations

from typing import Any

from .desk_bridge import enqueue_send_outcome
from .desk_fresh_case import PHASE_E_CASE_ID, fresh_case_id
from .desk_outcome import inspect_action_outcome
from .desk_recover_send import RECOVERY_ACTION_ID, RECOVERY_CASE_ID, isolation_blockers
from .send_bind import QUEUED_BY_PHASEE, action_row, binding_from_action
from .send_verify import count_exact_inbox, count_exact_outbound, verify_recipient, verify_sent


def report_desk_send_outcome(
    layer: Any,
    *,
    action_id: int = RECOVERY_ACTION_ID,
    case_id: str = RECOVERY_CASE_ID,
    verify_sent_live: bool = False,
    verify_recipient_live: bool = False,
    enqueue_result: bool = False,
    sent_transport: Any | None = None,
    inbox_transport: Any | None = None,
) -> dict[str, Any]:
    """Read current stages. Optional live verify. Never forges receipt or resends the proof."""
    blockers = isolation_blockers()
    if case_id == PHASE_E_CASE_ID:
        blockers.append("phase_e_leftover_forbidden")
    action = action_row(layer, action_id)
    if not action:
        return {"ok": False, "reason": "unknown_action", "blockers": blockers + ["unknown_action"]}
    if str(action.get("case_id") or "") != case_id:
        blockers.append("case_mismatch")
    if str(action.get("queued_by") or "") == QUEUED_BY_PHASEE:
        blockers.append("phase_e_leftover_forbidden")
    report = inspect_action_outcome(layer, action_id)
    report["case_id_expected"] = case_id
    report["fresh_case_id"] = fresh_case_id()
    report["blockers"] = blockers
    report["would_resend_proof"] = False
    report["mode"] = "inspect"
    if blockers:
        report["ok"] = False
        return report
    binding = binding_from_action(action)
    if sent_transport is not None:
        report["contactus_sent"] = count_exact_outbound(binding, sent_transport)
    if inbox_transport is not None:
        report["daniel_inbox"] = count_exact_inbox(binding, inbox_transport)
    if verify_sent_live:
        if sent_transport is None:
            report["ok"] = False
            report["blockers"] = ["sent_verify_unavailable"]
            return report
        report["sent_verify"] = verify_sent(layer, action_id, sent_transport)
        kept = {key: report.get(key) for key in ("contactus_sent", "daniel_inbox", "sent_verify")}
        report.update(inspect_action_outcome(layer, action_id))
        report.update({key: value for key, value in kept.items() if value is not None})
        report["would_resend_proof"] = False
        if not report["sent_verify"].get("ok"):
            blockers.append("sent_verify_failed")
        report["blockers"] = list(blockers)
    if verify_recipient_live:
        if inbox_transport is None:
            report["ok"] = False
            report["blockers"] = list(report.get("blockers") or []) + ["recipient_verify_unavailable"]
            return report
        current = inspect_action_outcome(layer, action_id)
        if not current.get("sent_verified"):
            report["ok"] = False
            report["blockers"] = list(report.get("blockers") or []) + ["sent_not_verified"]
            report["recipient_receipt_not_claimed_from_api"] = True
            return report
        report["recipient_verify"] = verify_recipient(layer, action_id, inbox_transport)
        kept = {
            key: report.get(key)
            for key in ("contactus_sent", "daniel_inbox", "sent_verify", "recipient_verify")
        }
        report.update(inspect_action_outcome(layer, action_id))
        report.update({key: value for key, value in kept.items() if value is not None})
        report["would_resend_proof"] = False
        if not report["recipient_verify"].get("ok"):
            blockers.append("recipient_verify_failed")
        report["blockers"] = list(blockers)
    if enqueue_result:
        queued = enqueue_send_outcome(layer, action_id)
        report["outbox"] = queued
        report["mode"] = "enqueue_result"
        if not queued.get("ok") or queued.get("reason") == "outbox_insert_ignored":
            blockers.append("outbox_enqueue_failed")
        elif queued.get("enqueued") or queued.get("already_reported") or queued.get("deferred") or queued.get("updated_pending"):
            pass
        else:
            blockers.append("outbox_enqueue_failed")
        report["blockers"] = list(blockers)
    report["recipient_receipt_not_claimed_from_api"] = not report.get("recipient_receipt_verified")
    report["blockers"] = list(blockers)
    report["ok"] = not blockers
    return report
