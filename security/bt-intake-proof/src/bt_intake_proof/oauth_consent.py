"""Build a Gmail read-only Desktop OAuth URL. Never requests send/modify/draft."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

from .constants import FORBIDDEN_GMAIL_SCOPES, GMAIL_READONLY_SCOPE, MAILBOX
from .gates import is_usable_project_id, oauth_client_path, project_id


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
