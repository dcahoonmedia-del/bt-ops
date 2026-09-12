"""Use the GCE attached service account. Never downloads a JSON key."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .constants import RECEIVER_SA_ID

METADATA = "http://169.254.169.254/computeMetadata/v1"
PUBSUB_SCOPE = "https://www.googleapis.com/auth/pubsub"


class MetadataError(RuntimeError):
    pass


def metadata_available() -> bool:
    if os.environ.get("BT_FORCE_GCE_METADATA", "").strip() in {"0", "false", "no"}:
        return False
    try:
        request = urllib.request.Request(
            f"{METADATA}/instance/service-accounts/default/email",
            method="GET",
        )
        request.add_header("Metadata-Flavor", "Google")
        with urllib.request.urlopen(request, timeout=1.0) as response:
            email = response.read().decode("utf-8").strip()
        return bool(email)
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def attached_service_account_email() -> str:
    request = urllib.request.Request(
        f"{METADATA}/instance/service-accounts/default/email",
        method="GET",
    )
    request.add_header("Metadata-Flavor", "Google")
    try:
        with urllib.request.urlopen(request, timeout=2.0) as response:
            return response.read().decode("utf-8").strip()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise MetadataError("GCE metadata identity is not available") from exc


def metadata_access_token(scope: str = PUBSUB_SCOPE) -> str:
    query = urllib.parse.urlencode({"scopes": scope})
    request = urllib.request.Request(
        f"{METADATA}/instance/service-accounts/default/token?{query}",
        method="GET",
    )
    request.add_header("Metadata-Flavor", "Google")
    try:
        with urllib.request.urlopen(request, timeout=5.0) as response:
            payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise MetadataError("could not mint an attached-service-account token") from exc
    token = str(payload.get("access_token") or "")
    if not token:
        raise MetadataError("metadata token response missing access_token")
    return token


def receiver_identity() -> dict[str, Any]:
    """Prefer attached GCE identity. Impersonation is the laptop/agent fallback."""
    if metadata_available():
        email = attached_service_account_email()
        return {
            "source": "gce_metadata",
            "service_account": email,
            "matches_receiver_id": RECEIVER_SA_ID in email,
            "json_key_created": False,
            "impersonation": False,
        }
    return {
        "source": "impersonation_fallback",
        "service_account": None,
        "matches_receiver_id": False,
        "json_key_created": False,
        "impersonation": True,
    }
