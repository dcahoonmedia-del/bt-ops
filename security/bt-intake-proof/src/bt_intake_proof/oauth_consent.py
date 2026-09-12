"""Build a Gmail read-only Desktop OAuth URL. Never requests send/modify/draft."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from urllib.parse import urlencode

from .constants import FORBIDDEN_GMAIL_SCOPES, GMAIL_READONLY_SCOPE, MAILBOX
from .eligibility import normalize_email
from .gates import is_usable_project_id, oauth_client_path, project_id, token_path


class OAuthClientError(RuntimeError):
    pass


def load_desktop_client(path=None) -> dict[str, Any]:
    client_file = path or oauth_client_path()
    if not client_file.exists():
        raise OAuthClientError(f"Desktop OAuth client JSON is not present at {client_file}")
    try:
        data = json.loads(client_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OAuthClientError("OAuth client file is not valid JSON") from exc
    if not isinstance(data, dict):
        raise OAuthClientError("OAuth client file must be a JSON object")
    if "web" in data and "installed" not in data:
        raise OAuthClientError("This is a Web client. Create a Desktop app client instead.")
    installed = data.get("installed")
    if not isinstance(installed, dict):
        raise OAuthClientError("Desktop client JSON must contain an 'installed' object")
    client_id = str(installed.get("client_id") or "").strip()
    if not client_id:
        raise OAuthClientError("Desktop client JSON is missing client_id")
    client_project = str(installed.get("project_id") or "").strip()
    expected = project_id()
    if expected and client_project and client_project != expected:
        raise OAuthClientError(
            f"OAuth client belongs to project {client_project}, not authorized project {expected}"
        )
    if client_project and not is_usable_project_id(client_project):
        raise OAuthClientError("OAuth client project_id is not a usable GCP project ID")
    return installed


def redirect_uri(installed: dict[str, Any]) -> str:
    uris = [str(item) for item in (installed.get("redirect_uris") or []) if item]
    for preferred in ("http://127.0.0.1/", "http://127.0.0.1", "http://localhost/", "http://localhost"):
        if preferred in uris:
            return preferred.rstrip("/") if preferred.endswith("/") and preferred.count("/") > 2 else preferred
    for uri in uris:
        if uri.startswith("http://127.0.0.1") or uri.startswith("http://localhost"):
            return uri
    return "http://localhost"


def authorization_url(installed: dict[str, Any] | None = None) -> dict[str, Any]:
    client = installed or load_desktop_client()
    scope = GMAIL_READONLY_SCOPE
    if scope in FORBIDDEN_GMAIL_SCOPES:
        raise OAuthClientError("internal scope configuration is unsafe")
    redirect = redirect_uri(client)
    params = {
        "client_id": client["client_id"],
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "false",
        "login_hint": MAILBOX,
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    write_markers = ("gmail.modify", "gmail.send", "gmail.compose", "gmail.insert", "mail.google.com/")
    if any(marker in url for marker in write_markers):
        raise OAuthClientError("refusing to build an OAuth URL that mentions write scopes")
    return {
        "status": "READY_FOR_CONTACTUS_CONSENT",
        "authorization_url": url,
        "mailbox_required": MAILBOX,
        "scope": scope,
        "redirect_uri": redirect,
        "project_id": project_id() or client.get("project_id"),
        "forbidden_scopes_requested": False,
        "instructions": [
            f"Open the authorization URL while signed out of daniel@ if needed.",
            f"Sign in as {MAILBOX} only.",
            "Approve Gmail read-only only. Decline if Google shows send, modify, or draft.",
            "After approve, the browser will try to open localhost and fail. Copy the full address-bar URL and send it back.",
        ],
    }


def extract_auth_code(redirect_or_code: str) -> str:
    text = (redirect_or_code or "").strip()
    if not text:
        raise OAuthClientError("empty authorization response")
    if text.startswith("http://") or text.startswith("https://"):
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(text)
        query = parse_qs(parsed.query)
        if parsed.fragment:
            query.update(parse_qs(parsed.fragment))
        if query.get("error"):
            raise OAuthClientError(f"Google returned error: {query['error']}")
        codes = query.get("code") or []
        if not codes:
            raise OAuthClientError("redirect URL does not contain a code parameter")
        return codes[0]
    return text


def _post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OAuthClientError(f"token endpoint HTTP {exc.code}: {detail}") from exc


def _get_json(url: str, access_token: str | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET")
    if access_token:
        request.add_header("Authorization", f"Bearer {access_token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OAuthClientError(f"HTTP {exc.code} from {url}: {detail}") from exc


def exchange_code(redirect_or_code: str) -> dict[str, Any]:
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
    forbidden = [scope for scope in scopes if scope in FORBIDDEN_GMAIL_SCOPES]
    if forbidden:
        raise OAuthClientError(f"token includes forbidden Gmail scopes: {forbidden}")
    if GMAIL_READONLY_SCOPE not in scopes:
        raise OAuthClientError("token does not include gmail.readonly")
    access = str(token.get("access_token") or "")
    if not access:
        raise OAuthClientError("token response missing access_token")
    profile = _get_json("https://gmail.googleapis.com/gmail/v1/users/me/profile", access)
    email = normalize_email(str(profile.get("emailAddress") or ""))
    if email != MAILBOX:
        raise OAuthClientError(f"authenticated mailbox is {email or '(unknown)'}, expected {MAILBOX}")
    record = {
        "token_uri": client.get("token_uri") or "https://oauth2.googleapis.com/token",
        "client_id": client["client_id"],
        "client_secret": client.get("client_secret"),
        "refresh_token": token.get("refresh_token"),
        "access_token": access,
        "token_type": token.get("token_type") or "Bearer",
        "scopes": scopes,
        "scope": GMAIL_READONLY_SCOPE,
        "email": email,
        "account": email,
    }
    dest = token_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    dest.chmod(0o600)
    return {
        "status": "PASS",
        "email": email,
        "scopes": scopes,
        "readonly_only": scopes == [GMAIL_READONLY_SCOPE] or (
            GMAIL_READONLY_SCOPE in scopes and not forbidden
        ),
        "refresh_token_present": bool(token.get("refresh_token")),
        "token_path": str(dest),
        "history_id": str(profile.get("historyId") or "") or None,
        "messages_total": profile.get("messagesTotal"),
    }


def blocked_oauth_url() -> dict[str, Any]:
    return {
        "status": "BLOCKED",
        "authorization_url": None,
        "mailbox_required": MAILBOX,
        "scope": GMAIL_READONLY_SCOPE,
        "project_id": project_id() or None,
        "reason": (
            "Desktop OAuth client JSON is not in this environment yet. "
            "Create the Desktop client in project bt-intake-proof and send the downloaded JSON."
        ),
    }
