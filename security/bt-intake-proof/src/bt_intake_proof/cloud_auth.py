"""Project-owner Cloud OAuth for one service account + impersonation. No Gmail scopes. No JSON key."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

from .constants import (
    ALLOWED_SENDER,
    CLOUD_OWNER_HINT,
    CLOUD_PLATFORM_SCOPE,
    FORBIDDEN_GMAIL_SCOPES,
    GMAIL_READONLY_SCOPE,
)
from .eligibility import normalize_email
from .gates import cloud_token_path, project_id
from .oauth_consent import (
    OAuthClientError,
    _get_json,
    _post_form,
    extract_auth_code,
    load_desktop_client,
    redirect_uri,
)


def impersonation_possible_without_key() -> dict[str, Any]:
    import os
    from pathlib import Path

    adc = Path.home() / ".config/gcloud/application_default_credentials.json"
    return {
        "gce_metadata": False,
        "adc_present": adc.exists() or bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")),
        "cloud_user_token_present": cloud_token_path().exists(),
        "json_key_required": False,
        "reason": (
            "This VM has no GCP metadata identity. Impersonation can work after a short-lived "
            "project-owner Cloud login. A downloaded service-account JSON key is not required and will not be created."
        ),
    }


def cloud_authorization_url() -> dict[str, Any]:
    client = load_desktop_client()
    redirect = redirect_uri(client)
    params = {
        "client_id": client["client_id"],
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": CLOUD_PLATFORM_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "false",
        "login_hint": CLOUD_OWNER_HINT,
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    if any(marker in url for marker in ("gmail.modify", "gmail.send", "gmail.compose", "gmail.readonly", "mail.google.com/")):
        raise OAuthClientError("refusing Cloud OAuth URL that mentions Gmail scopes")
    return {
        "status": "READY_FOR_PROJECT_OWNER_CLOUD_CONSENT",
        "authorization_url": url,
        "sign_in_as": CLOUD_OWNER_HINT,
        "do_not_sign_in_as": "contactus@btpestcontrol.com",
        "scope": CLOUD_PLATFORM_SCOPE,
        "gmail_scopes_requested": False,
        "service_account_key_will_be_created": False,
        "project_id": project_id(),
        "purpose": (
            "Create service account bt-intake-proof-receiver, grant roles/pubsub.subscriber "
            "on bt-intake-proof-contactus-sub only, impersonate that account, and pull."
        ),
    }


def exchange_cloud_code(redirect_or_code: str) -> dict[str, Any]:
    client = load_desktop_client()
    token = _post_form(
        str(client.get("token_uri") or "https://oauth2.googleapis.com/token"),
        {
            "code": extract_auth_code(redirect_or_code),
            "client_id": client["client_id"],
            "client_secret": str(client.get("client_secret") or ""),
            "redirect_uri": redirect_uri(client),
            "grant_type": "authorization_code",
        },
    )
    scopes = str(token.get("scope") or "").split()
    gmail = [scope for scope in scopes if scope in FORBIDDEN_GMAIL_SCOPES or scope == GMAIL_READONLY_SCOPE]
    if gmail:
        raise OAuthClientError(f"Cloud token unexpectedly includes Gmail scopes: {gmail}")
    if CLOUD_PLATFORM_SCOPE not in scopes and "https://www.googleapis.com/auth/pubsub" not in scopes:
        raise OAuthClientError(f"Cloud token missing required Cloud scopes: {scopes}")
    access = str(token.get("access_token") or "")
    if not access:
        raise OAuthClientError("Cloud token response missing access_token")
    info = {}
    try:
        info = _get_json(f"https://www.googleapis.com/oauth2/v3/userinfo", access)
    except OAuthClientError:
        info = _get_json(f"https://www.googleapis.com/oauth2/v1/userinfo", access)
    email = normalize_email(str(info.get("email") or ""))
    if email == "contactus@btpestcontrol.com":
        raise OAuthClientError("Cloud login must be the project owner, not contactus@")
    record = {
        "token_uri": client.get("token_uri") or "https://oauth2.googleapis.com/token",
        "client_id": client["client_id"],
        "client_secret": client.get("client_secret"),
        "refresh_token": token.get("refresh_token"),
        "access_token": access,
        "scopes": scopes,
        "email": email,
        "account": email,
    }
    dest = cloud_token_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    dest.chmod(0o600)
    return {
        "status": "PASS",
        "email": email,
        "scopes": scopes,
        "gmail_scopes": False,
        "refresh_token_present": bool(token.get("refresh_token")),
        "expected_owner_hint": CLOUD_OWNER_HINT,
        "matches_owner_hint": email == ALLOWED_SENDER,
    }
