"""Tightly restricted daniel@ → daniel+lead-desk-results@ sender.

Never uses the Daniel readonly token, contactus send token, or contactus@.
Missing configuration is an activation blocker, not a silent fallback.
Gmail cannot guarantee exactly-once delivery; uncertain outcomes are
reconciled against provider records before any retry.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

from .bounded_send import raw_b64
from .constants import (
    ALLOWED_SENDER,
    FORBIDDEN_GMAIL_SCOPES,
    GMAIL_READONLY_SCOPE,
    LEAD_DESK_PLUS_MAILBOX,
    LEAD_DESK_PLUS_RESULTS_MAILBOX,
    MAILBOX,
    MARKER_DESK_CTRL,
    MARKER_PLUS_RESULT,
)
from .eligibility import normalize_email
from .gates import daniel_sent_token_path, plus_result_send_token_path, send_token_path, token_path
from .gmail_readonly import GmailAuthError
from .oauth_consent import OAuthClientError
from .desk_plus_store import ensure_plus_tables
from .store import utc_now


GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
SEND_TOKEN_ALLOWED_SCOPES = {
    GMAIL_SEND_SCOPE,
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
}
KIND_PLUS_COMBINED = "plus_combined"
REASON_CHANNEL_NOT_READY = "plus_result_channel_not_ready"

_TEST_READY: bool | None = None
_TEST_TRANSPORT: Any = None


def set_test_plus_result_ready(enabled: bool | None) -> None:
    """Test injection only. Production never sets this."""
    global _TEST_READY
    _TEST_READY = enabled


def set_test_plus_result_transport(transport: Any | None) -> None:
    """Test injection only. Replaces the live plus-result sender."""
    global _TEST_TRANSPORT
    _TEST_TRANSPORT = transport


def extra_gmail_scopes(scopes: list[str]) -> list[str]:
    extra = []
    for scope in scopes:
        if not scope:
            continue
        if scope in SEND_TOKEN_ALLOWED_SCOPES:
            continue
        extra.append(scope)
    return extra


def _token_scopes(record: dict[str, Any]) -> list[str]:
    scopes = record.get("scopes") or record.get("scope") or []
    if isinstance(scopes, str):
        return [item for item in scopes.replace(",", " ").split() if item]
    if isinstance(scopes, list):
        return [str(item) for item in scopes]
    return []


def _same_path(left, right) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return str(left) == str(right)


def assert_plus_result_credentials(scopes: list[str], email: str, path) -> None:
    email_n = normalize_email(email)
    if email_n != ALLOWED_SENDER:
        raise GmailAuthError(f"plus-result send token mailbox is {email_n or '(unknown)'}, expected {ALLOWED_SENDER}")
    if email_n == MAILBOX:
        raise GmailAuthError("plus-result sender must not be contactus@")
    if GMAIL_SEND_SCOPE not in scopes:
        raise GmailAuthError("plus-result send token must include gmail.send")
    extras = extra_gmail_scopes(scopes)
    if extras:
        raise GmailAuthError(f"plus-result send token must be send-only; extra scopes: {extras}")
    if GMAIL_READONLY_SCOPE in scopes:
        raise GmailAuthError("plus-result send token must not include gmail.readonly")
    forbidden = [scope for scope in scopes if scope in FORBIDDEN_GMAIL_SCOPES and scope != GMAIL_SEND_SCOPE]
    if forbidden:
        raise GmailAuthError(f"plus-result send token includes forbidden scopes: {forbidden}")
    if _same_path(path, daniel_sent_token_path()):
        raise GmailAuthError("refusing to use the Daniel readonly token for plus-result send")
    if _same_path(path, token_path()):
        raise GmailAuthError("refusing to use the contactus readonly token for plus-result send")
    if _same_path(path, send_token_path()):
        raise GmailAuthError("refusing to use the contactus send token for plus-result send")


def plus_result_channel_ready() -> dict[str, Any]:
    """Readiness for result intent + send. Missing sender does not consume a decision."""
    if _TEST_READY is True or _TEST_TRANSPORT is not None:
        return {
            "ready": True,
            "status": "READY",
            "via": "test_fixture",
            "from": ALLOWED_SENDER,
            "to": LEAD_DESK_PLUS_RESULTS_MAILBOX,
            "exactly_once": False,
        }
    if _TEST_READY is False:
        return {
            "ready": False,
            "status": "BLOCKED",
            "reason": REASON_CHANNEL_NOT_READY,
            "blocker": "test_plus_result_channel_disabled",
        }
    dest = plus_result_send_token_path()
    payload: dict[str, Any] = {
        "ready": False,
        "status": "BLOCKED",
        "reason": REASON_CHANNEL_NOT_READY,
        "token_path": str(dest),
        "from": ALLOWED_SENDER,
        "to": LEAD_DESK_PLUS_RESULTS_MAILBOX,
        "widens_readonly": False,
        "uses_contactus_credentials": False,
        "exactly_once": False,
    }
    if not dest.exists():
        payload["blocker"] = "plus_result_send_token_missing"
        payload["note"] = (
            "Place an already-authorized daniel@ gmail.send-only token at this path "
            "or BT_DANIEL_PLUS_RESULT_SEND_TOKEN. Do not reuse the readonly token or "
            "contactus credentials. This assignment does not create or grant that token."
        )
        return payload
    try:
        record = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload["blocker"] = "plus_result_send_token_unreadable"
        return payload
    email = normalize_email(str(record.get("email") or record.get("account") or ""))
    scopes = _token_scopes(record)
    try:
        assert_plus_result_credentials(scopes, email, dest)
    except GmailAuthError as exc:
        payload["blocker"] = "plus_result_send_token_invalid"
        payload["detail"] = str(exc)
        return payload
    return {
        **payload,
        "ready": True,
        "status": "READY",
        "blocker": None,
        "token_email": email,
        "token_scopes": scopes,
        "residual_uncertainty": (
            "Gmail users.messages.send is at-least-once from the client view. "
            "Unknown/timeout outcomes are reconciled against SENT before retry. "
            "This path does not claim exactly-once delivery."
        ),
    }


def format_plus_combined_result(
    result: dict[str, Any],
    *,
    binding: dict[str, Any] | None = None,
    draft_text: str = "",
) -> dict[str, str]:
    from .desk_bridge import format_binding_block

    version = result.get("draft_version")
    if version is None and binding:
        version = binding.get("draft_version")
    if result.get("ok"):
        human = f"Draft updated to v{version}. Nothing sent."
    else:
        human = str(result.get("human") or "Nothing was saved. Nothing sent.")
    lines = [
        "B&T Lead Desk private result (internal). Tell Daniel this in plain language.",
        "Do not read machine fields to him.",
        "Sending the control is not proof of a save. This result is the authoritative outcome.",
        "",
        MARKER_PLUS_RESULT,
        human,
        "",
        f"STATUS={'ok' if result.get('ok') else 'failed'}",
        f"INTENT={result.get('intent') or ''}",
        f"CASE={result.get('case_id') or ''}",
        f"DRAFT={version or ''}",
        f"REASON={result.get('reason') or ''}",
        f"CONTROL_ID={result.get('control_gmail_id') or ''}",
        f"NONCE={result.get('nonce') or ''}",
        f"EXECUTE_SEND=no",
        f"CUSTOMER_SEND=no",
        f"CONTACTUS_TRAFFIC=no",
        f"SAVE={'yes' if result.get('ok') else 'no'}",
        f"RESULT_KIND={KIND_PLUS_COMBINED}",
        "",
        "--- Updated draft ---",
        str(draft_text or "(none)"),
    ]
    if binding:
        lines.extend(["", format_binding_block(binding)])
    body = "\n".join(lines) + "\n"
    if MARKER_DESK_CTRL in body.split("BT-INTAKE-PROOF-PLUS-RESULT-E9A8", 1)[-1] and MARKER_DESK_CTRL in draft_text:
        pass
    return {
        "from": ALLOWED_SENDER,
        "to": LEAD_DESK_PLUS_RESULTS_MAILBOX,
        "cc": "",
        "bcc": "",
        "subject": f"{MARKER_PLUS_RESULT} {result.get('intent') or 'action'} {result.get('case_id') or ''} v{version or ''}".strip(),
        "body": body,
        "kind": KIND_PLUS_COMBINED,
        "marker": MARKER_PLUS_RESULT,
    }


def persist_plus_result_intent(
    layer: Any,
    result: dict[str, Any],
    *,
    binding: dict[str, Any] | None = None,
    draft_text: str = "",
) -> dict[str, Any]:
    """One durable combined result. Safe to call inside the revise transaction."""
    ensure_plus_tables(layer)
    control_id = str(result.get("control_gmail_id") or "")
    if not control_id:
        raise ValueError("plus result intent requires control_gmail_id")
    mail = format_plus_combined_result(result, binding=binding, draft_text=draft_text)
    now = utc_now()
    layer.conn.execute(
        """
        INSERT OR IGNORE INTO plus_result_outbox
            (control_gmail_id, nonce, kind, subject, body, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?)
        """,
        (control_id, result.get("nonce"), KIND_PLUS_COMBINED, mail["subject"], mail["body"], now),
    )
    row = layer.conn.execute(
        "SELECT id, status FROM plus_result_outbox WHERE control_gmail_id = ? AND kind = ?",
        (control_id, KIND_PLUS_COMBINED),
    ).fetchone()
    if row is None:
        raise RuntimeError("plus result intent was not persisted")
    result["result_email"] = mail
    result["plus_result_outbox_id"] = row["id"]
    result["plus_result_status"] = row["status"]
    return {"ok": True, "outbox_id": row["id"], "status": row["status"], "mail": mail}


def plus_result_payload_allowed(mail: dict[str, Any]) -> dict[str, Any]:
    from_addr = normalize_email(mail.get("from") or mail.get("from_addr") or "")
    to_addr = normalize_email(mail.get("to") or mail.get("to_addr") or "")
    subject = str(mail.get("subject") or "")
    body = str(mail.get("body") or "")
    if from_addr != ALLOWED_SENDER:
        return {"ok": False, "reason": "plus_result_from_not_daniel"}
    if to_addr != LEAD_DESK_PLUS_RESULTS_MAILBOX:
        return {"ok": False, "reason": "plus_result_to_not_results_mailbox"}
    if to_addr == MAILBOX or to_addr == LEAD_DESK_PLUS_MAILBOX:
        return {"ok": False, "reason": "plus_result_contactus_or_control_forbidden"}
    if mail.get("cc") or mail.get("bcc"):
        return {"ok": False, "reason": "plus_result_cc_bcc_forbidden"}
    if MARKER_PLUS_RESULT not in subject or MARKER_PLUS_RESULT not in body:
        return {"ok": False, "reason": "plus_result_marker_missing"}
    if MARKER_DESK_CTRL in subject:
        return {"ok": False, "reason": "plus_result_must_not_be_control"}
    return {"ok": True}


class MissingPlusResultSendTransport:
    def send_plus_result(self, mail: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": False,
            "unknown": False,
            "blocked": True,
            "reason": REASON_CHANNEL_NOT_READY,
        }


class MemoryPlusResultTransport:
    def __init__(self, *, timeout: bool = False, fail: bool = False) -> None:
        self.sent: list[dict[str, Any]] = []
        self.timeout = timeout
        self.fail = fail
        self.send_count = 0

    def send_plus_result(self, mail: dict[str, Any]) -> dict[str, Any]:
        allowed = plus_result_payload_allowed(mail)
        if not allowed.get("ok"):
            return {"ok": False, "unknown": False, "reason": allowed.get("reason")}
        self.send_count += 1
        if self.timeout:
            return {"ok": False, "unknown": True, "reason": "timeout"}
        if self.fail:
            return {"ok": False, "unknown": False, "reason": "provider_failed"}
        mid = f"plus-res-{len(self.sent) + 1}"
        record = {**mail, "provider_message_id": mid}
        self.sent.append(record)
        return {"ok": True, "unknown": False, "provider_message_id": mid}


class HttpPlusResultGmail:
    """Submit only a backend-generated plus result. No Cc/Bcc, no contactus."""

    def __init__(self, access_token: str, email: str, scopes: list[str], path) -> None:
        assert_plus_result_credentials(scopes, email, path)
        self.access_token = access_token
        self.email = ALLOWED_SENDER
        self.scopes = list(scopes)

    def send_plus_result(self, mail: dict[str, Any]) -> dict[str, Any]:
        allowed = plus_result_payload_allowed(mail)
        if not allowed.get("ok"):
            return {"ok": False, "unknown": False, "reason": allowed.get("reason")}
        binding = {
            "from_addr": ALLOWED_SENDER,
            "to_addr": LEAD_DESK_PLUS_RESULTS_MAILBOX,
            "subject": mail["subject"],
            "body": mail["body"],
        }
        payload = {"raw": raw_b64(binding)}
        request = urllib.request.Request(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )
        request.add_header("Authorization", f"Bearer {self.access_token}")
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
        except TimeoutError:
            return {"ok": False, "unknown": True, "reason": "timeout"}
        except socket.timeout:
            return {"ok": False, "unknown": True, "reason": "timeout"}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code >= 500:
                return {"ok": False, "unknown": True, "reason": f"http_{exc.code}"}
            return {"ok": False, "unknown": False, "reason": f"http_{exc.code}", "detail": detail[:200]}
        except urllib.error.URLError as exc:
            return {"ok": False, "unknown": True, "reason": f"urlerror:{exc.reason}"}
        mid = str(body.get("id") or "")
        if not mid:
            return {"ok": False, "unknown": True, "reason": "missing_provider_message_id", "provider": body}
        return {
            "ok": True,
            "unknown": False,
            "provider_message_id": mid,
            "provider_thread_id": body.get("threadId"),
            "exactly_once": False,
        }


def refresh_plus_result_send_token() -> dict[str, Any]:
    from .oauth_consent import _post_form, load_desktop_client

    dest = plus_result_send_token_path()
    if not dest.exists():
        raise OAuthClientError("plus-result send token is not present")
    record = json.loads(dest.read_text(encoding="utf-8"))
    assert_plus_result_credentials(
        _token_scopes(record),
        str(record.get("email") or ""),
        dest,
    )
    refresh = str(record.get("refresh_token") or "")
    if not refresh:
        raise OAuthClientError("plus-result send token has no refresh_token")
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
    access = str(token.get("access_token") or "")
    if not access:
        raise OAuthClientError("plus-result send-token refresh missing access_token")
    record["access_token"] = access
    dest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    dest.chmod(0o600)
    return record


def configured_plus_result_transport():
    if _TEST_TRANSPORT is not None:
        return _TEST_TRANSPORT
    dest = plus_result_send_token_path()
    if not dest.exists():
        return MissingPlusResultSendTransport()
    try:
        record = refresh_plus_result_send_token()
        return HttpPlusResultGmail(
            str(record.get("access_token") or ""),
            str(record.get("email") or ALLOWED_SENDER),
            _token_scopes(record),
            dest,
        )
    except (OAuthClientError, GmailAuthError, OSError, json.JSONDecodeError):
        return MissingPlusResultSendTransport()


def deliver_plus_results(layer: Any, transport: Any | None = None) -> list[dict[str, Any]]:
    """Send pending plus results. Unknown stays unknown until provider reconcile."""
    ensure_plus_tables(layer)
    sender = transport or configured_plus_result_transport()
    rows = layer.conn.execute(
        "SELECT * FROM plus_result_outbox WHERE status = 'pending' ORDER BY id"
    ).fetchall()
    out = []
    send = getattr(sender, "send_plus_result", None)
    if send is None:
        return [{"ok": False, "reason": "plus_result_sender_missing"}]
    for row in rows:
        claimed = layer.conn.execute(
            "UPDATE plus_result_outbox SET status = 'sending' WHERE id = ? AND status = 'pending'",
            (row["id"],),
        )
        if claimed.rowcount != 1:
            continue
        result = send(
            {
                "from": ALLOWED_SENDER,
                "to": LEAD_DESK_PLUS_RESULTS_MAILBOX,
                "subject": row["subject"],
                "body": row["body"],
            }
        )
        if result.get("unknown"):
            layer.conn.execute(
                "UPDATE plus_result_outbox SET status = 'unknown', provider_id = ? WHERE id = ?",
                (result.get("provider_message_id"), row["id"]),
            )
            out.append({"ok": False, "unknown": True, "id": row["id"], "reason": result.get("reason"), "retried": False})
            continue
        if not result.get("ok"):
            layer.conn.execute(
                "UPDATE plus_result_outbox SET status = 'pending' WHERE id = ? AND status = 'sending'",
                (row["id"],),
            )
            if result.get("blocked"):
                layer.conn.execute(
                    "UPDATE plus_result_outbox SET status = 'blocked' WHERE id = ?",
                    (row["id"],),
                )
            out.append({"ok": False, "id": row["id"], "reason": result.get("reason"), "blocked": result.get("blocked")})
            continue
        layer.conn.execute(
            "UPDATE plus_result_outbox SET status = 'sent', provider_id = ?, sent_at = ? WHERE id = ?",
            (result.get("provider_message_id"), utc_now(), row["id"]),
        )
        out.append(
            {
                "ok": True,
                "id": row["id"],
                "kind": row["kind"],
                "control_gmail_id": row["control_gmail_id"],
                "provider_message_id": result.get("provider_message_id"),
                "exactly_once": False,
            }
        )
    return out


def reconcile_plus_result_outbox(layer: Any, sent_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reconcile sending/unknown rows against provider SENT before any retry."""
    ensure_plus_tables(layer)
    rows = layer.conn.execute(
        "SELECT * FROM plus_result_outbox WHERE status IN ('sending', 'unknown') ORDER BY id"
    ).fetchall()
    out = []
    for row in rows:
        matches = [
            item
            for item in sent_records
            if str(item.get("subject") or "") == row["subject"]
            and MARKER_PLUS_RESULT in str(item.get("body") or "")
            and str(row["control_gmail_id"] or "") in str(item.get("body") or "")
        ]
        if len(matches) == 1:
            mid = matches[0].get("provider_message_id") or matches[0].get("id")
            layer.conn.execute(
                "UPDATE plus_result_outbox SET status = 'sent', provider_id = ?, sent_at = ? WHERE id = ?",
                (mid, utc_now(), row["id"]),
            )
            out.append({"ok": True, "recovered": True, "id": row["id"], "provider_message_id": mid, "retried": False})
        elif len(matches) > 1:
            layer.conn.execute(
                "UPDATE plus_result_outbox SET status = 'unknown' WHERE id = ?",
                (row["id"],),
            )
            out.append({"ok": False, "unknown": True, "retried": False, "id": row["id"], "reason": "ambiguous_provider_match"})
        elif row["status"] == "sending":
            layer.conn.execute(
                "UPDATE plus_result_outbox SET status = 'pending' WHERE id = ? AND status = 'sending'",
                (row["id"],),
            )
            out.append({"ok": True, "unlocked": True, "id": row["id"], "reason": "sending_reset_to_pending"})
        else:
            out.append({"ok": False, "unknown": True, "retried": False, "id": row["id"], "reason": "still_unconfirmed"})
    return out
