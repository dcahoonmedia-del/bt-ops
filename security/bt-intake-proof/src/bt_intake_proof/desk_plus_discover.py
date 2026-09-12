"""READ-ONLY Daniel plus-control discovery via history poll.

Uses the existing Daniel readonly credential only. Does not create Pub/Sub,
does not change Gmail filters/labels, and never writes contactus watch_cursors.
Handles messageAdded and labelAdded, pagination, repeated events, and a
paginated SENT recovery over the freshness window after history expiration.

Opaque Gmail label IDs are never placed in `q`. Recovery uses API labelIds
resolved by the current label name.
"""

from __future__ import annotations

from datetime import datetime
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
from .desk_plus_proof import PLUS_FRESHNESS, _plus_gmail_client, _profile_email_from_client, plus_now
from .desk_plus_store import (
    STATUS_AWAITING_LABEL,
    STATUS_PENDING,
    STATUS_PROCESSED,
    STATUS_PROCESSING,
    STATUS_SKIPPED,
    checkpoint_history_events,
    ensure_plus_tables,
    get_plus_cursor,
    get_seen,
    is_stale_forbidden,
    lease_expired,
    record_seen,
    unclassified_seen_ids,
    update_seen,
)
from .desk_sent_proof import diagnose_daniel_sent_access
from .eligibility import emails_from_header, normalize_email
from .gmail_readonly import GmailAuthError
from .oauth_consent import _get_json


RECOVERY_PAGE_SIZE = 20
RECOVERY_MAX_PAGES = 50
CONTROL_LABELS = {LEAD_DESK_CONTROL_LABEL_ID, LEAD_DESK_CONTROL_LABEL}
RESULTS_LABELS = {LEAD_DESK_RESULTS_LABEL_ID, LEAD_DESK_RESULTS_LABEL}
SENT_LABEL = "SENT"

REASON_STALE_FORBIDDEN = "stale_plus_control_forbidden"
REASON_RESULTS_LOOP = "plus_results_loop_excluded"
REASON_NOT_CONTROL_LABEL = "control_label_missing"
REASON_NOT_SENT = "sent_label_missing"
REASON_WRONG_ENVELOPE = "plus_discovery_envelope_mismatch"
REASON_HISTORY_EXPIRED = "plus_history_expired"
REASON_LABEL_LOOKUP = "plus_label_lookup_failed"

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


def plus_recovery_query(*, now: datetime | None = None) -> str:
    """Supported search syntax only. No opaque label IDs in q."""
    when = now or plus_now()
    after = int((when - PLUS_FRESHNESS).timestamp())
    return (
        f"in:sent to:{LEAD_DESK_PLUS_MAILBOX} "
        f"-to:{LEAD_DESK_PLUS_RESULTS_MAILBOX} "
        f"subject:{MARKER_DESK_CTRL} after:{after}"
    )


def plus_history_query() -> str:
    """Backward-compatible name for the freshness-window recovery query."""
    return plus_recovery_query()


def extract_plus_history_ids(
    history_response: dict[str, Any],
    *,
    control_labels: set[str] | None = None,
) -> list[dict[str, str]]:
    """messageAdded and Control labelAdded. Dedupes repeated/reordered events."""
    wanted = set(control_labels or CONTROL_LABELS)
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
            labels = {str(item) for item in (labeled.get("labelIds") or [])}
            if labels & wanted:
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


def _list_labels(client: Any) -> list[dict[str, str]]:
    if hasattr(client, "list_labels"):
        return list(client.list_labels() or [])
    token = str(getattr(client, "access_token", "") or "")
    if not token:
        raise GmailAuthError("missing access token for plus label list")
    page = _get_json("https://gmail.googleapis.com/gmail/v1/users/me/labels", token)
    return list(page.get("labels") or [])


def resolve_plus_labels(client: Any) -> dict[str, Any]:
    """Resolve Control/Results by current name. Fail closed if lookup or names fail."""
    try:
        labels = _list_labels(client)
    except Exception as exc:
        return {
            "ok": False,
            "reason": REASON_LABEL_LOOKUP,
            "error": type(exc).__name__,
            "control_match": set(CONTROL_LABELS),
            "results_match": set(RESULTS_LABELS),
            "labels": [],
        }
    control_id = None
    results_id = None
    for item in labels:
        name = str(item.get("name") or "")
        lid = str(item.get("id") or "")
        if name == LEAD_DESK_CONTROL_LABEL:
            control_id = lid
        if name == LEAD_DESK_RESULTS_LABEL:
            results_id = lid
    if not control_id or not results_id:
        return {
            "ok": False,
            "reason": "required_plus_label_missing",
            "control_id": control_id,
            "results_id": results_id,
            "control_match": {item for item in (control_id, LEAD_DESK_CONTROL_LABEL, LEAD_DESK_CONTROL_LABEL_ID) if item},
            "results_match": {item for item in (results_id, LEAD_DESK_RESULTS_LABEL, LEAD_DESK_RESULTS_LABEL_ID) if item},
            "labels": labels,
        }
    return {
        "ok": True,
        "control_id": control_id,
        "results_id": results_id,
        "control_match": {control_id, LEAD_DESK_CONTROL_LABEL, LEAD_DESK_CONTROL_LABEL_ID},
        "results_match": {results_id, LEAD_DESK_RESULTS_LABEL, LEAD_DESK_RESULTS_LABEL_ID},
        "labels": labels,
    }


