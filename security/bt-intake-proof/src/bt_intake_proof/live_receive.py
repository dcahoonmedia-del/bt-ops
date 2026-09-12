"""Pull Gmail watch notifications, persist eligible receipts, ack after commit."""

from __future__ import annotations

import base64
import json
from typing import Any

from .cloud_auth import refresh_cloud_token
from .constants import MAILBOX
from .gce_identity import metadata_access_token, metadata_available
from .receiver import process_notification
from .receiver_sa import acknowledge, impersonate_receiver, pull_subscription
from .store import ReceiptStore, utc_now


def _decode_data(data: str) -> dict[str, Any] | str:
    if not data:
        return {}
    raw = base64.urlsafe_b64decode(data + "===")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw.decode("utf-8", errors="replace")


def _safe_result(result: dict[str, Any]) -> dict[str, Any]:
    eligible = []
    for item in result.get("eligible") or []:
        eligible.append(
            {
                "gmail_message_id": item.get("gmail_message_id"),
                "thread_id": item.get("thread_id"),
                "classification": item.get("classification"),
                "test_marker": item.get("test_marker"),
                "labels_before": item.get("labels_before"),
                "labels_after": item.get("labels_after"),
                "labels_unchanged": item.get("labels_before") == item.get("labels_after"),
                "detection_path": item.get("detection_path"),
            }
        )
    return {
        "ok": result.get("ok"),
        "acked": result.get("acked"),
        "receipt_count": result.get("receipt_count"),
        "eligible": eligible,
        "ineligible_count": len(result.get("ineligible") or []),
        "start_history_id": result.get("start_history_id"),
        "end_history_id": result.get("end_history_id"),
        "detection_path": result.get("detection_path"),
    }


def receive_once(store: ReceiptStore, gmail: Any, sa_token: str) -> dict[str, Any]:
    pull = pull_subscription(sa_token, max_messages=10)
    items = pull.get("received_messages") or []
    processed = []
    ack_ids: list[str] = []
    for item in items:
        message = item.get("message") or {}
        pubsub_id = str(message.get("messageId") or "")
        ack_id = str(item.get("ackId") or "")
        payload = _decode_data(str(message.get("data") or ""))
        pending: list[str] = []

        def ack(captured: str = ack_id) -> None:
            if captured:
                pending.append(captured)

        def nack() -> None:
            return None

        result = process_notification(
            store,
            payload,
            gmail=gmail,
            pubsub_message_id=pubsub_id or None,
            ack=ack,
            nack=nack,
        )
        ack_ids.extend(pending)
        processed.append(_safe_result(result))
    if ack_ids:
        acknowledge(sa_token, ack_ids)
    return {
        "pulled": len(items),
        "acked_count": len(ack_ids),
        "processed": processed,
        "received_at": utc_now(),
        "mailbox": MAILBOX,
        "subscription": pull.get("subscription"),
    }


def impersonated_receiver_token() -> str:
    record = refresh_cloud_token()
    return impersonate_receiver(str(record.get("access_token") or ""))


def receiver_access_token() -> str:
    """Attached GCE identity first. Impersonation only when metadata is absent."""
    if metadata_available():
        return metadata_access_token()
    return impersonated_receiver_token()
