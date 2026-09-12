"""Independent Gmail verification. A sender API return is not delivery proof."""

from __future__ import annotations

import base64
from email import message_from_bytes
from typing import Any, Protocol

from .cases import CaseLayer
from .eligibility import emails_from_header, normalize_email
from .gmail_readonly import decode_raw_message, gmail_internal_date
from .phasee_constants import (
    PHASEE_FROM,
    PHASEE_SEND_MARKER,
    PHASEE_TO,
    STATUS_RECEIPT_VERIFIED,
    STATUS_SENT_VERIFIED,
)
from .send_bind import action_row, binding_from_action, mark_action, record_verification


class VerifyTransport(Protocol):
    def search_sent(self, marker: str) -> list[dict[str, Any]]:
        ...

    def search_inbox(self, marker: str) -> list[dict[str, Any]]:
        ...


class MemoryVerifyTransport:
    def __init__(self, sent: list[dict[str, Any]] | None = None, inbox: list[dict[str, Any]] | None = None) -> None:
        self.sent = list(sent or [])
        self.inbox = list(inbox or [])

    def search_sent(self, marker: str) -> list[dict[str, Any]]:
        return [item for item in self.sent if marker in str(item.get("body") or "") or marker in str(item.get("subject") or "")]

    def search_inbox(self, marker: str) -> list[dict[str, Any]]:
        return [item for item in self.inbox if marker in str(item.get("body") or "") or marker in str(item.get("subject") or "")]


def found_from_raw_gmail(message: dict[str, Any]) -> dict[str, Any]:
    decoded = decode_raw_message(message["raw"])
    raw = base64.urlsafe_b64decode(message["raw"].encode("ascii") + b"===")
    parsed = message_from_bytes(raw)
    return {
        "id": message.get("id"),
        "thread_id": message.get("threadId"),
        "from": parsed.get("From") or decoded.get("sender"),
        "to": emails_from_header(parsed.get("To")),
        "cc": emails_from_header(parsed.get("Cc")),
        "bcc": emails_from_header(parsed.get("Bcc")),
        "subject": decoded.get("subject"),
        "body": decoded.get("body_text"),
        "internal_date": gmail_internal_date(message),
        "label_ids": message.get("labelIds") or [],
    }


class ContactusReadonlySentVerify:
    """Search contactus Sent with the existing read-only token. Does not send."""

    def __init__(self, gmail: Any) -> None:
        self.gmail = gmail

    def search_sent(self, marker: str) -> list[dict[str, Any]]:
        hits = self.gmail.search_messages(f'in:sent "{marker}"', max_results=10)
        found = []
        for hit in hits:
            raw = self.gmail.get_message(hit["id"], "raw")
            found.append(found_from_raw_gmail(raw))
        return found

    def search_inbox(self, marker: str) -> list[dict[str, Any]]:
        return []


class RecordedInboxVerify:
    """Recipient-side results collected on a separate authorized path. Does not mutate labels."""

    def __init__(self, inbox: list[dict[str, Any]] | None = None) -> None:
        self.inbox = list(inbox or [])

    def search_sent(self, marker: str) -> list[dict[str, Any]]:
        return []

    def search_inbox(self, marker: str) -> list[dict[str, Any]]:
        return [item for item in self.inbox if marker in str(item.get("body") or "") or marker in str(item.get("subject") or "")]


def _norm_list(values: Any) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        return [normalize_email(addr) for addr in emails_from_header(values)]
    return [normalize_email(str(addr)) for addr in values]


def _norm_body(text: Any) -> str:
    return str(text or "").replace("\r\n", "\n").strip()


