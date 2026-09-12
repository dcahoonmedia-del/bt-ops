"""Dedicated contactus@ send transport. Never uses the intake readonly token."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

from .bounded_send import MissingContactusSendTransport, raw_b64
from .constants import DESK_PACKET_MARKERS, MAILBOX, MARKER_DESK_CTRL
from .eligibility import normalize_email
from .gates import project_id, send_token_path, token_path
from .gmail_readonly import GmailAuthError
from .oauth_consent import (
    OAuthClientError,
    _post_form,
    extract_auth_code,
    load_desktop_client,
    redirect_uri,
)
from .phasee_constants import PHASEE_FROM, PHASEE_TO
from .send_bind import LINK_RE, is_authorized_internal_send_body

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
SEND_TOKEN_ALLOWED_SCOPES = {
    GMAIL_SEND_SCOPE,
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
}


def send_authorization_url(installed: dict[str, Any] | None = None) -> dict[str, Any]:
    """Desktop URL for a separate contactus send-only token. Does not touch the readonly token."""
    client = installed or load_desktop_client()
    redirect = redirect_uri(client)
    params = {
        "client_id": client["client_id"],
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": GMAIL_SEND_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "false",
        "login_hint": MAILBOX,
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    if "gmail.readonly" in url or "gmail.modify" in url or "gmail.compose" in url or "mail.google.com" in url:
        raise OAuthClientError("send OAuth URL requested a non-send Gmail scope")
    if GMAIL_SEND_SCOPE.replace(":", "%3A").replace("/", "%2F") not in url and GMAIL_SEND_SCOPE not in url:
        raise OAuthClientError("send OAuth URL missing gmail.send")
    return {
        "status": "READY_FOR_CONTACTUS_SEND_CONSENT",
        "authorization_url": url,
        "mailbox_required": MAILBOX,
        "scope": GMAIL_SEND_SCOPE,
        "scopes_requested": [GMAIL_SEND_SCOPE],
        "token_file": str(send_token_path()),
        "readonly_token_file": str(token_path()),
        "widens_intake_readonly": False,
        "redirect_uri": redirect,
        "project_id": project_id() or client.get("project_id"),
        "instructions": [
            f"Sign in as {MAILBOX} only. Sign out of daniel@ first if the browser is on that account.",
            "Google should show Gmail send only. Decline if it also shows read, modify, compose, or full mail.",
            "This creates a separate send token. It will not replace the intake read-only token.",
            "After approve, the browser will try to open localhost and fail. Copy the full address-bar URL and send it back.",
            "Do not authorize until you have reviewed this URL and scope list.",
        ],
    }


def extra_gmail_scopes(scopes: list[str]) -> list[str]:
    extra = []
    for scope in scopes:
        if not scope:
            continue
        if scope in SEND_TOKEN_ALLOWED_SCOPES:
            continue
        extra.append(scope)
    return extra


def assert_send_credentials(scopes: list[str], email: str, path) -> None:
    email_n = normalize_email(email)
    if email_n != MAILBOX:
        raise GmailAuthError(f"send token mailbox is {email_n or '(unknown)'}, expected {MAILBOX}")
    if GMAIL_SEND_SCOPE not in scopes:
        raise GmailAuthError("contactus send token must include gmail.send")
    extras = extra_gmail_scopes(scopes)
    if extras:
        raise GmailAuthError(f"contactus send token must be send-only; extra scopes: {extras}")
    if path.resolve() == token_path().resolve():
        raise GmailAuthError("refusing to use the intake readonly token for send")


def lookup_token_email(access_token: str) -> str:
    request = urllib.request.Request(
        "https://oauth2.googleapis.com/tokeninfo",
        data=urlencode({"access_token": access_token}).encode("utf-8"),
        method="POST",
    )
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            info = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OAuthClientError(f"tokeninfo HTTP {exc.code}: {detail}") from exc
    return normalize_email(str(info.get("email") or ""))


def exchange_send_code(redirect_or_code: str) -> dict[str, Any]:
    dest = send_token_path()
    readonly = token_path()
    if dest.resolve() == readonly.resolve():
        raise OAuthClientError("refusing to write a send token over the intake readonly token")
    client = load_desktop_client()
    code = extract_auth_code(redirect_or_code)
    token = _post_form(
        str(client.get("token_uri") or "https://oauth2.googleapis.com/token"),
        {
            "code": code,
            "client_id": client["client_id"],
            "client_secret": str(client.get("client_secret") or ""),
            "redirect_uri": redirect_uri(client),
            "grant_type": "authorization_code",
        },
    )
    scopes = str(token.get("scope") or "").split()
    access = str(token.get("access_token") or "")
    if not access:
        raise OAuthClientError("send token response missing access_token")
    extras = extra_gmail_scopes(scopes)
    if GMAIL_SEND_SCOPE not in scopes:
        raise OAuthClientError("send token does not include gmail.send")
    if extras:
        raise OAuthClientError(f"send token must be send-only; extra scopes: {extras}")
    email = lookup_token_email(access)
    if email and email != MAILBOX:
        raise OAuthClientError(f"authenticated mailbox is {email}, expected {MAILBOX}")
    if not email:
        email = MAILBOX
        mailbox_via = "login_hint_and_later_sent_verify"
    else:
        mailbox_via = "tokeninfo"
    record = {
        "token_uri": client.get("token_uri") or "https://oauth2.googleapis.com/token",
        "client_id": client["client_id"],
        "client_secret": client.get("client_secret"),
        "refresh_token": token.get("refresh_token"),
        "access_token": access,
        "token_type": token.get("token_type") or "Bearer",
        "scopes": scopes,
        "scope": GMAIL_SEND_SCOPE,
        "email": email,
        "account": email,
        "purpose": "phasee_bounded_send_only",
        "mailbox_verified_via": mailbox_via,
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    dest.chmod(0o600)
    if readonly.exists() and dest.resolve() != readonly.resolve():
        ro = json.loads(readonly.read_text(encoding="utf-8"))
        if GMAIL_SEND_SCOPE in list(ro.get("scopes") or []):
            dest.unlink(missing_ok=True)
            raise OAuthClientError("intake readonly token unexpectedly contains gmail.send")
    return {
        "status": "PASS",
        "email": email,
        "scopes": scopes,
        "send_only": True,
        "mailbox_verified_via": mailbox_via,
        "refresh_token_present": bool(token.get("refresh_token")),
        "token_path": str(dest),
        "readonly_token_untouched": True,
        "gmail_profile_not_used": True,
    }


def refresh_send_token() -> dict[str, Any]:
    dest = send_token_path()
    if not dest.exists():
        raise OAuthClientError("contactus send token is not present")
    record = json.loads(dest.read_text(encoding="utf-8"))
    assert_send_credentials(
        list(record.get("scopes") or [record.get("scope") or ""]),
        str(record.get("email") or ""),
        dest,
    )
    refresh = str(record.get("refresh_token") or "")
    if not refresh:
        raise OAuthClientError("contactus send token has no refresh_token")
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
        raise OAuthClientError("send-token refresh missing access_token")
    scopes = str(token.get("scope") or " ".join(record.get("scopes") or [])).split()
    assert_send_credentials(scopes or list(record.get("scopes") or []), str(record.get("email") or MAILBOX), dest)
    record["access_token"] = access
    if scopes:
        record["scopes"] = scopes
    dest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    dest.chmod(0o600)
    return record


class HttpContactusSendGmail:
    """Submit only the stored Phase E MIME. Does not rewrite subject, body, or recipients."""

    def __init__(self, access_token: str, email: str, scopes: list[str], path) -> None:
        assert_send_credentials(scopes, email, path)
        self.access_token = access_token
        self.email = MAILBOX
        self.scopes = list(scopes)

    def _submit_raw(self, binding: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {"raw": raw_b64(binding)}
        if binding.get("thread_id"):
            payload["threadId"] = binding["thread_id"]
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
                return {"ok": False, "unknown": True, "reason": f"http_{exc.code}", "detail": detail}
            return {"ok": False, "unknown": False, "reason": f"http_{exc.code}", "detail": detail}
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
            "label_ids": body.get("labelIds") or [],
        }

    def send_exact(self, binding: dict[str, Any]) -> dict[str, Any]:
        if binding.get("from_addr") != PHASEE_FROM or binding.get("to_addr") != PHASEE_TO:
            return {"ok": False, "unknown": False, "reason": "payload_not_phasee"}
        if not is_authorized_internal_send_body(binding.get("body")):
            return {"ok": False, "unknown": False, "reason": "payload_not_phasee"}
        return self._submit_raw(binding)

    def send_internal_desk(self, mail: dict[str, Any]) -> dict[str, Any]:
        """contactus → daniel desk packets only. Never a DESK-CTRL and never customer mail."""
        from_addr = mail.get("from_addr") or mail.get("from") or PHASEE_FROM
        to_addr = mail.get("to_addr") or mail.get("to") or ""
        subject = str(mail.get("subject") or "")
        body = str(mail.get("body") or "")
        blob = f"{subject}\n{body}"
        if normalize_email(from_addr) != PHASEE_FROM or normalize_email(to_addr) != PHASEE_TO:
            return {"ok": False, "unknown": False, "reason": "desk_packet_not_internal"}
        if MARKER_DESK_CTRL in blob:
            return {"ok": False, "unknown": False, "reason": "desk_ctrl_loop_forbidden"}
        if not any(marker in blob for marker in DESK_PACKET_MARKERS):
            return {"ok": False, "unknown": False, "reason": "not_desk_packet"}
        if LINK_RE.search(body):
            return {"ok": False, "unknown": False, "reason": "links_present"}
        if mail.get("cc") or mail.get("bcc") or mail.get("attachments"):
            return {"ok": False, "unknown": False, "reason": "desk_packet_extras"}
        return self._submit_raw(
            {
                "from_addr": PHASEE_FROM,
                "to_addr": PHASEE_TO,
                "subject": subject,
                "body": body,
                "thread_id": mail.get("thread_id") or "",
            }
        )


def configured_send_transport():
    dest = send_token_path()
    if not dest.exists():
        return MissingContactusSendTransport()
    try:
        record = refresh_send_token()
        return HttpContactusSendGmail(
            str(record.get("access_token") or ""),
            str(record.get("email") or MAILBOX),
            list(record.get("scopes") or []),
            dest,
        )
    except (OAuthClientError, GmailAuthError, OSError, json.JSONDecodeError):
        return MissingContactusSendTransport()
