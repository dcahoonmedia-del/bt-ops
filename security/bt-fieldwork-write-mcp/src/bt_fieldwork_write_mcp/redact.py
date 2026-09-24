"""Never return or log the Fieldwork key or operator key."""

from __future__ import annotations

from typing import Any

REDACT_KEYS = {
    "api_key",
    "auth_token",
    "authorization",
    "token",
    "password",
    "secret",
    "operator_key",
    "hs256_secret",
    "fieldwork_api_key",
    "bt-fieldworks-key",
}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if str(key).lower() in REDACT_KEYS:
                out[key] = "[redacted]"
            else:
                out[key] = redact(item)
        return out
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str) and len(value) > 24 and value.count(".") == 2:
        return "[redacted-jwt]"
    return value


def looks_like_secret(text: str) -> bool:
    lowered = text.lower()
    return any(item in lowered for item in ("token token=", "api_key=", "begin secret"))
