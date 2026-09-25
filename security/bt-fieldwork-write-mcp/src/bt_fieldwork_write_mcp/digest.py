"""Canonical JSON and proposal identity binding."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def proposal_digest(
    *,
    proposal_id: str,
    operation: str,
    identity: dict[str, str],
    target: str,
    before: dict[str, Any],
    after: dict[str, Any],
    payload: dict[str, Any],
    created_at: str,
    expires_at: str,
) -> str:
    return sha256_hex(
        canonical(
            {
                "proposal_id": proposal_id,
                "operation": operation,
                "identity": {"sub": identity.get("sub", ""), "email": identity.get("email", "")},
                "target": target,
                "before": before,
                "after": after,
                "payload": payload,
                "created_at": created_at,
                "expires_at": expires_at,
            }
        )
    )
