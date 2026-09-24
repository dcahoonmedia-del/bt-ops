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
    operation: str,
    identity: dict[str, str],
    subject_key: str,
    before: dict[str, Any],
    after: dict[str, Any],
    payload: dict[str, Any],
) -> str:
    return sha256_hex(
        canonical(
            {
                "operation": operation,
                "identity": {"sub": identity.get("sub", ""), "email": identity.get("email", "")},
                "subject_key": subject_key,
                "before": before,
                "after": after,
                "payload": payload,
            }
        )
    )
