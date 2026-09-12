"""Read-only plus-control preflight. Does not change filters, labels, or scopes."""

from __future__ import annotations

from typing import Any

from .constants import (
    ALLOWED_SENDER,
    GMAIL_READONLY_SCOPE,
    LEAD_DESK_CONTROL_LABEL,
    LEAD_DESK_CONTROL_LABEL_ID,
    LEAD_DESK_PLUS_MAILBOX,
    LEAD_DESK_PLUS_RESULTS_MAILBOX,
    LEAD_DESK_RESULTS_LABEL,
    LEAD_DESK_RESULTS_LABEL_ID,
    MAILBOX,
    PLUS_DISCOVERY_CURSOR_KEY,
    STALE_PLUS_CONTROL_ID,
)
from .desk_plus_discover import plus_history_query
from .desk_plus_proof import _plus_gmail_client, _profile_email_from_client
from .desk_plus_result_send import plus_result_channel_ready
from .desk_sent_proof import diagnose_daniel_sent_access
from .eligibility import normalize_email
from .gates import daniel_sent_token_path, plus_result_send_token_path, send_token_path, token_path
from .gmail_readonly import GmailAuthError
from .oauth_consent import _get_json


_TEST_LABELS: list[dict[str, str]] | str | None = None
_TEST_FILTERS: Any = None
_TEST_PROFILE: dict[str, Any] | None = None


def set_test_plus_preflight(
    *,
    labels: list[dict[str, str]] | str | None = None,
    filters: Any = None,
    profile: dict[str, Any] | None = None,
) -> None:
    global _TEST_LABELS, _TEST_FILTERS, _TEST_PROFILE
    _TEST_LABELS = labels
    _TEST_FILTERS = filters
    _TEST_PROFILE = profile


def _list_labels(client: Any) -> dict[str, Any]:
    if _TEST_LABELS is not None:
        if _TEST_LABELS == "fail":
            return {"ok": False, "reason": "plus_label_lookup_failed", "labels": []}
        return {"ok": True, "labels": list(_TEST_LABELS), "via": "test_fixture"}
    if hasattr(client, "list_labels"):
        return {"ok": True, "labels": list(client.list_labels() or []), "via": "client"}
    token = str(getattr(client, "access_token", "") or "")
    if not token:
        return {"ok": False, "reason": "missing_access_token", "labels": []}
    page = _get_json("https://gmail.googleapis.com/gmail/v1/users/me/labels", token)
    return {"ok": True, "labels": list(page.get("labels") or []), "via": "gmail.readonly"}


def _list_filters(client: Any) -> dict[str, Any]:
    """Best-effort. gmail.readonly cannot read settings; do not request a new scope."""
    if _TEST_FILTERS is not None:
        if _TEST_FILTERS == "forbidden":
            return {
                "ok": False,
                "accessible": False,
                "reason": "gmail_settings_not_in_readonly_scope",
                "filters": [],
                "note": "Existing gmail.readonly cannot list filters. No mail-settings scope is requested.",
            }
        return {"ok": True, "accessible": True, "filters": list(_TEST_FILTERS), "via": "test_fixture"}
    if hasattr(client, "list_filters"):
        try:
            return {"ok": True, "accessible": True, "filters": list(client.list_filters() or []), "via": "client"}
        except Exception as exc:
            return {
                "ok": False,
                "accessible": False,
                "reason": "gmail_settings_not_in_readonly_scope",
                "error": type(exc).__name__,
                "filters": [],
            }
    token = str(getattr(client, "access_token", "") or "")
    if not token:
        return {"ok": False, "accessible": False, "reason": "missing_access_token", "filters": []}
    try:
        page = _get_json("https://gmail.googleapis.com/gmail/v1/users/me/settings/filters", token)
        return {"ok": True, "accessible": True, "filters": list(page.get("filter") or page.get("filters") or [])}
    except Exception:
        return {
            "ok": False,
            "accessible": False,
            "reason": "gmail_settings_not_in_readonly_scope",
            "filters": [],
            "note": (
                "Filter configuration is not readable with the existing Daniel "
                "gmail.readonly token. Do not add gmail.settings.basic. Daniel's "
                "manually created filters were not changed."
            ),
        }


