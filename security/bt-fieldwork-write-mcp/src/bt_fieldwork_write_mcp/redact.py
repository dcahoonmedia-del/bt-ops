"""Never return or log the Fieldwork key or operator key."""

from __future__ import annotations

import base64
import json
import re
from typing import Any

_JWT_CANDIDATE = re.compile(r"[A-Za-z0-9_-]{2,}\.[A-Za-z0-9_-]{2,}\.[A-Za-z0-9_-]{2,}")

REDACT_KEYS = {
    "api_key",
    "access_token",
    "refresh_token",
    "id_token",
    "client_secret",
    "calls_auth_token",
    "operator_approval",
    "auth_token",
    "authorization",
    "token",
    "password",
    "secret",
    "operator_key",
    "hs256_secret",
    "fieldwork_api_key",
    "bt-fieldworks-key",
    "stripe_pk",
    "card_number",
    "credit_card",
}


def _jwt_header(segment: str) -> bool:
    padded = segment + "=" * (-len(segment) % 4)
    try:
        header = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, json.JSONDecodeError):
        return False
    return isinstance(header, dict) and isinstance(header.get("alg"), str) and bool(header["alg"])


def _mask_tokens(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if _jwt_header(token.split(".", 1)[0]):
            return "[redacted-jwt]"
        return token

    return _JWT_CANDIDATE.sub(replace, text)


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
    if isinstance(value, str):
        return _mask_tokens(value)
    return value


def looks_like_secret(text: str) -> bool:
    lowered = text.lower()
    return any(item in lowered for item in ("token token=", "api_key=", "begin secret"))
