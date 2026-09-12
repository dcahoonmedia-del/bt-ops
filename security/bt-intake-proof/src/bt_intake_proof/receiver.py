"""Resolve Pub/Sub Gmail notifications through history and commit before ack."""

from __future__ import annotations

import json
from typing import Any, Callable

from . import eligibility
from .constants import DETECTION_EVENT_DRIVEN, MAILBOX
from .gmail_readonly import added_message_ids, decode_raw_message, gmail_internal_date
from .oauth_consent import OAuthClientError
from .store import ReceiptStore, should_ack, utc_now


def is_missing_gmail_entity(exc: BaseException) -> bool:
    text = str(exc)
    return "HTTP 404" in text or "Requested entity was not found" in text


def parse_gmail_notification(data: dict[str, Any] | str | bytes) -> dict[str, Any]:
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8")
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        raise ValueError("Gmail notification payload is not an object")
    email_address = str(data.get("emailAddress") or "")
    history_id = str(data.get("historyId") or "")
    if not history_id:
        raise ValueError("Gmail notification missing historyId")
    return {"emailAddress": email_address, "historyId": history_id}


def hydrate_receipt(
    mailbox: str,
    message: dict[str, Any],
    thread_ids: list[str],
    detection_path: str,
) -> dict[str, Any]:
    decoded = {}
    if message.get("raw"):
        decoded = decode_raw_message(message["raw"])
    labels = list(message.get("labelIds") or [])
    sender = decoded.get("sender") or ""
    recipients = decoded.get("recipients") or []
    subject = decoded.get("subject") or ""
    body = decoded.get("body_text") or ""
    decision = eligibility.evaluate_message(
        mailbox=mailbox,
        sender=sender,
        recipients=recipients,
        subject=subject,
        body=body,
        gmail_message_id=message["id"],
        thread_message_ids_oldest_first=thread_ids,
    )
    receipt = {
        **decision,
        "thread_id": message.get("threadId") or "",
        "rfc_message_id": decoded.get("rfc_message_id"),
        "subject": subject if decision["eligible"] else None,
        "gmail_received_at": decoded.get("gmail_received_at") or gmail_internal_date(message),
        "detected_at": utc_now(),
        "body_text": body if decision["eligible"] else None,
        "raw_message": decoded.get("raw_message") if decision["eligible"] else None,
        "labels_before": labels,
        "labels_after": labels,
        "detection_path": detection_path,
        "test_marker": decision.get("marker"),
    }
    return receipt


def process_notification(
    store: ReceiptStore,
    payload: dict[str, Any] | str | bytes,
    *,
    gmail: Any,
    detection_path: str = DETECTION_EVENT_DRIVEN,
    pubsub_message_id: str | None = None,
    ack: Callable[[], None] | None = None,
    nack: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Fetch history, persist eligible receipts, then ack only if commit succeeded."""
    parsed = parse_gmail_notification(payload)
    mailbox = eligibility.normalize_email(parsed["emailAddress"] or MAILBOX)
    if mailbox != MAILBOX:
        # Still durable-advance nothing; do not ack foreign-mailbox notifications.
        if nack:
            nack()
        return {"ok": False, "acked": False, "reason": "notification_mailbox_mismatch", "mailbox": mailbox}

    cursor = store.get_watch(mailbox)
    start_history = (cursor or {}).get("history_id") or parsed["historyId"]
    history = gmail.history(start_history)
    added = added_message_ids(history)
    receipts: list[dict[str, Any]] = []
    skipped_missing = []
    for item in added:
        try:
            message = gmail.get_message(item["id"], fmt="raw")
        except OAuthClientError as exc:
            if is_missing_gmail_entity(exc):
                skipped_missing.append(item["id"])
                continue
            raise
        thread_ids = gmail.get_thread_message_ids(message.get("threadId") or item.get("threadId") or "")
        # Re-read labels after hydration to prove we did not mutate Gmail.
        labels_after = list((gmail.get_message(item["id"], fmt="metadata").get("labelIds") or []))
        receipt = hydrate_receipt(mailbox, message, thread_ids, detection_path)
        receipt["labels_after"] = labels_after
        receipts.append(receipt)

    new_history = str(history.get("historyId") or parsed["historyId"])
    cursor_id = str((cursor or {}).get("history_id") or "")
    if cursor_id.isdigit() and new_history.isdigit() and int(new_history) < int(cursor_id):
        new_history = cursor_id
    error = None
    commit = None
    try:
        commit = store.commit_notification(
            mailbox=mailbox,
            history_id=new_history,
            detection_path=detection_path,
            pubsub_message_id=pubsub_message_id,
            receipts=receipts,
        )
    except Exception as exc:  # noqa: BLE001
        error = exc
        commit = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    acked = should_ack(commit, error)
    if acked:
        if pubsub_message_id:
            store.mark_acked(pubsub_message_id)
        if ack:
            ack()
    elif nack:
        nack()
    return {
        "ok": bool(commit and commit.get("ok")),
        "acked": acked,
        "commit": commit,
        "receipt_count": len(receipts),
        "eligible": [item for item in receipts if item.get("eligible")],
        "ineligible": [item["gmail_message_id"] for item in receipts if not item.get("eligible")],
        "skipped_missing": skipped_missing,
        "start_history_id": start_history,
        "end_history_id": new_history,
        "detection_path": detection_path,
    }


def recover_from_cursor(store: ReceiptStore, gmail: Any, mailbox: str = MAILBOX) -> dict[str, Any]:
    cursor = store.get_watch(mailbox)
    if not cursor or not cursor.get("history_id"):
        return {"ok": False, "reason": "no_watch_cursor"}
    synthetic = {"emailAddress": mailbox, "historyId": cursor["history_id"]}
    return process_notification(
        store,
        synthetic,
        gmail=gmail,
        detection_path="recovery",
        pubsub_message_id=None,
    )
