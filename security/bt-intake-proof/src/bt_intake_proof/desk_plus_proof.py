"""Hidden daniel+lead-desk@ control transport.

Internal Lead Desk controls may arrive as self-addressed Gmail:

    daniel@btpestcontrol.com → daniel+lead-desk@btpestcontrol.com

Self-addressed Gmail does not carry the inbound Authentication-Results
headers used by the contactus@ path. This module must not call
`authenticate_control_origin` and must not treat From:/To: headers alone
as proof.

Authorization is only for a message retrieved through the authenticated
daniel@ Gmail account that has all of:

- mailbox authenticated as daniel@btpestcontrol.com
- Gmail message exists in Daniel's mailbox
- SENT label present
- exact From = daniel@btpestcontrol.com
- exact To = daniel+lead-desk@btpestcontrol.com
- current valid control metadata

Customer or external mail cannot satisfy this path by spoofing headers
or copying control syntax. The contactus@ path is unchanged.
"""

from __future__ import annotations

from typing import Any

from .constants import (
    ALLOWED_SENDER,
    LEAD_DESK_PLUS_MAILBOX,
    MARKER_DESK_CTRL,
    TRANSPORT_PLUS,
)
from .desk_origin import unquoted_control_text
from .desk_sent_proof import (
    REASON_ACCESS_BLOCKED,
    _daniel_readonly_gmail,
    canonical_control_payload,
    diagnose_daniel_sent_access,
    header_date,
    header_message_id,
)
from .eligibility import emails_from_header, normalize_email
from .gmail_readonly import GmailAuthError, decode_raw_message, gmail_internal_date

FETCHED_VIA_DANIEL_PLUS = "daniel_gmail_plus_control_api"
FETCHED_VIA_FIXTURE_PLUS = "fixture_daniel_plus_control"
PLUS_FETCH_VIAS = {FETCHED_VIA_DANIEL_PLUS, FETCHED_VIA_FIXTURE_PLUS}

REASON_PLUS_FETCH = "plus_address_fetch_required"
REASON_PLUS_MAILBOX = "plus_mailbox_not_daniel"
REASON_PLUS_MISSING = "plus_gmail_message_missing"
REASON_PLUS_SENT = "plus_sent_label_missing"
REASON_PLUS_FROM = "plus_from_not_daniel"
REASON_PLUS_TO = "plus_recipient_mismatch"
REASON_PLUS_META = "plus_control_metadata_invalid"
REASON_PLUS_OK = "plus_address_sent_mailbox_match"

SENT_LABEL = "SENT"


def plus_recipient_ok(recipients: list[str] | None, cc: list[str] | None = None) -> bool:
    tos = {normalize_email(item) for item in (recipients or []) if normalize_email(item)}
    extras = {normalize_email(item) for item in (cc or []) if normalize_email(item)}
    return tos == {LEAD_DESK_PLUS_MAILBOX} and not extras


def _labels(evidence: dict[str, Any]) -> list[str]:
    raw = evidence.get("labels")
    if raw is None:
        raw = evidence.get("labelIds") or []
    return [str(item).upper() for item in raw if str(item).strip()]


def _header_addresses(headers: Any, name: str) -> list[str]:
    if not headers:
        return []
    items = headers.items() if isinstance(headers, dict) else headers
    found: list[str] = []
    for item in items:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            if str(item[0]).lower() == name.lower():
                found.extend(emails_from_header(item[1]))
    return [normalize_email(addr) for addr in found if normalize_email(addr)]


def plus_control_evidence(
    gmail_message_id: str,
    *,
    mailbox: str = ALLOWED_SENDER,
    labels: list[str] | None = None,
    fetched_via: str = FETCHED_VIA_FIXTURE_PLUS,
    **extra: Any,
) -> dict[str, Any]:
    """Fixture / adapter helper. Not a production bypass."""
    payload = {
        "fetched_via": fetched_via,
        "authenticated_mailbox": normalize_email(mailbox),
        "gmail_message_id": gmail_message_id,
        "message_exists": True,
        "labels": labels if labels is not None else [SENT_LABEL],
    }
    payload.update(extra)
    return payload


def authorize_plus_address_control(
    from_addr: str | None,
    provider_evidence: dict[str, Any] | None,
    inbound: dict[str, Any],
) -> dict[str, Any]:
    """Authorize only Daniel-mailbox SENT mail to the hidden plus-address."""
    evidence = dict(provider_evidence or {})
    base = {
        "accepted": False,
        "ok": False,
        "transport": TRANSPORT_PLUS,
        "recipient": LEAD_DESK_PLUS_MAILBOX,
        "mailbox_bound": False,
        "full_identity_pass": False,
        "requires_authentication_results": False,
        "fetched_via": evidence.get("fetched_via"),
    }
    mailbox = normalize_email(evidence.get("authenticated_mailbox") or evidence.get("mailbox"))
    if mailbox != ALLOWED_SENDER:
        return {**base, "reason": REASON_PLUS_MAILBOX}
    fetched = str(evidence.get("fetched_via") or "")
    if fetched not in PLUS_FETCH_VIAS:
        return {**base, "reason": REASON_PLUS_FETCH}
    gmail_id = str(evidence.get("gmail_message_id") or inbound.get("control_gmail_id") or "")
    if not gmail_id or evidence.get("message_exists") is False:
        return {**base, "reason": REASON_PLUS_MISSING}
    if SENT_LABEL not in _labels(evidence):
        return {**base, "reason": REASON_PLUS_SENT}
    from_n = normalize_email(from_addr)
    header_from = _header_addresses(evidence.get("headers") or inbound.get("headers"), "From")
    if from_n != ALLOWED_SENDER or (header_from and header_from != [ALLOWED_SENDER]):
        return {**base, "reason": REASON_PLUS_FROM}
    header_to = _header_addresses(evidence.get("headers"), "To")
    header_cc = _header_addresses(evidence.get("headers"), "Cc")
    inbound_to = [normalize_email(item) for item in inbound.get("recipients") or [] if normalize_email(item)]
    inbound_cc = [normalize_email(item) for item in inbound.get("cc") or evidence.get("cc") or [] if normalize_email(item)]
    to_check = header_to or inbound_to
    cc_check = header_cc or inbound_cc
    if not plus_recipient_ok(to_check, cc_check):
        return {**base, "reason": REASON_PLUS_TO}
    if inbound_to and not plus_recipient_ok(inbound_to, inbound_cc):
        return {**base, "reason": REASON_PLUS_TO}
    if not inbound.get("canonical") or not inbound.get("payload_hash"):
        return {**base, "reason": REASON_PLUS_META}
    return {
        **base,
        "accepted": True,
        "ok": True,
        "reason": REASON_PLUS_OK,
        "proof_version": "desk-plus-v1",
        "sent_gmail_id": gmail_id,
        "sent_at": inbound.get("received_at") or evidence.get("received_at") or evidence.get("sent_at"),
        "gmail_message_id": gmail_id,
    }


