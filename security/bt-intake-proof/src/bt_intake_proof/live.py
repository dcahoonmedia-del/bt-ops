"""Live watch/receive helpers. Refuse to run until Daniel's Google gates are READY."""

from __future__ import annotations

from typing import Any

from .gates import diagnose_google
from .setup_google import blocked_setup


def require_ready() -> dict[str, Any]:
    diagnosis = diagnose_google()
    if diagnosis["status"] != "READY":
        return blocked_setup(diagnosis)
    return {"status": "READY", "stop": False, "diagnosis": diagnosis}