def prefilter_plus_candidate(
    message: dict[str, Any],
    *,
    control_match: set[str] | None = None,
    results_match: set[str] | None = None,
) -> dict[str, Any]:
    """Metadata-only gate. Does not store bodies."""
    mid = str(message.get("id") or "").strip()
    if is_stale_forbidden(mid):
        return {"ok": False, "reason": REASON_STALE_FORBIDDEN, "gmail_message_id": mid}
    labels = _labels_of(message)
    control_ids = set(control_match or CONTROL_LABELS)
    results_ids = set(results_match or RESULTS_LABELS)
    if labels & results_ids:
        return {"ok": False, "reason": REASON_RESULTS_LOOP, "gmail_message_id": mid}
    if not (labels & control_ids):
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


def _list_message_ids(
    client: Any,
    query: str,
    *,
    label_ids: list[str] | None = None,
    page_size: int = RECOVERY_PAGE_SIZE,
) -> list[str]:
    """Paginate messages.list. labelIds are API parameters, never q tokens."""
    found: list[str] = []
    if hasattr(client, "search_messages"):
        token = None
        for _ in range(RECOVERY_MAX_PAGES):
            try:
                hits = client.search_messages(
                    query,
                    max_results=page_size,
                    label_ids=label_ids,
                    page_token=token,
                )
            except TypeError:
                hits = client.search_messages(query, max_results=page_size)
            if isinstance(hits, dict):
                found.extend(str(item.get("id") or "") for item in hits.get("messages") or [] if item.get("id"))
                token = hits.get("nextPageToken")
                if not token:
                    break
            else:
                found.extend(str(item.get("id") or "") for item in hits or [] if item.get("id"))
                break
        return [mid for mid in found if mid]
    access = str(getattr(client, "access_token", "") or "")
    if not access:
        raise GmailAuthError("missing access token for plus recovery search")
    token = None
    for _ in range(RECOVERY_MAX_PAGES):
        params: list[tuple[str, str]] = [("q", query), ("maxResults", str(max(1, min(int(page_size), 100))))]
        for lid in label_ids or []:
            if lid:
                params.append(("labelIds", str(lid)))
        if token:
            params.append(("pageToken", token))
        page = _get_json("https://gmail.googleapis.com/gmail/v1/users/me/messages?" + urlencode(params), access)
        found.extend(str(item.get("id") or "") for item in page.get("messages") or [] if item.get("id"))
        token = page.get("nextPageToken")
        if not token:
            break
    return [mid for mid in found if mid]


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


