"""Decide whether a Gmail message may enter the intake-proof store and Codex."""

from __future__ import annotations

import re
from email.utils import getaddresses, parseaddr
from typing import Any

from .constants import (
    ALLOWED_SENDER,
    CLASS_INELIGIBLE,
    CLASS_NEW,
    CLASS_REPLY,
    MAILBOX,
    MARKER_RE,
)

_MARKER = re.compile(MARKER_RE)


def normalize_email(value: str | None) -> str:
    if not value:
        return ""
    _name, addr = parseaddr(str(value))
    return (addr or str(value)).strip().lower()


def emails_from_header(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        found: list[str] = []
        for item in value:
            found.extend(emails_from_header(item))
        return found
    return [addr.lower() for _name, addr in getaddresses([str(value)]) if addr]


def extract_marker(text: str | None) -> str | None:
    if not text:
        return None
    match = _MARKER.search(text)
    return match.group(0) if match else None


def classify_thread_role(gmail_message_id: str, thread_message_ids_oldest_first: list[str]) -> str:
    """A message is a reply when the Gmail thread already contained an older message."""
    ids = [mid for mid in thread_message_ids_oldest_first if mid]
    if not ids:
        return CLASS_NEW
    if ids[0] == gmail_message_id:
        return CLASS_NEW
    return CLASS_REPLY


def evaluate_message(
    *,
    mailbox: str,
    sender: str | None,
    recipients: list[str] | str | None,
    subject: str | None,
    body: str | None,
    gmail_message_id: str,
    thread_message_ids_oldest_first: list[str] | None = None,
) -> dict[str, Any]:
    """Return eligibility, skip reason, marker, and new/reply classification."""
    mailbox_n = normalize_email(mailbox)
    sender_n = normalize_email(sender)
    recipient_list = [normalize_email(addr) for addr in emails_from_header(recipients)]
    marker = extract_marker(subject) or extract_marker(body)
    classification = classify_thread_role(
        gmail_message_id,
        thread_message_ids_oldest_first or [gmail_message_id],
    )

    reasons: list[str] = []
    if mailbox_n != MAILBOX:
        reasons.append("mailbox_not_contactus")
    if sender_n != ALLOWED_SENDER:
        reasons.append("sender_not_authorized_internal")
    if MAILBOX not in recipient_list:
        reasons.append("contactus_not_a_recipient")
    if not marker:
        reasons.append("missing_bt_intake_proof_marker")

    eligible = not reasons
    return {
        "eligible": eligible,
        "reasons": reasons,
        "mailbox": mailbox_n,
        "sender": sender_n,
        "recipients": recipient_list,
        "marker": marker,
        "classification": classification if eligible else CLASS_INELIGIBLE,
        "gmail_message_id": gmail_message_id,
    }