def compare_outbound(binding: dict[str, Any], found: dict[str, Any], *, require_thread: bool = True) -> list[str]:
    mismatches = []
    if normalize_email(found.get("from") or found.get("sender")) != PHASEE_FROM:
        mismatches.append("from")
    if _norm_list(found.get("to") or found.get("to_addr")) != [PHASEE_TO]:
        mismatches.append("to")
    if _norm_list(found.get("cc")):
        mismatches.append("cc")
    if _norm_list(found.get("bcc")):
        mismatches.append("bcc")
    if str(found.get("subject") or "") != binding["subject"]:
        mismatches.append("subject")
    if _norm_body(found.get("body")) != _norm_body(binding.get("body")):
        mismatches.append("body")
    if PHASEE_SEND_MARKER not in str(found.get("body") or ""):
        mismatches.append("marker")
    found_thread = str(found.get("thread_id") or found.get("threadId") or "")
    bound_thread = str(binding.get("thread_id") or "")
    if require_thread and bound_thread and found_thread and found_thread != bound_thread:
        mismatches.append("thread")
    return mismatches


def verify_sent(layer: CaseLayer, action_id: int, transport: VerifyTransport) -> dict[str, Any]:
    action = action_row(layer, action_id)
    if not action:
        return {"ok": False, "reason": "unknown_action"}
    binding = binding_from_action(action)
    found = transport.search_sent(PHASEE_SEND_MARKER)
    if len(found) == 0:
        record_verification(layer, action_id, "contactus_sent", "missing", detail={"count": 0})
        return {"ok": False, "reason": "no_matching_outbound", "count": 0}
    if len(found) > 1:
        record_verification(layer, action_id, "contactus_sent", "duplicate", detail={"count": len(found)})
        return {"ok": False, "reason": "more_than_one_outbound", "count": len(found)}
    message = found[0]
    mismatches = compare_outbound(binding, message)
    if mismatches:
        record_verification(layer, action_id, "contactus_sent", "mismatch", detail={"mismatches": mismatches})
        return {"ok": False, "reason": "content_mismatch", "mismatches": mismatches}
    mark_action(layer, action_id, status=STATUS_SENT_VERIFIED)
    record_verification(
        layer,
        action_id,
        "contactus_sent",
        "sent_verified",
        provider_message_id=message.get("id") or message.get("provider_message_id"),
        detail={"internal_date": message.get("internal_date")},
    )
    layer.add_event(action["case_id"], "phasee_sent_verified", provider_message_id=message.get("id") or message.get("provider_message_id"))
    return {
        "ok": True,
        "status": STATUS_SENT_VERIFIED,
        "provider_message_id": message.get("id") or message.get("provider_message_id"),
        "count": 1,
    }


def verify_recipient(layer: CaseLayer, action_id: int, transport: VerifyTransport) -> dict[str, Any]:
    action = action_row(layer, action_id)
    if not action:
        return {"ok": False, "reason": "unknown_action"}
    binding = binding_from_action(action)
    found = transport.search_inbox(PHASEE_SEND_MARKER)
    if len(found) != 1:
        record_verification(layer, action_id, "daniel_inbox", "missing" if not found else "duplicate", detail={"count": len(found)})
        return {"ok": False, "reason": "recipient_count", "count": len(found)}
    message = found[0]
    # Gmail thread IDs are per-mailbox; do not require the contactus thread id on daniel@.
    mismatches = compare_outbound(binding, message, require_thread=False)
    if mismatches:
        record_verification(layer, action_id, "daniel_inbox", "mismatch", detail={"mismatches": mismatches})
        return {"ok": False, "reason": "content_mismatch", "mismatches": mismatches}
    unread = "UNREAD" in (message.get("label_ids") or message.get("labels") or [])
    mark_action(layer, action_id, status=STATUS_RECEIPT_VERIFIED)
    record_verification(
        layer,
        action_id,
        "daniel_inbox",
        "recipient_receipt_verified",
        provider_message_id=message.get("id"),
        detail={"unread_preserved": unread, "labels_untouched": True},
    )
    layer.add_event(action["case_id"], "phasee_receipt_verified", unread_preserved=unread)
    return {"ok": True, "status": STATUS_RECEIPT_VERIFIED, "unread_preserved": unread, "count": 1}
