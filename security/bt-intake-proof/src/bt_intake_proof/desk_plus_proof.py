"""Hidden daniel+lead-desk@ control transport.

Internal Lead Desk controls may arrive as self-addressed Gmail:

    daniel@btpestcontrol.com → daniel+lead-desk@btpestcontrol.com

Self-addressed Gmail does not carry the inbound Authentication-Results
headers used by the contactus@ path. This module must not call
`authenticate_control_origin` and must not treat From:/To: headers alone
as proof.

Authorization is only for a message retrieved through the authenticated
daniel@ Gmail account that has all of:

- users.getProfile on the live token equals daniel@btpestcontrol.com
- Gmail message exists and the returned id equals the requested id
- SENT label present
- every From/To/Cc/Bcc occurrence from the raw provider mail:
  From is only daniel@; To/Cc/Bcc together are only daniel+lead-desk@
- provider internalDate is present and fresh at first processing
- current valid control metadata

This milestone authorizes `revise_draft` only.

Customer or external mail cannot satisfy this path by spoofing headers
or copying control syntax. The contactus@ path is unchanged.

Freshness compared with contactus@: that path allows 15 minutes between
daniel@ Sent time and contactus inbound received time. This path allows
15 minutes between Gmail internalDate and processing time (injected
clock in tests). An unchanged draft/nonce is not indefinite approval.
Cached verified outcomes may be reread without re-execution. The
already-sent live control is not grandfathered.

Fixture fetch markers are test injection only. The production entry
always calls users.getProfile and users.messages.get through the token.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .constants import (
    ALLOWED_SENDER,
    LEAD_DESK_PLUS_MAILBOX,
    MARKER_DESK_CTRL,
    TRANSPORT_PLUS,
)
from .desk_control import INTENT_REVISE
from .desk_origin import unquoted_control_text
from .desk_sent_proof import (
    REASON_ACCESS_BLOCKED,
    TIMING_SLACK,
    _daniel_readonly_gmail,
    _parse_time,
    canonical_control_payload,
    diagnose_daniel_sent_access,
    header_date,
    header_message_id,
)
from .eligibility import emails_from_header, normalize_email
from .gmail_readonly import GmailAuthError, decode_raw_message, gmail_internal_date

FETCHED_VIA_DANIEL_PLUS = "daniel_gmail_plus_control_api"
FETCHED_VIA_FIXTURE_PLUS = "fixture_daniel_plus_control"
PLUS_MILESTONE_INTENT = INTENT_REVISE
PLUS_FRESHNESS = TIMING_SLACK
PLUS_FUTURE_SKEW = timedelta(seconds=60)

REASON_PLUS_FETCH = "plus_address_fetch_required"
REASON_PLUS_MAILBOX = "plus_mailbox_not_daniel"
REASON_PLUS_MISSING = "plus_gmail_message_missing"
REASON_PLUS_ID = "plus_fetched_id_mismatch"
REASON_PLUS_SENT = "plus_sent_label_missing"
REASON_PLUS_FROM = "plus_from_not_daniel"
REASON_PLUS_TO = "plus_recipient_mismatch"
REASON_PLUS_HEADERS = "plus_headers_missing_or_malformed"
REASON_PLUS_META = "plus_control_metadata_invalid"
REASON_PLUS_FRESHNESS_MISSING = "plus_internal_date_missing"
REASON_PLUS_FRESHNESS_INVALID = "plus_internal_date_invalid"
REASON_PLUS_FRESHNESS_FUTURE = "plus_internal_date_future"
REASON_PLUS_FRESHNESS_EXPIRED = "plus_internal_date_expired"
REASON_PLUS_PROFILE = "plus_live_profile_unverified"
REASON_PLUS_OK = "plus_address_sent_mailbox_match"
REASON_PLUS_INTENT = "plus_intent_not_in_milestone"

SENT_LABEL = "SENT"

_TEST_ALLOW_FIXTURE = False
_TEST_PLUS_CLIENT: Any = None
_TEST_PLUS_NOW: datetime | None = None
_TEST_PLUS_PROFILE: Callable[[], dict[str, Any]] | None = None


def set_test_plus_fixtures(enabled: bool) -> None:
    """Test injection only. Production never enables fixture fetch markers."""
    global _TEST_ALLOW_FIXTURE
    _TEST_ALLOW_FIXTURE = bool(enabled)


def set_test_plus_client(client: Any | None) -> None:
    """Test injection only. Replaces the live Daniel Gmail client."""
    global _TEST_PLUS_CLIENT
    _TEST_PLUS_CLIENT = client


def set_test_plus_now(value: datetime | None) -> None:
    """Test injection only. Clock for plus-path internalDate freshness."""
    global _TEST_PLUS_NOW
    _TEST_PLUS_NOW = value


def set_test_plus_profile(func: Callable[[], dict[str, Any]] | None) -> None:
    """Test injection only. Replaces users.getProfile."""
    global _TEST_PLUS_PROFILE
    _TEST_PLUS_PROFILE = func


def plus_now() -> datetime:
    if _TEST_PLUS_NOW is not None:
        now = _TEST_PLUS_NOW
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def plus_recipient_ok(recipients: list[str] | None, cc: list[str] | None = None, bcc: list[str] | None = None) -> bool:
    tos = {normalize_email(item) for item in (recipients or []) if normalize_email(item)}
    extras = {normalize_email(item) for item in (cc or []) if normalize_email(item)}
    hidden = {normalize_email(item) for item in (bcc or []) if normalize_email(item)}
    return tos == {LEAD_DESK_PLUS_MAILBOX} and not extras and not hidden


def _labels(evidence: dict[str, Any]) -> list[str]:
    raw = evidence.get("labels")
    if raw is None:
        raw = evidence.get("labelIds") or []
    return [str(item).upper() for item in raw if str(item).strip()]


def _header_items(headers: Any) -> list[tuple[str, str]]:
    if not headers:
        return []
    items = headers.items() if isinstance(headers, dict) else headers
    found: list[tuple[str, str]] = []
    for item in items:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            found.append((str(item[0]), str(item[1])))
    return found


def _header_present(headers: Any, name: str) -> bool:
    want = name.lower()
    return any(key.lower() == want for key, _value in _header_items(headers))


def _header_addresses(headers: Any, name: str) -> list[str]:
    want = name.lower()
    found: list[str] = []
    for key, value in _header_items(headers):
        if key.lower() != want:
            continue
        parsed = [normalize_email(addr) for addr in emails_from_header(value) if normalize_email(addr)]
        found.extend(parsed)
    return found


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
    if payload.get("internal_date") is None and payload.get("internalDate") is None:
        if payload.get("received_at"):
            payload["internal_date"] = payload["received_at"]
    return payload


def _provider_internal_date(evidence: dict[str, Any]) -> tuple[datetime | None, str | None]:
    if "internal_date" not in evidence and "internalDate" not in evidence:
        return None, REASON_PLUS_FRESHNESS_MISSING
    raw = evidence.get("internal_date")
    if raw is None:
        raw = evidence.get("internalDate")
    if raw is None or raw == "":
        return None, REASON_PLUS_FRESHNESS_MISSING
    if isinstance(raw, (int, float)) or (isinstance(raw, str) and str(raw).strip().isdigit()):
        try:
            ms = int(raw)
        except (TypeError, ValueError):
            return None, REASON_PLUS_FRESHNESS_INVALID
        if ms <= 0:
            return None, REASON_PLUS_FRESHNESS_INVALID
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc), None
    parsed = _parse_time(str(raw))
    if parsed is None:
        return None, REASON_PLUS_FRESHNESS_INVALID
    return parsed, None


def judge_plus_freshness(evidence: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """First-processing freshness against provider internalDate. Not Date:."""
    when = now or plus_now()
    parsed, missing = _provider_internal_date(evidence)
    if missing:
        return {"ok": False, "reason": missing, "window_seconds": int(PLUS_FRESHNESS.total_seconds())}
    if parsed is None:
        return {"ok": False, "reason": REASON_PLUS_FRESHNESS_INVALID, "window_seconds": int(PLUS_FRESHNESS.total_seconds())}
    if parsed > when + PLUS_FUTURE_SKEW:
        return {"ok": False, "reason": REASON_PLUS_FRESHNESS_FUTURE, "internal_date": parsed.isoformat(), "now": when.isoformat()}
    if when - parsed > PLUS_FRESHNESS:
        return {"ok": False, "reason": REASON_PLUS_FRESHNESS_EXPIRED, "internal_date": parsed.isoformat(), "now": when.isoformat()}
    return {
        "ok": True,
        "internal_date": parsed.isoformat(),
        "now": when.isoformat(),
        "window_seconds": int(PLUS_FRESHNESS.total_seconds()),
        "compared_to": "contactus_sent_vs_received_15m",
    }


def _envelope_from_raw_headers(headers: Any) -> dict[str, Any]:
    if not headers or not _header_present(headers, "From") or not _header_present(headers, "To"):
        return {"ok": False, "reason": REASON_PLUS_HEADERS}
    froms = _header_addresses(headers, "From")
    tos = _header_addresses(headers, "To")
    ccs = _header_addresses(headers, "Cc")
    bccs = _header_addresses(headers, "Bcc")
    all_addrs = froms + tos + ccs + bccs
    if not froms or not tos or any("@" not in addr for addr in all_addrs):
        return {"ok": False, "reason": REASON_PLUS_HEADERS}
    if set(froms) != {ALLOWED_SENDER}:
        return {"ok": False, "reason": REASON_PLUS_FROM, "from": froms, "to": tos, "cc": ccs, "bcc": bccs}
    dests = set(tos) | set(ccs) | set(bccs)
    if dests != {LEAD_DESK_PLUS_MAILBOX} or set(tos) != {LEAD_DESK_PLUS_MAILBOX}:
        return {"ok": False, "reason": REASON_PLUS_TO, "from": froms, "to": tos, "cc": ccs, "bcc": bccs}
    return {"ok": True, "from": froms, "to": tos, "cc": ccs, "bcc": bccs}


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
        "freshness_window": f"{int(PLUS_FRESHNESS.total_seconds())}s_internalDate",
    }
    fetched = str(evidence.get("fetched_via") or "")
    if fetched == FETCHED_VIA_FIXTURE_PLUS:
        if not _TEST_ALLOW_FIXTURE:
            return {**base, "reason": REASON_PLUS_FETCH}
    elif fetched == FETCHED_VIA_DANIEL_PLUS:
        if not evidence.get("live_profile_verified") and not _TEST_ALLOW_FIXTURE:
            return {**base, "reason": REASON_PLUS_PROFILE}
    else:
        return {**base, "reason": REASON_PLUS_FETCH}
    mailbox = normalize_email(evidence.get("authenticated_mailbox") or evidence.get("mailbox"))
    if mailbox != ALLOWED_SENDER:
        return {**base, "reason": REASON_PLUS_MAILBOX}
    gmail_id = str(evidence.get("gmail_message_id") or "")
    if not gmail_id or evidence.get("message_exists") is False:
        return {**base, "reason": REASON_PLUS_MISSING}
    if SENT_LABEL not in _labels(evidence):
        return {**base, "reason": REASON_PLUS_SENT}
    if normalize_email(from_addr) != ALLOWED_SENDER:
        return {**base, "reason": REASON_PLUS_FROM}
    envelope = _envelope_from_raw_headers(evidence.get("headers"))
    if not envelope.get("ok"):
        return {**base, "reason": envelope.get("reason") or REASON_PLUS_HEADERS}
    inbound_to = [normalize_email(item) for item in inbound.get("recipients") or [] if normalize_email(item)]
    inbound_cc = [normalize_email(item) for item in inbound.get("cc") or evidence.get("cc") or [] if normalize_email(item)]
    inbound_bcc = [normalize_email(item) for item in inbound.get("bcc") or evidence.get("bcc") or [] if normalize_email(item)]
    if inbound_to or inbound_cc or inbound_bcc:
        if not plus_recipient_ok(inbound_to or envelope.get("to"), inbound_cc, inbound_bcc):
            return {**base, "reason": REASON_PLUS_TO}
    fresh = judge_plus_freshness(evidence)
    if not fresh.get("ok"):
        return {**base, "reason": fresh.get("reason"), "freshness": fresh}
    if not inbound.get("canonical") or not inbound.get("payload_hash"):
        return {**base, "reason": REASON_PLUS_META}
    return {
        **base,
        "accepted": True,
        "ok": True,
        "reason": REASON_PLUS_OK,
        "proof_version": "desk-plus-v1",
        "sent_gmail_id": gmail_id,
        "sent_at": fresh.get("internal_date"),
        "gmail_message_id": gmail_id,
        "freshness": fresh,
        "live_profile_verified": bool(evidence.get("live_profile_verified")),
    }


def plus_evidence_from_fetched_message(
    message: dict[str, Any],
    *,
    mailbox: str,
    fetched_via: str = FETCHED_VIA_DANIEL_PLUS,
    live_profile_verified: bool = False,
) -> dict[str, Any]:
    """Shape a Daniel-mailbox get() into plus-path evidence. Does not authorize."""
    decoded: dict[str, Any] = {}
    if message.get("raw"):
        decoded = decode_raw_message(message["raw"])
    headers = decoded.get("headers") or []
    to_addrs = _header_addresses(headers, "To")
    cc_addrs = _header_addresses(headers, "Cc")
    bcc_addrs = _header_addresses(headers, "Bcc")
    internal = gmail_internal_date(message)
    return {
        "fetched_via": fetched_via,
        "authenticated_mailbox": normalize_email(mailbox),
        "gmail_message_id": message.get("id"),
        "message_exists": bool(message.get("id")),
        "labels": list(message.get("labelIds") or message.get("labels") or []),
        "headers": headers,
        "rfc_message_id": decoded.get("rfc_message_id") or header_message_id(headers),
        "received_at": internal or decoded.get("gmail_received_at") or header_date(headers),
        "internal_date": internal,
        "internalDate": message.get("internalDate"),
        "recipients": to_addrs,
        "cc": cc_addrs,
        "bcc": bcc_addrs,
        "sender": decoded.get("sender") or "",
        "subject": decoded.get("subject") or "",
        "body": decoded.get("body_text") or "",
        "sent_at": internal,
        "live_profile_verified": bool(live_profile_verified),
    }


def _live_daniel_users_profile(access_token: str) -> str:
    """users.getProfile through the token. Token-file email is not identity."""
    from .oauth_consent import _get_json

    profile = _get_json("https://gmail.googleapis.com/gmail/v1/users/me/profile", access_token)
    email = normalize_email(str(profile.get("emailAddress") or ""))
    if email != ALLOWED_SENDER:
        raise GmailAuthError(f"authenticated mailbox is {email or '(unknown)'}, expected {ALLOWED_SENDER}")
    return email


def _plus_gmail_client() -> Any:
    if _TEST_PLUS_CLIENT is not None:
        return _TEST_PLUS_CLIENT
    return _daniel_readonly_gmail()


def _profile_email_from_client(client: Any) -> str:
    if _TEST_PLUS_PROFILE is not None:
        profile = _TEST_PLUS_PROFILE()
        email = normalize_email(str((profile or {}).get("emailAddress") or (profile or {}).get("email") or ""))
        if email != ALLOWED_SENDER:
            raise GmailAuthError(f"authenticated mailbox is {email or '(unknown)'}, expected {ALLOWED_SENDER}")
        return email
    if _TEST_PLUS_CLIENT is client and hasattr(client, "get_profile"):
        profile = client.get_profile()
        email = normalize_email(str((profile or {}).get("emailAddress") or (profile or {}).get("email") or ""))
        if email != ALLOWED_SENDER:
            raise GmailAuthError(f"authenticated mailbox is {email or '(unknown)'}, expected {ALLOWED_SENDER}")
        return email
    token = str(getattr(client, "access_token", "") or "")
    if not token:
        raise GmailAuthError("missing access token for live profile")
    return _live_daniel_users_profile(token)


def fetch_plus_control_from_daniel(gmail_message_id: str) -> dict[str, Any]:
    """Read one message after live users.getProfile. No new OAuth. No fixture markers."""
    access = diagnose_daniel_sent_access()
    if not access.get("available") and _TEST_PLUS_CLIENT is None:
        return {"ok": False, "reason": REASON_ACCESS_BLOCKED, "access": access}
    bare = str(gmail_message_id or "").strip()
    if not bare:
        return {"ok": False, "reason": REASON_PLUS_MISSING, "access": access}
    try:
        from .oauth_consent import OAuthClientError

        client = _plus_gmail_client()
        profile_email = _profile_email_from_client(client)
        if profile_email != ALLOWED_SENDER:
            return {"ok": False, "reason": REASON_PLUS_MAILBOX, "access": access, "profile_email": profile_email}
        raw = client.get_message(bare, "raw")
    except (GmailAuthError, OAuthClientError, OSError, ValueError) as exc:
        reason = REASON_PLUS_MAILBOX if "authenticated mailbox" in str(exc) else REASON_PLUS_MISSING
        return {"ok": False, "reason": reason, "error": type(exc).__name__, "detail": str(exc), "access": access}
    if not raw or not raw.get("id"):
        return {"ok": False, "reason": REASON_PLUS_MISSING, "access": access}
    if str(raw.get("id") or "") != bare:
        return {
            "ok": False,
            "reason": REASON_PLUS_ID,
            "requested_id": bare,
            "fetched_id": str(raw.get("id") or ""),
            "access": access,
        }
    evidence = plus_evidence_from_fetched_message(
        raw,
        mailbox=profile_email,
        fetched_via=FETCHED_VIA_DANIEL_PLUS,
        live_profile_verified=True,
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
        "profile_email": profile_email,
        "live_profile_verified": True,
    }


def search_plus_controls_in_daniel_sent(*, max_results: int = 10) -> dict[str, Any]:
    """Manual SENT list helper. Not a watch, history, or label-added recovery path."""
    access = diagnose_daniel_sent_access()
    if not access.get("available") and _TEST_PLUS_CLIENT is None:
        return {"ok": False, "reason": REASON_ACCESS_BLOCKED, "access": access, "messages": []}
    query = f"in:sent to:{LEAD_DESK_PLUS_MAILBOX} subject:{MARKER_DESK_CTRL}"
    try:
        client = _plus_gmail_client()
        profile_email = _profile_email_from_client(client)
        if profile_email != ALLOWED_SENDER:
            return {"ok": False, "reason": REASON_PLUS_MAILBOX, "access": access, "messages": []}
        hits = client.search_messages(query, max_results=max_results)
    except (GmailAuthError, OSError, ValueError) as exc:
        return {"ok": False, "reason": REASON_ACCESS_BLOCKED, "error": type(exc).__name__, "access": access, "messages": []}
    return {"ok": True, "query": query, "access": access, "messages": list(hits or []), "automatic": False}


def looks_like_plus_control_payload(subject: str | None, body: str | None) -> bool:
    canonical = canonical_control_payload(subject, unquoted_control_text(body))
    return bool(canonical)