def plus_evidence_from_fetched_message(
    message: dict[str, Any],
    *,
    mailbox: str,
    fetched_via: str = FETCHED_VIA_DANIEL_PLUS,
) -> dict[str, Any]:
    """Shape a Daniel-mailbox get() into plus-path evidence. Does not authorize."""
    decoded: dict[str, Any] = {}
    if message.get("raw"):
        decoded = decode_raw_message(message["raw"])
    headers = decoded.get("headers") or []
    to_addrs = _header_addresses(headers, "To") or [normalize_email(item) for item in decoded.get("recipients") or []]
    cc_addrs = _header_addresses(headers, "Cc")
    return {
        "fetched_via": fetched_via,
        "authenticated_mailbox": normalize_email(mailbox),
        "gmail_message_id": message.get("id"),
        "message_exists": bool(message.get("id")),
        "labels": list(message.get("labelIds") or message.get("labels") or []),
        "headers": headers,
        "rfc_message_id": decoded.get("rfc_message_id") or header_message_id(headers),
        "received_at": decoded.get("gmail_received_at") or gmail_internal_date(message) or header_date(headers),
        "recipients": to_addrs,
        "cc": cc_addrs,
        "sender": decoded.get("sender") or "",
        "subject": decoded.get("subject") or "",
        "body": decoded.get("body_text") or "",
        "sent_at": decoded.get("gmail_received_at") or gmail_internal_date(message),
    }


def fetch_plus_control_from_daniel(gmail_message_id: str) -> dict[str, Any]:
    """Read one message from the existing daniel@ readonly token. No new OAuth."""
    access = diagnose_daniel_sent_access()
    if not access.get("available"):
        return {"ok": False, "reason": REASON_ACCESS_BLOCKED, "access": access}
    bare = str(gmail_message_id or "").strip()
    if not bare:
        return {"ok": False, "reason": REASON_PLUS_MISSING, "access": access}
    try:
        from .oauth_consent import OAuthClientError

        client = _daniel_readonly_gmail()
        if normalize_email(getattr(client, "email", "")) != ALLOWED_SENDER:
            return {"ok": False, "reason": REASON_PLUS_MAILBOX, "access": access}
        raw = client.get_message(bare, "raw")
    except (GmailAuthError, OAuthClientError, OSError, ValueError) as exc:
        return {"ok": False, "reason": REASON_PLUS_MISSING, "error": type(exc).__name__, "access": access}
    if not raw or not raw.get("id"):
        return {"ok": False, "reason": REASON_PLUS_MISSING, "access": access}
    evidence = plus_evidence_from_fetched_message(
        raw,
        mailbox=ALLOWED_SENDER,
        fetched_via=FETCHED_VIA_DANIEL_PLUS,
    )
    return {
        "ok": True,
        "reason": "fetched_daniel_plus_control",
        "access": access,
        "evidence": evidence,
        "sender": evidence.get("sender"),
        "subject": evidence.get("subject"),
        "body": evidence.get("body"),
        "rfc_message_id": evidence.get("rfc_message_id"),
        "recipients": evidence.get("recipients"),
        "received_at": evidence.get("received_at"),
        "gmail_message_id": evidence.get("gmail_message_id"),
        "labels": evidence.get("labels"),
    }


def search_plus_controls_in_daniel_sent(*, max_results: int = 10) -> dict[str, Any]:
    """List SENT plus-address controls. Does not search Inbox or contactus@."""
    access = diagnose_daniel_sent_access()
    if not access.get("available"):
        return {"ok": False, "reason": REASON_ACCESS_BLOCKED, "access": access, "messages": []}
    query = f"in:sent to:{LEAD_DESK_PLUS_MAILBOX} subject:{MARKER_DESK_CTRL}"
    try:
        client = _daniel_readonly_gmail()
        if normalize_email(getattr(client, "email", "")) != ALLOWED_SENDER:
            return {"ok": False, "reason": REASON_PLUS_MAILBOX, "access": access, "messages": []}
        hits = client.search_messages(query, max_results=max_results)
    except (GmailAuthError, OSError, ValueError) as exc:
        return {"ok": False, "reason": REASON_ACCESS_BLOCKED, "error": type(exc).__name__, "access": access, "messages": []}
    return {"ok": True, "query": query, "access": access, "messages": list(hits or [])}


def looks_like_plus_control_payload(subject: str | None, body: str | None) -> bool:
    canonical = canonical_control_payload(subject, unquoted_control_text(body))
    return bool(canonical)
