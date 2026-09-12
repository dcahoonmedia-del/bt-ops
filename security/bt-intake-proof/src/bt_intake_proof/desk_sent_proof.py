"""Fail-closed daniel@ Sent corroboration for desk control mail.

Mailbox-bound Authentication-Results is a prerequisite, not authorization.
Authorization requires exactly one authenticated daniel@ Sent message that
matches the inbound control on Message-ID, recipient, canonical payload,
and timing. Missing, ambiguous, or mismatched evidence fails closed.

This module does not request OAuth, mint credentials, or treat
`origin_already_authenticated` / legacy inbox flags as proof.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Protocol
from .constants import ALLOWED_SENDER, FORBIDDEN_GMAIL_SCOPES, GMAIL_READONLY_SCOPE, MAILBOX, MARKER_DESK_CTRL
from .desk_origin import authenticate_control_origin, unquoted_control_text
from .eligibility import normalize_email
from .gates import daniel_sent_token_path
from .gmail_readonly import GmailAuthError, decode_raw_message, gmail_internal_date
from .store import utc_now

PROOF_VERSION = "desk-sent-v1"
FETCHED_VIA_DANIEL_SENT = "daniel_gmail_sent_api"
FETCHED_VIA_FIXTURE = "fixture_daniel_sent"
TIMING_SLACK = timedelta(minutes=15)

REASON_ACCESS_BLOCKED = "sent_mailbox_access_blocked"
REASON_MISSING = "sent_mailbox_evidence_missing"
REASON_AMBIGUOUS = "sent_mailbox_evidence_ambiguous"
REASON_MISMATCH = "sent_mailbox_evidence_mismatched"
REASON_RFC_MISSING = "rfc_message_id_missing"
REASON_INBOUND_TIMING = "inbound_timing_missing"
REASON_SENT_TIMING = "sent_timing_missing"
REASON_LEGACY = "legacy_approval_not_sender_proof"
REASON_EXACT = "mailbox_bound_and_sent_exact_match"


def _normalize_message_id(value: str | None) -> str:
    raw = str(value or "").strip()
    if raw.startswith("<") and raw.endswith(">") and len(raw) > 2:
        raw = raw[1:-1]
    return raw.strip().lower()


def _parse_time(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def canonical_control_payload(subject: str | None, body: str | None) -> dict[str, Any] | None:
    from .desk_bridge import parse_control_mail

    parsed = parse_control_mail(subject, unquoted_control_text(body))
    if not parsed.get("ok") or not parsed.get("intent"):
        return None
    return {
        "intent": parsed.get("intent") or "",
        "owner": parsed.get("owner") or "",
        "note": parsed.get("note") or "",
        "case_id": parsed.get("case_id") or "",
        "draft_version": parsed.get("draft_version"),
        "nonce": parsed.get("nonce") or "",
        "packet_hash": parsed.get("packet_hash") or "",
        "marker": MARKER_DESK_CTRL,
    }


def payload_hash(canonical: dict[str, Any] | None) -> str:
    if not canonical:
        return ""
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def header_message_id(headers: Any) -> str | None:
    if not headers:
        return None
    items = headers.items() if isinstance(headers, dict) else headers
    for item in items:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            name, value = item[0], item[1]
        else:
            continue
        if str(name).lower() == "message-id" and str(value).strip():
            return str(value).strip()
    return None


def header_date(headers: Any) -> str | None:
    if not headers:
        return None
    items = headers.items() if isinstance(headers, dict) else headers
    for item in items:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            name, value = item[0], item[1]
        else:
            continue
        if str(name).lower() == "date" and str(value).strip():
            return str(value).strip()
    return None


@dataclass
class SentControlRecord:
    rfc_message_id: str
    recipients: list[str]
    cc: list[str] = field(default_factory=list)
    subject: str = ""
    body: str = ""
    sent_at: str = ""
    gmail_id: str = ""
    mailbox: str = ALLOWED_SENDER
    fetched_via: str = FETCHED_VIA_FIXTURE


@dataclass
class SentLookupResult:
    status: str
    reason: str
    records: list[SentControlRecord] = field(default_factory=list)
    access: dict[str, Any] = field(default_factory=dict)


class SentLookup(Protocol):
    def find_by_rfc_message_id(self, rfc_message_id: str) -> SentLookupResult:
        ...


class BlockedSentLookup:
    """Production default when no existing daniel@ readonly token is present."""

    def __init__(self, *, path: Path | None = None, detail: str | None = None) -> None:
        self.path = path or daniel_sent_token_path()
        self.detail = detail or (
            "Existing already-authorized gmail.readonly credential for "
            f"{ALLOWED_SENDER} that can users.messages.list/get on label SENT. "
            f"File {self.path} or env BT_DANIEL_GMAIL_TOKEN. Mailbox must be "
            f"{ALLOWED_SENDER}; scope {GMAIL_READONLY_SCOPE} only. Do not mint "
            "a new client or request new scopes. contactus@ tokens cannot read "
            "daniel@ Sent. Cursor Gmail MCP is not the host path."
        )

    def find_by_rfc_message_id(self, rfc_message_id: str) -> SentLookupResult:
        return SentLookupResult(
            status="blocked",
            reason=REASON_ACCESS_BLOCKED,
            access={
                "available": False,
                "token_path": str(self.path),
                "mailbox_required": ALLOWED_SENDER,
                "scope_required": GMAIL_READONLY_SCOPE,
                "detail": self.detail,
            },
        )


class MemorySentLookup:
    """Fixture lookup. Not a production bypass."""

    def __init__(self, records: list[SentControlRecord] | None = None) -> None:
        self.records = list(records or [])

    def find_by_rfc_message_id(self, rfc_message_id: str) -> SentLookupResult:
        want = _normalize_message_id(rfc_message_id)
        found = [item for item in self.records if _normalize_message_id(item.rfc_message_id) == want]
        return SentLookupResult(status="ok", reason="fixture", records=found, access={"available": True, "via": FETCHED_VIA_FIXTURE})


_TEST_LOOKUP: SentLookup | None = None


def set_test_sent_lookup(lookup: SentLookup | None) -> None:
    global _TEST_LOOKUP
    _TEST_LOOKUP = lookup


def diagnose_daniel_sent_access() -> dict[str, Any]:
    """Read-only probe. Does not start consent or refresh if the file is absent."""
    path = daniel_sent_token_path()
    payload: dict[str, Any] = {
        "status": "BLOCKED",
        "available": False,
        "token_path": str(path),
        "token_present": path.exists(),
        "mailbox_required": ALLOWED_SENDER,
        "scope_required": GMAIL_READONLY_SCOPE,
        "label": "SENT",
        "query": "in:sent rfc822msgid:<Message-ID>",
        "note": (
            "Do not request or grant new OAuth. Place an already-authorized "
            f"{ALLOWED_SENDER} gmail.readonly token at this path or "
            "BT_DANIEL_GMAIL_TOKEN. contactus@ readonly/send tokens are not this connection."
        ),
    }
    if not path.exists():
        return payload
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {**payload, "reason": "token_unreadable"}
    email = normalize_email(str(data.get("email") or data.get("account") or ""))
    scopes = data.get("scopes") or data.get("scope") or []
    if isinstance(scopes, str):
        scopes = [item for item in scopes.replace(",", " ").split() if item]
    forbidden = [scope for scope in scopes if scope in FORBIDDEN_GMAIL_SCOPES]
    if email != ALLOWED_SENDER:
        return {**payload, "status": "FAIL", "reason": f"token mailbox is {email or '(unknown)'}"}
    if forbidden or GMAIL_READONLY_SCOPE not in list(scopes):
        return {**payload, "status": "FAIL", "reason": "token is not gmail.readonly-only"}
    return {**payload, "status": "READY", "available": True, "token_email": email, "token_scopes": list(scopes)}


def configured_sent_lookup() -> SentLookup:
    if _TEST_LOOKUP is not None:
        return _TEST_LOOKUP
    access = diagnose_daniel_sent_access()
    if not access.get("available"):
        return BlockedSentLookup(detail=str(access.get("note") or ""))
    return ExistingDanielSentLookup()


class ExistingDanielSentLookup:
    """Uses an already-authorized daniel@ readonly token. Does not create one."""

    def find_by_rfc_message_id(self, rfc_message_id: str) -> SentLookupResult:
        access = diagnose_daniel_sent_access()
        if not access.get("available"):
            return BlockedSentLookup().find_by_rfc_message_id(rfc_message_id)
        bare = _normalize_message_id(rfc_message_id)
        if not bare:
            return SentLookupResult(status="ok", reason=REASON_RFC_MISSING, records=[], access=access)
        try:
            from .oauth_consent import OAuthClientError

            client = _daniel_readonly_gmail()
            query = f"in:sent rfc822msgid:{bare}"
            hits = client.search_messages(query, max_results=5)
        except (GmailAuthError, OAuthClientError, OSError, ValueError) as exc:
            return SentLookupResult(
                status="blocked",
                reason=REASON_ACCESS_BLOCKED,
                access={**access, "available": False, "error": f"{type(exc).__name__}"},
            )
        records: list[SentControlRecord] = []
        for hit in hits:
            raw = client.get_message(hit["id"], "raw")
            decoded = decode_raw_message(raw["raw"])
            records.append(
                SentControlRecord(
                    rfc_message_id=str(decoded.get("rfc_message_id") or ""),
                    recipients=list(decoded.get("recipients") or []),
                    subject=str(decoded.get("subject") or ""),
                    body=str(decoded.get("body_text") or ""),
                    sent_at=str(decoded.get("gmail_received_at") or gmail_internal_date(raw) or ""),
                    gmail_id=str(hit.get("id") or ""),
                    mailbox=ALLOWED_SENDER,
                    fetched_via=FETCHED_VIA_DANIEL_SENT,
                )
            )
        return SentLookupResult(status="ok", reason="live_lookup", records=records, access=access)


def _daniel_readonly_gmail() -> Any:
    """Refresh only an existing daniel@ token file. No consent URL."""
    from urllib.parse import urlencode

    from .live_google import HttpReadOnlyGmail
    from .oauth_consent import OAuthClientError, _get_json, load_desktop_client, _post_form

    path = daniel_sent_token_path()
    record = json.loads(path.read_text(encoding="utf-8"))
    email = normalize_email(str(record.get("email") or record.get("account") or ""))
    scopes = record.get("scopes") or record.get("scope") or [GMAIL_READONLY_SCOPE]
    if isinstance(scopes, str):
        scopes = [item for item in scopes.replace(",", " ").split() if item]
    if email != ALLOWED_SENDER:
        raise GmailAuthError(f"authenticated mailbox is {email or '(unknown)'}, expected {ALLOWED_SENDER}")
    forbidden = [scope for scope in scopes if scope in FORBIDDEN_GMAIL_SCOPES]
    if forbidden:
        raise GmailAuthError(f"credentials include forbidden Gmail scopes: {forbidden}")
    if GMAIL_READONLY_SCOPE not in scopes:
        raise GmailAuthError("credentials must include gmail.readonly and no other Gmail scopes")
    access = str(record.get("access_token") or "")
    refresh = str(record.get("refresh_token") or "")
    if refresh:
        client = load_desktop_client()
        token = _post_form(
            str(record.get("token_uri") or client.get("token_uri") or "https://oauth2.googleapis.com/token"),
            {
                "client_id": str(record.get("client_id") or client["client_id"]),
                "client_secret": str(record.get("client_secret") or client.get("client_secret") or ""),
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            },
        )
        access = str(token.get("access_token") or access)
        if not access:
            raise OAuthClientError("daniel sent token refresh missing access_token")
        record["access_token"] = access
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        path.chmod(0o600)
    if not access:
        raise OAuthClientError("daniel sent token has no access_token")

    class _DanielHttp(HttpReadOnlyGmail):
        def __init__(self, access_token: str, email_addr: str, scope_list: list[str]) -> None:
            self.access_token = access_token
            self.email = normalize_email(email_addr)
            self.scopes = list(scope_list)

        def search_messages(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
            params = {"q": query, "maxResults": max(1, min(int(max_results), 20))}
            url = "https://gmail.googleapis.com/gmail/v1/users/me/messages?" + urlencode(params)
            page = _get_json(url, self.access_token)
            return list(page.get("messages") or [])

    return _DanielHttp(access, email, list(scopes))


def inbound_control_view(
    *,
    subject: str | None,
    body: str | None,
    rfc_message_id: str | None = None,
    recipients: list[str] | None = None,
    received_at: str | None = None,
    headers: Any = None,
    provider_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence = dict(provider_evidence or {})
    headers = headers if headers is not None else evidence.get("headers")
    rfc = rfc_message_id or evidence.get("rfc_message_id") or header_message_id(headers)
    received = received_at or evidence.get("received_at") or evidence.get("gmail_received_at") or header_date(headers)
    recips = recipients if recipients is not None else evidence.get("recipients")
    if recips is None:
        recips = [MAILBOX]
    canonical = canonical_control_payload(subject, unquoted_control_text(body))
    return {
        "rfc_message_id": rfc,
        "recipients": [normalize_email(item) for item in recips if normalize_email(item)],
        "received_at": received,
        "subject": subject,
        "body": body,
        "canonical": canonical,
        "payload_hash": payload_hash(canonical),
        "control_gmail_id": evidence.get("gmail_message_id"),
    }


def _recipient_ok(recipients: list[str], cc: list[str] | None = None) -> bool:
    tos = {normalize_email(item) for item in recipients if normalize_email(item)}
    extras = {normalize_email(item) for item in (cc or []) if normalize_email(item)}
    return tos == {MAILBOX} and not extras


def match_sent_record(inbound: dict[str, Any], record: SentControlRecord) -> dict[str, Any]:
    reasons: list[str] = []
    if _normalize_message_id(inbound.get("rfc_message_id")) != _normalize_message_id(record.rfc_message_id):
        reasons.append("message_id")
    if not _recipient_ok(record.recipients, record.cc):
        reasons.append("recipient")
    inbound_recips = [normalize_email(item) for item in inbound.get("recipients") or []]
    if inbound_recips and set(inbound_recips) != {MAILBOX}:
        reasons.append("inbound_recipient")
    sent_canonical = canonical_control_payload(record.subject, unquoted_control_text(record.body))
    if not inbound.get("canonical") or inbound.get("canonical") != sent_canonical:
        reasons.append("payload")
    inbound_at = _parse_time(str(inbound.get("received_at") or ""))
    sent_at = _parse_time(record.sent_at)
    if inbound_at is None:
        reasons.append("inbound_timing")
    if sent_at is None:
        reasons.append("sent_timing")
    if inbound_at is not None and sent_at is not None:
        delta = inbound_at - sent_at if inbound_at >= sent_at else sent_at - inbound_at
        if delta > TIMING_SLACK:
            reasons.append("timing")
    if MARKER_DESK_CTRL not in str(record.subject or "") and MARKER_DESK_CTRL not in str(record.body or ""):
        reasons.append("marker")
    ok = not reasons
    return {
        "ok": ok,
        "reasons": reasons,
        "sent_gmail_id": record.gmail_id,
        "sent_at": record.sent_at,
        "payload_hash": inbound.get("payload_hash"),
    }


def corroborate_daniel_sent(
    inbound: dict[str, Any],
    sent_lookup: SentLookup | None = None,
    *,
    persisted_proof: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Exact Sent match, or a versioned proof bound to this same control message."""
    rfc = inbound.get("rfc_message_id")
    if not _normalize_message_id(rfc):
        return {"ok": False, "accepted": False, "reason": REASON_RFC_MISSING, "full_identity_pass": False}
    if persisted_proof and persisted_proof_matches(inbound, persisted_proof):
        return {
            "ok": True,
            "accepted": True,
            "reason": REASON_EXACT,
            "via": "persisted_exact_proof",
            "proof_version": persisted_proof.get("proof_version"),
            "full_identity_pass": False,
            "sent_gmail_id": persisted_proof.get("sent_gmail_id"),
        }
    if persisted_proof:
        return {
            "ok": False,
            "accepted": False,
            "reason": REASON_LEGACY if persisted_proof.get("legacy") else REASON_MISMATCH,
            "full_identity_pass": False,
        }
    lookup = sent_lookup or configured_sent_lookup()
    found = lookup.find_by_rfc_message_id(str(rfc))
    if found.status == "blocked" or found.reason == REASON_ACCESS_BLOCKED:
        return {
            "ok": False,
            "accepted": False,
            "reason": REASON_ACCESS_BLOCKED,
            "access": found.access,
            "full_identity_pass": False,
        }
    records = [
        item
        for item in found.records
        if _normalize_message_id(item.rfc_message_id) == _normalize_message_id(rfc)
    ]
    if len(records) == 0:
        return {"ok": False, "accepted": False, "reason": REASON_MISSING, "access": found.access, "full_identity_pass": False}
    if len(records) > 1:
        return {"ok": False, "accepted": False, "reason": REASON_AMBIGUOUS, "count": len(records), "full_identity_pass": False}
    judged = match_sent_record(inbound, records[0])
    if not judged["ok"]:
        reason = REASON_MISMATCH
        if "inbound_timing" in judged["reasons"]:
            reason = REASON_INBOUND_TIMING
        elif "sent_timing" in judged["reasons"]:
            reason = REASON_SENT_TIMING
        return {
            "ok": False,
            "accepted": False,
            "reason": reason,
            "mismatch": judged["reasons"],
            "full_identity_pass": False,
        }
    return {
        "ok": True,
        "accepted": True,
        "reason": REASON_EXACT,
        "via": "live_or_fixture_sent",
        "proof_version": PROOF_VERSION,
        "sent_gmail_id": judged.get("sent_gmail_id"),
        "sent_at": judged.get("sent_at"),
        "payload_hash": judged.get("payload_hash"),
        "rfc_message_id": rfc,
        "recipient": MAILBOX,
        "inbound_at": inbound.get("received_at"),
        "full_identity_pass": False,
    }


