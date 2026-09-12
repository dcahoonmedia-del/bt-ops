"""Dedicated contactus@ send transport. Never uses the intake readonly token."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any

from .bounded_send import MissingContactusSendTransport, raw_b64
from .constants import MAILBOX
from .eligibility import normalize_email
from .gates import send_token_path, token_path
from .gmail_readonly import GmailAuthError
from .oauth_consent import OAuthClientError, _get_json, _post_form, load_desktop_client
from .phasee_constants import PHASEE_FROM, PHASEE_TO

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


def assert_send_credentials(scopes: list[str], email: str, path) -> None:
    email_n = normalize_email(email)
    if email_n != MAILBOX:
        raise GmailAuthError(f"send token mailbox is {email_n or '(unknown)'}, expected {MAILBOX}")
    if GMAIL_SEND_SCOPE not in scopes:
        raise GmailAuthError("contactus send token must include gmail.send")
    if path.resolve() == token_path().resolve():
        raise GmailAuthError("refusing to use the intake readonly token for send")


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
        profile = _get_json("https://gmail.googleapis.com/gmail/v1/users/me/profile", access_token)
        if normalize_email(str(profile.get("emailAddress") or "")) != MAILBOX:
            raise GmailAuthError("send token is not signed in as contactus@")
        self.access_token = access_token
        self.email = MAILBOX
        self.scopes = list(scopes)

    def send_exact(self, binding: dict[str, Any]) -> dict[str, Any]:
        if binding.get("from_addr") != PHASEE_FROM or binding.get("to_addr") != PHASEE_TO:
            return {"ok": False, "unknown": False, "reason": "payload_not_phasee"}
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