def plus_control_preflight(*, client: Any | None = None) -> dict[str, Any]:
    """Report actual account, labels, discovery, and sender readiness. No mutations."""
    blockers: list[str] = []
    access = diagnose_daniel_sent_access()
    account = {
        "required": ALLOWED_SENDER,
        "token_path": str(daniel_sent_token_path()),
        "token_present": bool(access.get("token_present")),
        "scope_required": GMAIL_READONLY_SCOPE,
        "live_profile": None,
        "live_profile_verified": False,
    }
    labels_report: dict[str, Any] = {"ok": False, "labels": []}
    filters_report = {
        "ok": False,
        "accessible": False,
        "reason": "not_attempted",
        "filters": [],
        "unchanged": True,
        "note": "Preflight does not create or edit Daniel's filters, routing, labels, or permissions.",
    }
    gmail = client
    if access.get("available") or client is not None or _TEST_PROFILE is not None:
        try:
            if _TEST_PROFILE is not None:
                profile_email = normalize_email(str(_TEST_PROFILE.get("emailAddress") or ""))
                profile = dict(_TEST_PROFILE)
                gmail = client
            else:
                gmail = client or _plus_gmail_client()
                profile_email = _profile_email_from_client(gmail)
                profile = {"emailAddress": profile_email}
            account["live_profile"] = profile_email
            account["live_profile_verified"] = profile_email == ALLOWED_SENDER
            if profile_email != ALLOWED_SENDER:
                blockers.append("live_profile_not_daniel")
            labels_report = _list_labels(gmail)
            filters_report.update(_list_filters(gmail))
            filters_report["unchanged"] = True
            account["profile_history_id"] = str(profile.get("historyId") or "") or None
        except (GmailAuthError, OSError, ValueError) as exc:
            blockers.append("daniel_readonly_unusable")
            account["error"] = type(exc).__name__
    else:
        blockers.append("daniel_readonly_unavailable")

    present_labels = {str(item.get("id") or ""): str(item.get("name") or "") for item in labels_report.get("labels") or []}
    names = set(present_labels.values())
    ids = set(present_labels)
    control_ok = LEAD_DESK_CONTROL_LABEL in names
    results_ok = LEAD_DESK_RESULTS_LABEL in names
    if not labels_report.get("ok"):
        blockers.append("plus_label_lookup_failed")
        control_ok = False
        results_ok = False
    else:
        if not control_ok:
            blockers.append("control_label_missing")
        if not results_ok:
            blockers.append("results_label_missing")
    required_labels = {
        "control": {
            "name": LEAD_DESK_CONTROL_LABEL,
            "id": next((lid for lid, name in present_labels.items() if name == LEAD_DESK_CONTROL_LABEL), LEAD_DESK_CONTROL_LABEL_ID),
            "present": control_ok,
        },
        "results": {
            "name": LEAD_DESK_RESULTS_LABEL,
            "id": next((lid for lid, name in present_labels.items() if name == LEAD_DESK_RESULTS_LABEL), LEAD_DESK_RESULTS_LABEL_ID),
            "present": results_ok,
            "note": "Excluded from discovery. Do not recreate.",
        },
    }

    sender = plus_result_channel_ready()
    if not sender.get("ready"):
        blockers.append(str(sender.get("blocker") or "plus_result_send_not_ready"))

    discovery_ready = bool(account.get("live_profile_verified")) and control_ok and results_ok and labels_report.get("ok") and access.get("available", True)
    if _TEST_PROFILE is not None and account.get("live_profile_verified") and control_ok and results_ok and labels_report.get("ok"):
        discovery_ready = True
    if not discovery_ready and "daniel_readonly_unavailable" not in blockers and "control_label_missing" not in blockers and "results_label_missing" not in blockers and "plus_label_lookup_failed" not in blockers and "live_profile_not_daniel" not in blockers:
        if not account.get("live_profile_verified"):
            blockers.append("discovery_not_ready")

    status = "READY" if not blockers else "BLOCKED"
    return {
        "status": status,
        "activation": "held" if blockers else "ready_for_project_lead",
        "account": account,
        "required_labels": required_labels,
        "filters": filters_report,
        "discovery": {
            "ready": discovery_ready and "daniel_readonly_unavailable" not in blockers and "live_profile_not_daniel" not in blockers and "control_label_missing" not in blockers and "results_label_missing" not in blockers and "plus_label_lookup_failed" not in blockers,
            "cursor_key": PLUS_DISCOVERY_CURSOR_KEY,
            "isolated_from_contactus": True,
            "contactus_mailbox": MAILBOX,
            "query": plus_history_query(),
            "history_types": ["messageAdded", "labelAdded"],
            "stale_excluded": STALE_PLUS_CONTROL_ID,
            "control_mailbox": LEAD_DESK_PLUS_MAILBOX,
            "results_mailbox": LEAD_DESK_PLUS_RESULTS_MAILBOX,
            "inbox_not_required": True,
            "pubsub": False,
            "readonly_scope_only": True,
        },
        "sender": sender,
        "permissions": {
            "readonly_token": str(daniel_sent_token_path()),
            "plus_result_send_token": str(plus_result_send_token_path()),
            "contactus_readonly_unused": str(token_path()),
            "contactus_send_unused": str(send_token_path()),
            "mail_settings_scope_requested": False,
            "filters_or_labels_changed": False,
            "credentials_created": False,
        },
        "activation_blockers": blockers,
        "exactly_once_delivery": False,
        "residual_uncertainty": sender.get("residual_uncertainty")
        or "Result send is not activated until a separate daniel@ send-only token is configured.",
        "do_not": [
            "Do not process or timestamp-adjust 1a0979e37a0b0a94",
            "Do not send live mail from preflight",
            "Do not recreate Daniel's filters, labels, or routing",
            "Do not widen the readonly token",
            "Do not fall back to contactus credentials",
        ],
    }
