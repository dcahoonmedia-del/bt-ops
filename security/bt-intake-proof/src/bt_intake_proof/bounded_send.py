"""Separate sender. Codex has no Gmail send. Executes one stored approval only."""

from __future__ import annotations

import base64
from email.message import EmailMessage
from typing import Any, Protocol

from .cases import CaseLayer
from .phasee_constants import STATUS_ATTEMPTED, STATUS_FAILED, STATUS_REJECTED, STATUS_UNKNOWN
from .constants import ALLOWED_SENDER, MAILBOX
from .send_bind import (
    QUEUED_BY_DESK,
    action_row,
    binding_from_action,
    ensure_send_tables,
    mark_action,
    record_attempt,
    revalidate_action,
)
from .store import utc_now


class SendTransport(Protocol):
    def send_exact(self, binding: dict[str, Any]) -> dict[str, Any]:
        """Submit only the stored payload. Must not alter subject/body/recipients."""


class MemorySendTransport:
    def __init__(self, *, timeout: bool = False, fail: bool = False) -> None:
        self.sent: list[dict[str, Any]] = []
        self.timeout = timeout
        self.fail = fail
        self.send_count = 0

    def send_exact(self, binding: dict[str, Any]) -> dict[str, Any]:
        self.send_count += 1
        if self.timeout:
            return {"ok": False, "unknown": True, "reason": "timeout"}
        if self.fail:
            return {"ok": False, "unknown": False, "reason": "provider_failed"}
        mid = f"mem-{len(self.sent) + 1}"
        self.sent.append({**binding, "provider_message_id": mid})
        return {"ok": True, "unknown": False, "provider_message_id": mid}

    def send_internal_desk(self, mail: dict[str, Any]) -> dict[str, Any]:
        return self.send_exact(
            {
                "from_addr": mail.get("from_addr") or MAILBOX,
                "to_addr": mail.get("to") or mail.get("to_addr") or ALLOWED_SENDER,
                "subject": mail.get("subject") or "",
                "body": mail.get("body") or "",
                "thread_id": mail.get("thread_id") or "",
            }
        )


class MissingContactusSendTransport:
    """Live contactus send is unavailable without a dedicated send token. Intake readonly is not used."""

    def send_exact(self, binding: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": False,
            "unknown": False,
            "blocked": True,
            "reason": "contactus_send_token_not_configured",
        }

    def send_internal_desk(self, mail: dict[str, Any]) -> dict[str, Any]:
        return self.send_exact(mail)


def mime_from_binding(binding: dict[str, Any]) -> bytes:
    msg = EmailMessage()
    msg["From"] = binding["from_addr"]
    msg["To"] = binding["to_addr"]
    msg["Subject"] = binding["subject"]
    msg.set_content(binding["body"])
    return msg.as_bytes()


def raw_b64(binding: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(mime_from_binding(binding)).decode("ascii")


def execute_action(layer: CaseLayer, action_id: int, transport: SendTransport, *, owner: str = "phasee-sender") -> dict[str, Any]:
    now = utc_now()
    locked = layer.conn.execute(
        """
        UPDATE case_send_actions
        SET locked_at = ?, lock_owner = ?
        WHERE id = ? AND consumed = 0 AND locked_at IS NULL
        """,
        (now, owner, action_id),
    )
    if locked.rowcount != 1:
        row = action_row(layer, action_id)
        reason = "already_consumed" if row and int(row.get("consumed") or 0) else "lock_failed"
        return {"ok": False, "reason": reason, "action_id": action_id}
    action = action_row(layer, action_id)
    assert action is not None
    reasons = revalidate_action(layer, action)
    if reasons:
        mark_action(layer, action_id, status=STATUS_REJECTED, locked_at=None, lock_owner=None)
        record_attempt(layer, action_id, "rejected", detail=",".join(reasons))
        layer.add_event(action["case_id"], "phasee_send_rejected", reasons=reasons)
        return {"ok": False, "reason": "invalid_approval", "reasons": reasons, "action_id": action_id}

    binding = binding_from_action(action)
    result = transport.send_exact(binding)
    if result.get("blocked"):
        mark_action(layer, action_id, status=STATUS_FAILED, locked_at=None, lock_owner=None, consumed=0)
        record_attempt(layer, action_id, "blocked", detail=str(result.get("reason")))
        return {"ok": False, "blocked": True, "reason": result.get("reason"), "action_id": action_id}
    if result.get("unknown"):
        mark_action(layer, action_id, status=STATUS_UNKNOWN, consumed=1, locked_at=None, lock_owner=None)
        record_attempt(layer, action_id, "unknown", detail=str(result.get("reason")))
        layer.add_event(action["case_id"], "phasee_send_unknown", reason=result.get("reason"))
        return {"ok": False, "unknown": True, "reason": result.get("reason"), "action_id": action_id, "consumed": True, "resent": False}
    if not result.get("ok"):
        mark_action(layer, action_id, status=STATUS_FAILED, locked_at=None, lock_owner=None, consumed=0)
        record_attempt(layer, action_id, "failed", detail=str(result.get("reason")))
        return {"ok": False, "reason": result.get("reason"), "action_id": action_id}

    mark_action(
        layer,
        action_id,
        status=STATUS_ATTEMPTED,
        consumed=1,
        locked_at=None,
        lock_owner=None,
    )
    record_attempt(layer, action_id, "attempted", provider_message_id=result.get("provider_message_id"))
    layer.add_event(
        action["case_id"],
        "phasee_send_attempted",
        provider_message_id=result.get("provider_message_id"),
        consumed=True,
    )
    return {
        "ok": True,
        "action_id": action_id,
        "status": STATUS_ATTEMPTED,
        "provider_message_id": result.get("provider_message_id"),
        "consumed": True,
    }


def execute_due_sends(layer: CaseLayer, transport: SendTransport) -> list[dict[str, Any]]:
    rows = layer.conn.execute(
        "SELECT id FROM case_send_actions WHERE consumed = 0 AND status = 'queued' ORDER BY id"
    ).fetchall()
    return [execute_action(layer, row["id"], transport) for row in rows]


def execute_desk_queued_sends(layer: CaseLayer, transport: SendTransport) -> list[dict[str, Any]]:
    """Execute only desk-control queued actions. Phase E leftovers stay queued."""
    ensure_send_tables(layer)
    rows = layer.conn.execute(
        """
        SELECT id FROM case_send_actions
        WHERE consumed = 0 AND status = 'queued' AND queued_by = ?
        ORDER BY id
        """,
        (QUEUED_BY_DESK,),
    ).fetchall()
    return [execute_action(layer, row["id"], transport, owner="desk-sender") for row in rows]
