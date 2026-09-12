"""READ-ONLY Daniel plus-control discovery via history poll.

Uses the existing Daniel readonly credential only. Does not create Pub/Sub,
does not change Gmail filters/labels, and never writes contactus watch_cursors.
Handles messageAdded and labelAdded, pagination, repeated events, and a
bounded SENT+Control reconcile after history expiration.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from .constants import (
    ALLOWED_SENDER,
    LEAD_DESK_CONTROL_LABEL,
    LEAD_DESK_CONTROL_LABEL_ID,
    LEAD_DESK_PLUS_MAILBOX,
    LEAD_DESK_PLUS_RESULTS_MAILBOX,
    LEAD_DESK_RESULTS_LABEL,
    LEAD_DESK_RESULTS_LABEL_ID,
    MARKER_DESK_CTRL,
    MARKER_PLUS_RESULT,
    STALE_PLUS_CONTROL_ID,
)
from .desk_plus_proof import _plus_gmail_client, _profile_email_from_client
from .desk_plus_store import (
    STATUS_PENDING,
    STATUS_PROCESSED,
    STATUS_SKIPPED,
    ensure_plus_tables,
    get_plus_cursor,
    get_seen,
    is_stale_forbidden,
    record_seen,
    save_plus_cursor,
    update_seen,
)
from .desk_sent_proof import diagnose_daniel_sent_access
from .eligibility import emails_from_header, normalize_email
from .gmail_readonly import GmailAuthError
from .oauth_consent import _get_json


RECONCILE_MAX = 25
CONTROL_LABELS = {LEAD_DESK_CONTROL_LABEL_ID, LEAD_DESK_CONTROL_LABEL}
RESULTS_LABELS = {LEAD_DESK_RESULTS_LABEL_ID, LEAD_DESK_RESULTS_LABEL}
SENT_LABEL = "SENT"

REASON_STALE_FORBIDDEN = "stale_plus_control_forbidden"
REASON_RESULTS_LOOP = "plus_results_loop_excluded"
REASON_NOT_CONTROL_LABEL = "control_label_missing"
REASON_NOT_SENT = "sent_label_missing"
REASON_WRONG_ENVELOPE = "plus_discovery_envelope_mismatch"
REASON_HISTORY_EXPIRED = "plus_history_expired"

_TEST_CLIENT: Any = None


class PlusHistoryExpired(RuntimeError):
    pass


def set_test_plus_discover_client(client: Any | None) -> None:
    global _TEST_CLIENT
    _TEST_CLIENT = client


def _discover_client() -> Any:
    if _TEST_CLIENT is not None:
        return _TEST_CLIENT
    return _plus_gmail_client()


def plus_history_query() -> str:
    """SENT + Control label, exact plus recipient. Inbox is not required."""
    return (
        f"in:sent label:{LEAD_DESK_CONTROL_LABEL_ID} "
        f"to:{LEAD_DESK_PLUS_MAILBOX} "
        f"-to:{LEAD_DESK_PLUS_RESULTS_MAILBOX} "
        f"-label:{LEAD_DESK_RESULTS_LABEL_ID} "
        f"subject:{MARKER_DESK_CTRL}"
    )


def extract_plus_history_ids(history_response: dict[str, Any]) -> list[dict[str, str]]:
    """messageAdded and Control labelAdded. Dedupes repeated/reordered events."""
    found: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(message: dict[str, Any], event: str) -> None:
        mid = str(message.get("id") or "").strip()
        if not mid or mid in seen:
            return
        seen.add(mid)
        found.append({"id": mid, "threadId": str(message.get("threadId") or ""), "event": event})

    for record in history_response.get("history") or []:
        for added in record.get("messagesAdded") or []:
            _add(added.get("message") or {}, "messageAdded")
        for labeled in record.get("labelsAdded") or []:
            labels = set(labeled.get("labelIds") or [])
            if labels & CONTROL_LABELS:
                _add(labeled.get("message") or {}, "labelAdded")
    return found


def fetch_plus_history(client: Any, start_history_id: str) -> dict[str, Any]:
    """Paginated history with messageAdded and labelAdded. Not the contactus helper."""
    if hasattr(client, "plus_history"):
        return client.plus_history(start_history_id)
    token = str(getattr(client, "access_token", "") or "")
    if not token:
        raise GmailAuthError("missing access token for plus history")
    params = [
        ("startHistoryId", str(start_history_id)),
        ("historyTypes", "messageAdded"),
        ("historyTypes", "labelAdded"),
    ]
    url = "https://gmail.googleapis.com/gmail/v1/users/me/history?" + urlencode(params)
    merged: dict[str, Any] = {"history": [], "historyId": str(start_history_id)}
    while url:
        try:
            page = _get_json(url, token)
        except Exception as exc:
            text = str(exc)
            if "404" in text or "not found" in text.lower() or "historyId" in text:
                raise PlusHistoryExpired(text) from exc
            raise
        merged["history"].extend(page.get("history") or [])
        if page.get("historyId"):
            merged["historyId"] = str(page["historyId"])
        nxt = page.get("nextPageToken")
        if not nxt:
            break
        url = "https://gmail.googleapis.com/gmail/v1/users/me/history?" + urlencode(params + [("pageToken", nxt)])
    return merged


def _header_values(headers: Any, name: str) -> list[str]:
    found: list[str] = []
    items = headers.items() if isinstance(headers, dict) else (headers or [])
    for item in items:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            key, value = item[0], item[1]
        elif isinstance(item, dict):
            key, value = item.get("name"), item.get("value")
        else:
            continue
        if str(key or "").lower() == name.lower():
            found.extend(emails_from_header(str(value or "")))
    return [normalize_email(addr) for addr in found if normalize_email(addr)]


def _labels_of(message: dict[str, Any]) -> set[str]:
    return {str(item) for item in (message.get("labelIds") or message.get("labels") or [])}


def prefilter_plus_candidate(message: dict[str, Any]) -> dict[str, Any]:
    """Metadata-only gate. Does not store bodies."""
    mid = str(message.get("id") or "").strip()
    if is_stale_forbidden(mid):
        return {"ok": False, "reason": REASON_STALE_FORBIDDEN, "gmail_message_id": mid}
    labels = _labels_of(message)
    if labels & RESULTS_LABELS:
        return {"ok": False, "reason": REASON_RESULTS_LOOP, "gmail_message_id": mid}
    if not (labels & CONTROL_LABELS):
        return {"ok": False, "reason": REASON_NOT_CONTROL_LABEL, "gmail_message_id": mid}
    if SENT_LABEL not in labels:
        return {"ok": False, "reason": REASON_NOT_SENT, "gmail_message_id": mid}
    headers = message.get("headers")
    if not headers and isinstance(message.get("payload"), dict):
        headers = (message.get("payload") or {}).get("headers") or []
    tos = _header_values(headers, "To")
    ccs = _header_values(headers, "Cc")
    bccs = _header_values(headers, "Bcc")
    froms = _header_values(headers, "From")
    dests = set(tos + ccs + bccs)
    if LEAD_DESK_PLUS_RESULTS_MAILBOX in dests or MARKER_PLUS_RESULT in str(message.get("subject") or ""):
        return {"ok": False, "reason": REASON_RESULTS_LOOP, "gmail_message_id": mid}
    if headers:
        if set(froms) != {ALLOWED_SENDER} or dests != {LEAD_DESK_PLUS_MAILBOX}:
            return {"ok": False, "reason": REASON_WRONG_ENVELOPE, "gmail_message_id": mid}
    return {"ok": True, "gmail_message_id": mid, "labels": sorted(labels)}


def _get_metadata(client: Any, message_id: str) -> dict[str, Any]:
    raw = client.get_message(message_id, "metadata")
    return raw or {}


def _search_ids(client: Any, query: str, max_results: int) -> list[str]:
    if hasattr(client, "search_messages"):
        hits = client.search_messages(query, max_results=max_results)
        return [str(item.get("id") or "") for item in hits or [] if item.get("id")]
    token = str(getattr(client, "access_token", "") or "")
    params = {"q": query, "maxResults": max(1, min(int(max_results), RECONCILE_MAX))}
    page = _get_json("https://gmail.googleapis.com/gmail/v1/users/me/messages?" + urlencode(params), token)
    return [str(item.get("id") or "") for item in page.get("messages") or [] if item.get("id")]


def _profile(client: Any) -> dict[str, Any]:
    if hasattr(client, "get_profile"):
        return client.get_profile() or {}
    email = _profile_email_from_client(client)
    token = str(getattr(client, "access_token", "") or "")
    profile = {"emailAddress": email}
    if token:
        try:
            profile = _get_json("https://gmail.googleapis.com/gmail/v1/users/me/profile", token)
        except Exception:
            pass
    return profile


def discover_plus_controls(layer: Any, *, client: Any | None = None) -> dict[str, Any]:
    """One READ-ONLY poll. Checkpoints Daniel state only. Does not execute saves."""
    ensure_plus_tables(layer)
    access = diagnose_daniel_sent_access()
    report: dict[str, Any] = {
        "ok": False,
        "contactus_traffic": False,
        "stale_forbidden": STALE_PLUS_CONTROL_ID,
        "candidates": [],
        "skipped": [],
        "access": access,
    }
    if not access.get("available") and _TEST_CLIENT is None and client is None:
        report["reason"] = "daniel_readonly_unavailable"
        return report
    gmail = client or _discover_client()
    try:
        profile = _profile(gmail)
        profile_email = normalize_email(str(profile.get("emailAddress") or profile.get("email") or ""))
        if profile_email != ALLOWED_SENDER:
            report["reason"] = "plus_mailbox_not_daniel"
            report["profile_email"] = profile_email
            return report
        profile_hid = str(profile.get("historyId") or "")
        cursor = get_plus_cursor(layer)
        candidates: list[dict[str, str]] = []
        expired = False
        if cursor and cursor.get("history_id"):
            try:
                history = fetch_plus_history(gmail, str(cursor["history_id"]))
                candidates.extend(extract_plus_history_ids(history))
                if history.get("historyId"):
                    save_plus_cursor(layer, str(history["historyId"]), profile_history_id=profile_hid)
            except PlusHistoryExpired:
                expired = True
                report["history_expired"] = True
        else:
            if profile_hid:
                save_plus_cursor(layer, profile_hid, profile_history_id=profile_hid)
            expired = True
            report["initialized_cursor"] = True
        if expired:
            query = plus_history_query()
            report["reconcile_query"] = query
            for mid in _search_ids(gmail, query, RECONCILE_MAX):
                candidates.append({"id": mid, "threadId": "", "event": "reconcile"})
            if profile_hid:
                save_plus_cursor(layer, profile_hid, profile_history_id=profile_hid, reconciled=True)
        accepted: list[str] = []
        skipped: list[dict[str, str]] = []
        for item in candidates:
            mid = str(item.get("id") or "").strip()
            if not mid:
                continue
            if is_stale_forbidden(mid):
                record_seen(layer, mid, event=item.get("event") or "stale", status=STATUS_SKIPPED, reason=REASON_STALE_FORBIDDEN)
                update_seen(layer, mid, status=STATUS_SKIPPED, reason=REASON_STALE_FORBIDDEN)
                skipped.append({"id": mid, "reason": REASON_STALE_FORBIDDEN})
                continue
            already = get_seen(layer, mid)
            if already and already.get("status") in {STATUS_PROCESSED, STATUS_SKIPPED}:
                continue
            try:
                meta = _get_metadata(gmail, mid)
            except (GmailAuthError, KeyError, OSError, ValueError):
                record_seen(layer, mid, event=item.get("event") or "history", status=STATUS_PENDING, reason="metadata_unavailable")
                continue
            if str(meta.get("id") or "") and str(meta.get("id") or "") != mid:
                skipped.append({"id": mid, "reason": "plus_fetched_id_mismatch"})
                continue
            verdict = prefilter_plus_candidate(meta)
            if not verdict.get("ok"):
                reason = str(verdict.get("reason") or "skipped")
                if reason == REASON_NOT_CONTROL_LABEL and item.get("event") == "messageAdded":
                    record_seen(layer, mid, event="messageAdded", status=STATUS_PENDING, reason=reason)
                    continue
                record_seen(layer, mid, event=item.get("event") or "history", status=STATUS_SKIPPED, reason=reason)
                update_seen(layer, mid, status=STATUS_SKIPPED, reason=reason)
                skipped.append({"id": mid, "reason": reason})
                continue
            record_seen(layer, mid, event=item.get("event") or "history", status=STATUS_PENDING)
            accepted.append(mid)
        report.update(
            {
                "ok": True,
                "candidates": accepted,
                "skipped": skipped,
                "cursor": get_plus_cursor(layer),
                "profile_history_id": profile_hid,
            }
        )
        return report
    except (GmailAuthError, OSError, ValueError) as exc:
        report["reason"] = "plus_discovery_error"
        report["error"] = type(exc).__name__
        return report