def persisted_proof_matches(inbound: dict[str, Any], proof: dict[str, Any]) -> bool:
    if str(proof.get("proof_version") or "") != PROOF_VERSION:
        return False
    if str(proof.get("verdict") or "") != "exact_match":
        return False
    if _normalize_message_id(proof.get("rfc_message_id")) != _normalize_message_id(inbound.get("rfc_message_id")):
        return False
    if str(proof.get("payload_hash") or "") != str(inbound.get("payload_hash") or ""):
        return False
    if normalize_email(proof.get("recipient")) != MAILBOX:
        return False
    control_id = str(inbound.get("control_gmail_id") or "")
    if control_id and str(proof.get("control_gmail_id") or "") != control_id:
        return False
    return True


def authorize_control_sender(
    headers: Any,
    from_addr: str | None,
    provider_evidence: dict[str, Any] | None,
    inbound: dict[str, Any],
    sent_lookup: SentLookup | None = None,
    persisted_proof: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Authorize only when mailbox-bound AR and exact Sent corroboration both pass."""
    origin = authenticate_control_origin(headers, from_addr, provider_evidence)
    origin["full_identity_pass"] = False
    origin["accepted"] = False
    if not origin.get("mailbox_bound"):
        return origin
    proof = corroborate_daniel_sent(inbound, sent_lookup, persisted_proof=persisted_proof)
    origin["sent_corroboration"] = {k: v for k, v in proof.items() if k != "access" or v}
    if proof.get("access"):
        origin["sent_access"] = proof["access"]
    if not proof.get("ok"):
        origin["reason"] = proof.get("reason")
        origin["mismatch"] = proof.get("mismatch")
        return origin
    origin["accepted"] = True
    origin["reason"] = REASON_EXACT
    origin["proof_version"] = proof.get("proof_version")
    origin["sent_gmail_id"] = proof.get("sent_gmail_id")
    return origin


def matching_sent_record(
    subject: str,
    body: str,
    *,
    rfc_message_id: str,
    received_at: str,
    gmail_id: str = "sent-fixture",
) -> SentControlRecord:
    return SentControlRecord(
        rfc_message_id=rfc_message_id,
        recipients=[MAILBOX],
        subject=subject,
        body=body,
        sent_at=received_at,
        gmail_id=gmail_id,
        mailbox=ALLOWED_SENDER,
        fetched_via=FETCHED_VIA_FIXTURE,
    )


def fixture_sent_lookup(subject: str, body: str, *, rfc_message_id: str, received_at: str, gmail_id: str = "sent-fixture") -> MemorySentLookup:
    return MemorySentLookup([matching_sent_record(subject, body, rfc_message_id=rfc_message_id, received_at=received_at, gmail_id=gmail_id)])
