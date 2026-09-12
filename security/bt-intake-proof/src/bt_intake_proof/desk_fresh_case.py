"""Prepare one fresh isolated desk-roundtrip case. Does not approve or send."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .cases import APPROVAL_APPROVED, CaseLayer, case_id_for
from .constants import (
    ALLOWED_SENDER,
    DESK_SEND_BODY,
    DESK_SEND_SUBJECT,
    DESK_SEND_TIMING,
    DETECTION_EVENT_DRIVEN,
    DISPATCH_SKIPPED,
    MAILBOX,
    MARKER_DESK_CASE,
    MARKER_DESK_CTRL,
    MARKER_DESK_HEALTH,
    MARKER_DESK_QUEUE,
    MARKER_DESK_RT_CASE,
    MARKER_DESK_SEND,
)
from .desk_bridge import compute_packet_binding, install_desk_send_draft
from .desk_packets import build_desk_packets
from .phasee_constants import PHASEE_FROM, PHASEE_TO
from .send_bind import ensure_send_tables, latest_action
from .store import ReceiptStore, body_hash, utc_now

# Local case key only. Not a Gmail thread id and must not be sent as threadId.
FRESH_THREAD_ID = "desk-roundtrip-e9a8-20260912"
FRESH_MESSAGE_ID = "desk-rt-inbound-e9a8-20260912"
FRESH_RFC = "<desk-rt-inbound-e9a8-20260912@btpestcontrol.com>"
PHASE_E_CASE_ID = "BTC-contactus-1a093f8e919b8787"


def fresh_case_id() -> str:
    return case_id_for(MAILBOX, FRESH_THREAD_ID)


def inbound_nonce(case_id: str, message_id: str) -> str:
    return f"bt-case-{case_id}-r{message_id}"


def is_desk_roundtrip_receipt(receipt: dict[str, Any] | None) -> bool:
    blob = (
        f"{(receipt or {}).get('test_marker') or ''} "
        f"{(receipt or {}).get('subject') or ''} "
        f"{(receipt or {}).get('body_text') or ''}"
    )
    return MARKER_DESK_RT_CASE in blob


def exact_proof_payload(body: str | None = None) -> dict[str, str]:
    """The exact internal send Daniel must see before any approve_send exists."""
    return {
        "from": PHASEE_FROM,
        "to": PHASEE_TO,
        "cc": "",
        "subject": DESK_SEND_SUBJECT,
        "body": DESK_SEND_BODY.strip() if body is None else body,
        "timing": DESK_SEND_TIMING,
        "marker": MARKER_DESK_SEND,
        "kind": "proof_reply_not_sent",
    }


def decision_packet(case_id: str, draft: dict[str, Any], binding: dict[str, Any]) -> dict[str, Any]:
    proof = exact_proof_payload(str(draft.get("proposed_response") or ""))
    return {
        "status": "AWAITING_DANIEL_EXACT_DECISION",
        "generic_go_is_not_approval": True,
        "approve_send_recorded": False,
        "proof_reply_sent": False,
        "case_id": case_id,
        "draft_version": int(draft.get("version") or 0),
        "nonce": draft.get("nonce") or binding.get("nonce"),
        "packet_hash": binding.get("packet_hash"),
        "hold": False,
        "office_owner": None,
        "exact_internal_send": proof,
        "human": (
            "This is the exact isolated internal message that would be sent once "
            "if Daniel approves this version. A generic go is not approval. "
            "Do not send until this exact recipient, subject, and body are decided."
        ),
        "not_this_packet": {
            "phase_e_case_id": PHASE_E_CASE_ID,
            "phase_e_reusable": False,
            "desk_case_queue_health": "separate_internal_desk_packets",
        },
    }


def insert_synthetic_lead_receipt(store: ReceiptStore, receipt: dict[str, Any]) -> dict[str, Any]:
    """Insert one isolated receipt. Does not touch watch cursors or Pub/Sub."""
    now = utc_now()
    payload = receipt.get("raw_message") if receipt.get("raw_message") is not None else receipt.get("body_text")
    digest = receipt.get("body_hash") or body_hash(payload)
    before = store.get_watch(MAILBOX)
    cur = store.conn.execute(
        """
        INSERT OR IGNORE INTO receipts (
            mailbox, gmail_message_id, thread_id, rfc_message_id, sender,
            recipients_json, subject, gmail_received_at, detected_at,
            body_text, raw_message, body_hash, labels_before_json,
            labels_after_json, detection_path, classification, test_marker,
            eligible, skip_reasons_json, codex_dispatch_state,
            codex_dispatch_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, '[]', ?, NULL, ?)
        """,
        (
            receipt["mailbox"],
            receipt["gmail_message_id"],
            receipt["thread_id"],
            receipt.get("rfc_message_id"),
            receipt.get("sender"),
            json.dumps(receipt.get("recipients") or []),
            receipt.get("subject"),
            receipt.get("gmail_received_at") or now,
            receipt.get("detected_at") or now,
            receipt.get("body_text"),
            receipt.get("raw_message"),
            digest,
            json.dumps(receipt.get("labels_before") or ["INBOX"]),
            json.dumps(receipt.get("labels_after") or ["INBOX"]),
            receipt.get("detection_path") or DETECTION_EVENT_DRIVEN,
            receipt.get("classification") or "new_message",
            receipt.get("test_marker"),
            DISPATCH_SKIPPED,
            now,
        ),
    )
    after = store.get_watch(MAILBOX)
    if (before or {}).get("history_id") != (after or {}).get("history_id"):
        raise RuntimeError("synthetic receipt insert mutated the Gmail watch cursor")
    existing = store.get_receipt(receipt["mailbox"], receipt["gmail_message_id"])
    return {
        "ok": True,
        "inserted": cur.rowcount == 1,
        "duplicate": cur.rowcount != 1,
        "gmail_message_id": receipt["gmail_message_id"],
        "receipt": existing,
    }


def _synthetic_receipt() -> dict[str, Any]:
    body = (
        f"{MARKER_DESK_RT_CASE}\n\n"
        "Synthetic isolated Lead Desk inbound for the internal round-trip proof. "
        "Not customer mail."
    )
    now = utc_now()
    return {
        "eligible": True,
        "mailbox": MAILBOX,
        "gmail_message_id": FRESH_MESSAGE_ID,
        "thread_id": FRESH_THREAD_ID,
        "rfc_message_id": FRESH_RFC,
        "sender": ALLOWED_SENDER,
        "recipients": [MAILBOX],
        "subject": MARKER_DESK_RT_CASE,
        "gmail_received_at": now,
        "detected_at": now,
        "body_text": body,
        "raw_message": body,
        "body_hash": body_hash(body),
        "labels_before": ["INBOX"],
        "labels_after": ["INBOX"],
        "classification": "new_message",
        "test_marker": MARKER_DESK_RT_CASE,
        "detection_path": DETECTION_EVENT_DRIVEN,
        "reasons": [],
    }


def _fail_if_consumed(layer: CaseLayer, case_id: str) -> None:
    case = layer.get_case(case_id)
    if case and case.get("approval_state") == APPROVAL_APPROVED:
        raise RuntimeError(f"refusing to reuse approved case {case_id}")
    action = latest_action(layer, case_id)
    if action:
        raise RuntimeError(f"refusing to reuse case {case_id} with existing send action {action.get('id')}")
    row = layer.conn.execute(
        "SELECT id, decision FROM case_decisions WHERE case_id = ? AND decision = 'approve'",
        (case_id,),
    ).fetchone()
    if row:
        raise RuntimeError(f"refusing to reuse case {case_id} with existing approve decision")


def prepare_fresh_desk_case(store: ReceiptStore, *, dest: Path | None = None) -> dict[str, Any]:
    """Create or reuse the unused synthetic case. Never records approve_send."""
    layer = CaseLayer(store)
    ensure_send_tables(layer)
    case_id = fresh_case_id()
    if case_id == PHASE_E_CASE_ID:
        raise RuntimeError("fresh case id collided with Phase E")
    _fail_if_consumed(layer, case_id)
    inserted = insert_synthetic_lead_receipt(store, _synthetic_receipt())
    receipt = store.get_receipt(MAILBOX, FRESH_MESSAGE_ID)
    if not receipt:
        raise RuntimeError("synthetic receipt missing after insert")
    opened = layer.upsert_from_receipt(receipt)
    if opened.get("skipped") and opened.get("reason") not in {"already_applied", "lead"}:
        if not layer.get_case(case_id):
            raise RuntimeError(f"case upsert skipped: {opened}")
    if not layer.get_case(case_id):
        opened = layer.upsert_from_receipt(receipt)
    case = layer.get_case(case_id)
    if not case:
        raise RuntimeError("fresh case was not created")
    nonce = inbound_nonce(case_id, FRESH_MESSAGE_ID)
    draft = layer.latest_draft(case_id)
    if not draft or str(draft.get("proposed_response") or "").strip() != DESK_SEND_BODY.strip():
        layer.save_fieldwork(
            case_id,
            {
                "status": "not_run",
                "source_label": "FIELDWORK_NOT_ACCESSED",
                "live": False,
                "read_only": True,
                "writes_allowed": False,
                "reason": "desk_roundtrip_internal_send_test",
            },
            FRESH_MESSAGE_ID,
        )
        saved = install_desk_send_draft(layer, case_id, nonce)
        draft = layer.latest_draft(case_id)
    else:
        saved = {"case_id": case_id, "version": draft.get("version"), "reused": True}
    case = layer.get_case(case_id)
    binding = compute_packet_binding(case, draft)
    if str(draft.get("proposed_response") or "").strip() != DESK_SEND_BODY.strip():
        raise RuntimeError("fresh draft is not the exact isolated send body")
    if latest_action(layer, case_id):
        raise RuntimeError("prepare must not queue a send")
    packet = decision_packet(case_id, draft, binding)
    if dest is not None:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "DECISION_PACKET.json").write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
        (dest / "DECISION_PACKET.md").write_text(format_decision_markdown(packet), encoding="utf-8")
    return {
        "ok": True,
        "case_id": case_id,
        "draft_version": int(draft.get("version") or 0),
        "nonce": nonce,
        "receipt_inserted": inserted.get("inserted"),
        "opened": opened,
        "saved": saved,
        "binding": binding,
        "decision": packet,
        "approve_send_recorded": False,
        "send_queued": False,
        "proof_reply_sent": False,
        "watch_untouched": True,
    }


def format_decision_markdown(packet: dict[str, Any]) -> str:
    proof = packet["exact_internal_send"]
    return (
        "# Fresh internal Lead Desk decision packet\n\n"
        "A generic go is **not** an `approve_send` record and is **not** approval of this content.\n"
        "Do not send the proof reply until Daniel decides on this exact message.\n\n"
        f"- Case: `{packet['case_id']}`\n"
        f"- Draft version: `{packet['draft_version']}`\n"
        f"- Approve recorded: `{packet['approve_send_recorded']}`\n"
        f"- Proof reply sent: `{packet['proof_reply_sent']}`\n\n"
        "## Exact isolated send (not sent)\n\n"
        f"- From: `{proof['from']}`\n"
        f"- To: `{proof['to']}`\n"
        f"- CC: `(none)`\n"
        f"- Subject: `{proof['subject']}`\n"
        f"- Timing: `{proof['timing']}`\n\n"
        "### Body\n\n"
        f"```\n{proof['body']}\n```\n"
    )


def assert_not_proof_reply(mail: dict[str, Any]) -> None:
    subject = str(mail.get("subject") or "")
    body = str(mail.get("body") or "")
    if subject == DESK_SEND_SUBJECT:
        raise RuntimeError("refusing to deliver the proof reply as a desk packet")
    if MARKER_DESK_CTRL in subject or MARKER_DESK_CTRL in body:
        raise RuntimeError("refusing to deliver a control message")
    markers = (MARKER_DESK_CASE, MARKER_DESK_QUEUE, MARKER_DESK_HEALTH)
    if not any(marker in subject or marker in body for marker in markers):
        raise RuntimeError("not an internal desk CASE/QUEUE/HEALTH packet")


def deliver_case_packets(store: ReceiptStore, *, kinds: tuple[str, ...] = ("case",)) -> dict[str, Any]:
    """Send CASE (optionally QUEUE/HEALTH) contactus→daniel. Never the proof reply."""
    from .contactus_send import configured_send_transport

    built = build_desk_packets(store.path, case_id=fresh_case_id())
    transport = configured_send_transport()
    sender = getattr(transport, "send_internal_desk", None)
    if sender is None:
        return {"ok": False, "reason": "desk_sender_missing", "proof_reply_sent": False}
    delivered = []
    for email in built.get("emails") or []:
        if email.get("kind") not in kinds:
            continue
        assert_not_proof_reply(email)
        result = sender(
            {
                "from_addr": MAILBOX,
                "to": ALLOWED_SENDER,
                "subject": email["subject"],
                "body": email["body"],
            }
        )
        delivered.append(
            {
                "ok": bool(result.get("ok")),
                "kind": email.get("kind"),
                "subject": email.get("subject"),
                "reason": result.get("reason"),
                "unknown": result.get("unknown"),
                "provider_message_id": result.get("provider_message_id"),
            }
        )
    return {
        "ok": bool(delivered) and all(item.get("ok") for item in delivered),
        "delivered": delivered,
        "proof_reply_sent": False,
        "kinds": list(kinds),
    }
