"""Phase 1 Google gates. Never invent a Cloud project or complete silent consent."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .constants import (
    FORBIDDEN_GMAIL_SCOPES,
    GMAIL_READONLY_SCOPE,
    MAILBOX,
)

ROOT = Path(__file__).resolve().parents[2]
SECRETS = ROOT / "secrets"
CONFIG_PATH = ROOT / "config" / "intake.toml"


def _read_config() -> dict[str, str]:
    values: dict[str, str] = {}
    if not CONFIG_PATH.exists():
        return values
    for raw in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


GCP_PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
PLACEHOLDER_PROJECT_IDS = {
    "<put_project_id_here>",
    "put_project_id_here",
    "your-project-id",
    "your_project_id",
    "xxx",
    "todo",
}


def _env_or_config(name: str, config_key: str | None = None) -> str:
    env_val = os.environ.get(name, "").strip()
    if env_val:
        return env_val
    return _read_config().get(config_key or name.lower(), "").strip()


def raw_project_id() -> str:
    return _env_or_config("BT_GCP_PROJECT_ID", "project_id")


def is_usable_project_id(value: str) -> bool:
    cleaned = value.strip()
    if not cleaned or cleaned.lower() in PLACEHOLDER_PROJECT_IDS:
        return False
    return bool(GCP_PROJECT_ID_RE.fullmatch(cleaned))


def project_id() -> str:
    raw = raw_project_id()
    return raw if is_usable_project_id(raw) else ""


def allow_resource_create() -> bool:
    raw = _env_or_config("BT_GCP_ALLOW_RESOURCE_CREATE", "allow_resource_create").lower()
    return raw in {"1", "true", "yes", "on"}


def oauth_client_path() -> Path:
    override = os.environ.get("BT_GMAIL_OAUTH_CLIENT", "").strip()
    return Path(override) if override else SECRETS / "gmail_oauth_client.json"


def token_path() -> Path:
    override = os.environ.get("BT_GMAIL_TOKEN", "").strip()
    return Path(override) if override else SECRETS / "contactus_gmail_readonly_token.json"


def cloud_token_path() -> Path:
    override = os.environ.get("BT_GCP_TOKEN", "").strip()
    return Path(override) if override else SECRETS / "project_owner_cloud_token.json"


def _token_payload() -> dict[str, Any] | None:
    path = token_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"error": "token_unreadable"}
    return data if isinstance(data, dict) else {"error": "token_not_object"}


def token_scopes(payload: dict[str, Any] | None) -> list[str]:
    if not payload:
        return []
    scopes = payload.get("scopes") or payload.get("scope") or []
    if isinstance(scopes, str):
        return [item for item in scopes.replace(",", " ").split() if item]
    if isinstance(scopes, list):
        return [str(item) for item in scopes]
    return []


def scope_violations(scopes: list[str]) -> list[str]:
    found = []
    for scope in scopes:
        if scope in FORBIDDEN_GMAIL_SCOPES:
            found.append(scope)
    return found


def diagnose_google() -> dict[str, Any]:
    """Inspect local Google/Gmail readiness. Does not create or choose a project."""
    cfg = _read_config()
    token = _token_payload()
    scopes = token_scopes(token)
    decisions: list[dict[str, str]] = []
    raw_pid = raw_project_id()
    pid = project_id()
    if not pid:
        rejected = (
            f" Received `{raw_pid}`, which is a placeholder/invalid project ID and was rejected."
            if raw_pid
            else ""
        )
        decisions.append(
            {
                "id": "gcp_project_id",
                "status": "required",
                "ask": (
                    "Name the Google Cloud project I may use for this B&T intake proof only. "
                    "Reply with the real project ID (6-30 lowercase letters, digits, or hyphens). "
                    "I will not pick one from your existing projects."
                    + rejected
                ),
            }
        )
    if not allow_resource_create():
        decisions.append(
            {
                "id": "allow_resource_create",
                "status": "required",
                "ask": (
                    "After you name the project, confirm I may create only these resources "
                    f"in that project: Pub/Sub topic `{cfg.get('topic_id', 'bt-intake-proof-contactus')}`, "
                    "matching subscription, IAM publish grant for gmail-api-push@system.gserviceaccount.com, "
                    "and Gmail API users.watch. Set BT_GCP_ALLOW_RESOURCE_CREATE=yes."
                ),
            }
        )
    if not oauth_client_path().exists():
        decisions.append(
            {
                "id": "oauth_desktop_client",
                "status": "required",
                "ask": (
                    "Create (or export) a Desktop OAuth client in that same project with "
                    f"scope {GMAIL_READONLY_SCOPE} only, then place the client JSON at "
                    f"{oauth_client_path()} or tell me to create the client after you name the project."
                ),
            }
        )
    if token is None:
        decisions.append(
            {
                "id": "contactus_readonly_consent",
                "status": "required",
                "ask": (
                    f"Sign in as {MAILBOX} — not daniel@ — and consent to Gmail read-only. "
                    "I will print an authorization URL and stop. Do not approve send/modify scopes."
                ),
            }
        )

    token_email = ""
    if token:
        token_email = str(token.get("email") or token.get("account") or "").lower()

    blocked = bool(decisions)
    status = "BLOCKED" if blocked else "READY"
    failures: list[str] = []
    if token and token_email and token_email != MAILBOX:
        status = "FAIL"
        failures.append(f"token mailbox is {token_email}, expected {MAILBOX}")
    violations = scope_violations(scopes)
    if violations:
        status = "FAIL"
        failures.append(f"token includes write/send scopes: {violations}")
    if token and GMAIL_READONLY_SCOPE not in scopes and "scope" not in (token.get("error") or ""):
        # Some stored tokens omit scopes until refresh; treat missing file as blocked, not fail.
        if scopes:
            status = "FAIL"
            failures.append("token does not include gmail.readonly")

    return {
        "status": status,
        "mailbox_required": MAILBOX,
        "readonly_scope": GMAIL_READONLY_SCOPE,
        "project_id": pid or None,
        "rejected_project_id": raw_pid if raw_pid and not pid else None,
        "allow_resource_create": allow_resource_create(),
        "oauth_client_present": oauth_client_path().exists(),
        "contactus_token_present": token is not None and "error" not in (token or {}),
        "token_email": token_email or None,
        "token_scopes": scopes,
        "scope_violations": violations,
        "gmail_mcp_note": (
            "Cursor Gmail MCP is authenticated as daniel@btpestcontrol.com and can send/modify. "
            "It is not used for this proof and is not a users.watch + Pub/Sub substitute."
        ),
        "gcloud_present": bool(os.environ.get("CLOUDSDK_CORE_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")),
        "decisions_required": decisions,
        "failures": failures,
        "next_action": (
            "Stop for Daniel. Do not choose a Cloud project, enable billing, or complete consent."
            if blocked
            else "Google local gates are present; continue watch registration."
        ),
    }