def classify_plus_metadata(
    layer: Any,
    client: Any,
    gmail_message_id: str,
    *,
    event: str = "classify",
    resolved: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Revalidate the private subset from metadata only. Never fetches raw/body."""
    mid = str(gmail_message_id or "").strip()
    if not mid:
        return {"ok": False, "reason": "plus_gmail_message_missing", "gmail_message_id": mid}
    if is_stale_forbidden(mid):
        record_seen(layer, mid, event=event, status=STATUS_SKIPPED, reason=REASON_STALE_FORBIDDEN)
        update_seen(layer, mid, status=STATUS_SKIPPED, reason=REASON_STALE_FORBIDDEN, event=event)
        return {"ok": False, "reason": REASON_STALE_FORBIDDEN, "gmail_message_id": mid, "status": STATUS_SKIPPED}
    existing = get_seen(layer, mid)
    if existing and existing.get("status") in {STATUS_PROCESSED, STATUS_SKIPPED}:
        return {"ok": False, "reason": str(existing.get("reason") or existing.get("status")), "gmail_message_id": mid, "status": existing.get("status")}
    if existing and existing.get("status") == STATUS_PROCESSING and not lease_expired(existing):
        return {"ok": False, "reason": "already_claimed", "gmail_message_id": mid, "status": STATUS_PROCESSING}
    if existing is None:
        record_seen(layer, mid, event=event, status="discovered", reason=event)
    try:
        meta = _get_metadata(client, mid)
    except Exception as exc:
        return {
            "ok": False,
            "reason": "metadata_unavailable",
            "error": type(exc).__name__,
            "gmail_message_id": mid,
            "status": (existing or {}).get("status") or "discovered",
        }
    if str(meta.get("id") or "") and str(meta.get("id") or "") != mid:
        update_seen(layer, mid, status=STATUS_SKIPPED, reason="plus_fetched_id_mismatch", event=event)
        return {"ok": False, "reason": "plus_fetched_id_mismatch", "gmail_message_id": mid, "status": STATUS_SKIPPED}
    resolved = resolved or {}
    verdict = prefilter_plus_candidate(
        meta,
        control_match=resolved.get("control_match"),
        results_match=resolved.get("results_match"),
    )
    if not verdict.get("ok"):
        reason = str(verdict.get("reason") or "skipped")
        if reason == REASON_NOT_CONTROL_LABEL:
            update_seen(layer, mid, status=STATUS_AWAITING_LABEL, reason=reason, event=event)
            return {"ok": False, "reason": reason, "gmail_message_id": mid, "status": STATUS_AWAITING_LABEL, "awaiting_label": True}
        update_seen(layer, mid, status=STATUS_SKIPPED, reason=reason, event=event)
        return {"ok": False, "reason": reason, "gmail_message_id": mid, "status": STATUS_SKIPPED}
    update_seen(layer, mid, status=STATUS_PENDING, reason=None, event=event)
    return {"ok": True, "gmail_message_id": mid, "status": STATUS_PENDING, "labels": verdict.get("labels")}


def discover_plus_controls(layer: Any, *, client: Any | None = None) -> dict[str, Any]:
    """One READ-ONLY poll. Checkpoints every event before advancing the cursor."""
    ensure_plus_tables(layer)
    access = diagnose_daniel_sent_access()
    report: dict[str, Any] = {
        "ok": False,
        "contactus_traffic": False,
        "stale_forbidden": STALE_PLUS_CONTROL_ID,
        "candidates": [],
        "skipped": [],
        "awaiting_label": [],
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
        resolved = resolve_plus_labels(gmail)
        report["labels"] = {
            "ok": bool(resolved.get("ok")),
            "reason": resolved.get("reason"),
            "control_id": resolved.get("control_id"),
            "results_id": resolved.get("results_id"),
        }
        cursor = get_plus_cursor(layer)
        events: list[dict[str, str]] = []
        expired = False
        history_id = profile_hid
        if cursor and cursor.get("history_id"):
            try:
                history = fetch_plus_history(gmail, str(cursor["history_id"]))
                events.extend(
                    extract_plus_history_ids(
                        history,
                        control_labels=resolved.get("control_match") or CONTROL_LABELS,
                    )
                )
                if history.get("historyId"):
                    history_id = str(history["historyId"])
                checkpoint_history_events(
                    layer,
                    events,
                    history_id=history_id or str(cursor["history_id"]),
                    profile_history_id=profile_hid,
                )
            except PlusHistoryExpired:
                expired = True
                report["history_expired"] = True
        else:
            expired = True
            report["initialized_cursor"] = True
            if profile_hid:
                checkpoint_history_events(layer, [], history_id=profile_hid, profile_history_id=profile_hid)
        if expired:
            query = plus_recovery_query()
            report["reconcile_query"] = query
            if "label:" in query or "Label_" in query:
                raise RuntimeError("plus recovery query must not contain opaque label IDs")
            label_ids = [str(resolved.get("control_id") or "")] if resolved.get("ok") and resolved.get("control_id") else []
            report["reconcile_label_ids"] = label_ids
            recovered: list[dict[str, str]] = []
            for mid in _list_message_ids(gmail, query, label_ids=label_ids or None):
                recovered.append({"id": mid, "threadId": "", "event": "reconcile"})
            if profile_hid:
                checkpoint_history_events(
                    layer,
                    recovered,
                    history_id=profile_hid,
                    profile_history_id=profile_hid,
                    reconciled=True,
                )
            else:
                for item in recovered:
                    if item.get("id"):
                        record_seen(layer, str(item["id"]), event="reconcile", status="discovered", reason="reconcile")
        accepted: list[str] = []
        skipped: list[dict[str, str]] = []
        awaiting: list[str] = []
        to_classify = list(dict.fromkeys(unclassified_seen_ids(layer) + [str(item.get("id") or "") for item in events if item.get("id")]))
        for mid in to_classify:
            if not mid:
                continue
            verdict = classify_plus_metadata(layer, gmail, mid, event="discover", resolved=resolved)
            if verdict.get("ok"):
                accepted.append(mid)
            elif verdict.get("awaiting_label"):
                awaiting.append(mid)
            elif verdict.get("status") == STATUS_SKIPPED:
                skipped.append({"id": mid, "reason": str(verdict.get("reason") or "skipped")})
        report.update(
            {
                "ok": True,
                "candidates": accepted,
                "skipped": skipped,
                "awaiting_label": awaiting,
                "cursor": get_plus_cursor(layer),
                "profile_history_id": profile_hid,
            }
        )
        return report
    except (GmailAuthError, OSError, ValueError) as exc:
        report["reason"] = "plus_discovery_error"
        report["error"] = type(exc).__name__
        return report
