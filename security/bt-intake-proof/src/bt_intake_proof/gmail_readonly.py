"""Read-only Gmail API client. Refuses send/modify scopes and mutating methods."""

from __future__ import annotations

import base64
from email import message_from_bytes
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Any

from .constants import (
    FORBIDDEN_GMAIL_SCOPES,
    GMAIL_READONLY_SCOPE,
    MAILBOX,
)
from .eligibility import emails_from_header, normalize_email


MUTATING_HINTS = (
    "users().messages().send",
    "users().messages().modify",
    "users().messages().trash",
    "users().messages().insert",
    "users().drafts()",
    "users().labels().create",
    "users().labels().update",
    "users().labels().delete",
    "users().settings()",
)


class GmailAuthError(RuntimeError):
    pass


def assert_readonly_credentials(scopes: list[str], email: str) -> None:
    email_n = normalize_email(email)
    if email_n != MAILBOX:
        raise GmailAuthError(f"authenticated mailbox is {email_n or '(unknown)'}, expected {MAILBOX}")
    forbidden = [scope for scope in scopes if scope in FORBIDDEN_GMAIL_SCOPES]
    if forbidden:
        raise GmailAuthError(f"credentials include forbidden Gmail scopes: {forbidden}")
    if GMAIL_READONLY_SCOPE not in scopes:
        raise GmailAuthError("credentials must include gmail.readonly and no other Gmail scopes")


def header_map(payload: dict[str, Any]) -> dict[str, str]:
    headers = {}
    for item in (payload.get("payload") or {}).get("headers") or []:
        name = str(item.get("name") or "").lower()
        headers[name] = str(item.get("value") or "")
    return headers


def _decode_header_value(value: str) -> str:
    parts = []
    for chunk, charset in decode_header(value):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts)


def decode_raw_message(raw_b64: str) -> dict[str, Any]:
    raw = base64.urlsafe_b64decode(raw_b64.encode("ascii") + b"===")
    parsed = message_from_bytes(raw)
    body = ""
    if parsed.is_multipart():
        for part in parsed.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition") or ""):
                payload = part.get_payload(decode=True) or b""
                body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                break
    else:
        payload = parsed.get_payload(decode=True) or b""
        body = payload.decode(parsed.get_content_charset() or "utf-8", errors="replace")
    to_values = emails_from_header(parsed.get("To"))
    cc_values = emails_from_header(parsed.get("Cc"))
    received = parsed.get("Date")
    received_iso = None
    if received:
        try:
            received_iso = parsedate_to_datetime(received).isoformat()
        except (TypeError, ValueError):
            received_iso = received
    return {
        "rfc_message_id": (parsed.get("Message-ID") or "").strip(),
        "sender": parsed.get("From") or "",
        "recipients": to_values + cc_values,
        "subject": _decode_header_value(parsed.get("Subject") or ""),
        "body_text": body,
        "raw_message": raw.decode("utf-8", errors="surrogateescape"),
        "gmail_received_at": received_iso,
    }


def gmail_internal_date(message: dict[str, Any]) -> str | None:
    raw = message.get("internalDate")
    if not raw:
        return None
    try:
        ms = int(raw)
    except (TypeError, ValueError):
        return str(raw)
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


class ReadOnlyGmail:
    """Thin wrapper. Only profile, watch, history, and message get are exposed."""

    def __init__(self, service: Any, email: str, scopes: list[str]) -> None:
        assert_readonly_credentials(scopes, email)
        self.service = service
        self.email = normalize_email(email)
        self.scopes = list(scopes)

    def profile(self) -> dict[str, Any]:
        return self.service.users().getProfile(userId="me").execute()

    def watch(self, topic_name: str, label_ids: list[str] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"topicName": topic_name, "labelFilterBehavior": "include"}
        if label_ids:
            body["labelIds"] = label_ids
        return self.service.users().watch(userId="me", body=body).execute()

    def stop_watch(self) -> None:
        self.service.users().stop(userId="me").execute()

    def history(self, start_history_id: str) -> dict[str, Any]:
        return (
            self.service.users()
            .history()
            .list(userId="me", startHistoryId=str(start_history_id), historyTypes=["messageAdded"])
            .execute()
        )

    def get_message(self, message_id: str, fmt: str = "raw") -> dict[str, Any]:
        if fmt not in {"raw", "metadata", "minimal", "full"}:
            raise GmailAuthError(f"unsupported Gmail format {fmt}")
        return self.service.users().messages().get(userId="me", id=message_id, format=fmt).execute()

    def get_thread_message_ids(self, thread_id: str) -> list[str]:
        thread = self.service.users().threads().get(userId="me", id=thread_id, format="minimal").execute()
        ids = []
        for message in thread.get("messages") or []:
            mid = message.get("id")
            if mid:
                ids.append(mid)
        return ids


def added_message_ids(history_response: dict[str, Any]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen = set()
    for record in history_response.get("history") or []:
        for added in record.get("messagesAdded") or []:
            message = added.get("message") or {}
            mid = message.get("id")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            found.append({"id": mid, "threadId": message.get("threadId") or ""})
    return found
