"""Merge host env for the desk-roundtrip worker. Never writes tokens."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

PRESERVE_KEYS = (
    "BT_GMAIL_TOKEN",
    "BT_GMAIL_SEND_TOKEN",
    "BT_GMAIL_OAUTH_CLIENT",
    "BT_INTAKE_STORE",
    "BT_GCP_PROJECT_ID",
    "BT_GCP_TOKEN",
    "BT_INTAKE_INTERVAL",
    "CODEX_CONTAINER_MEMORY",
    "OPENAI_API_KEY",
    "CODEX_API_KEY",
    "PYTHONPATH",
    "BT_DANIEL_GMAIL_TOKEN",
)

FORBIDDEN_KEYS = (
    "BT_ALLOW_REAL_CUSTOMER_SENDS",
    "BT_ALLOW_CUSTOMER_SEND",
    "BT_GROK_CUTOVER",
)

DEFAULT_DANIEL_TOKEN = "/opt/bt-intake-proof/secrets/daniel_gmail_readonly_token.json"
DEFAULT_STORE = "/var/lib/bt-intake-proof/receipts.sqlite"


def parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return parse_env(path.read_text(encoding="utf-8"))


def merge_desk_roundtrip_env(
    existing: dict[str, str],
    *,
    prefix: str = "/opt/bt-intake-proof",
    state: str = "/var/lib/bt-intake-proof",
) -> dict[str, str]:
    merged = dict(existing)
    for key in FORBIDDEN_KEYS:
        merged.pop(key, None)
    src = f"{prefix.rstrip('/')}/src"
    pythonpath = merged.get("PYTHONPATH") or ""
    parts = [item for item in pythonpath.split(":") if item]
    if src not in parts:
        parts.insert(0, src)
    merged["PYTHONPATH"] = ":".join(parts)
    merged.setdefault("BT_INTAKE_STORE", f"{state.rstrip('/')}/receipts.sqlite")
    merged.setdefault("BT_GMAIL_TOKEN", f"{prefix}/secrets/contactus_gmail_readonly_token.json")
    merged.setdefault("BT_GMAIL_OAUTH_CLIENT", f"{prefix}/secrets/gmail_oauth_client.json")
    merged.setdefault("BT_GMAIL_SEND_TOKEN", f"{prefix}/secrets/contactus_gmail_send_token.json")
    merged.setdefault("BT_DANIEL_GMAIL_TOKEN", DEFAULT_DANIEL_TOKEN)
    merged.setdefault("BT_INTAKE_INTERVAL", "2")
    merged["BT_INTAKE_MODE"] = "isolated_test"
    return merged


def render_env(values: dict[str, str]) -> str:
    lines = [f"{key}={values[key]}" for key in sorted(values)]
    return "\n".join(lines) + "\n"


def file_fingerprint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    stat = path.stat()
    payload: dict[str, Any] = {
        "path": str(path),
        "mode": oct(stat.st_mode & 0o777),
        "uid": stat.st_uid,
        "gid": stat.st_gid,
        "size": stat.st_size,
    }
    if path.is_file():
        payload["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return payload


def protected_fingerprints(prefix: Path, state: Path) -> dict[str, Any]:
    secrets = prefix / "secrets"
    return {
        "contactus_readonly": file_fingerprint(secrets / "contactus_gmail_readonly_token.json"),
        "contactus_send": file_fingerprint(secrets / "contactus_gmail_send_token.json"),
        "oauth_client": file_fingerprint(secrets / "gmail_oauth_client.json"),
        "daniel_token_meta": _meta_only(secrets / "daniel_gmail_readonly_token.json"),
        "sqlite": file_fingerprint(state / "receipts.sqlite"),
    }


def _meta_only(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    stat = path.stat()
    return {
        "path": str(path),
        "mode": oct(stat.st_mode & 0o777),
        "uid": stat.st_uid,
        "gid": stat.st_gid,
        "present": True,
    }


def protected_unchanged(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    changed = []
    for key in ("contactus_readonly", "contactus_send", "oauth_client", "sqlite", "daniel_token_meta"):
        if before.get(key) != after.get(key):
            changed.append(key)
    return changed
