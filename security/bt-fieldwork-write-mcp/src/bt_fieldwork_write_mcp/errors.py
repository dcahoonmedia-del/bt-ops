"""Closed-gate errors. Unknown or unverified work fails closed."""

from __future__ import annotations

from typing import Any


class GateError(RuntimeError):
    def __init__(self, gate: str, **detail: Any) -> None:
        self.gate = gate
        self.detail = detail
        super().__init__(gate)

    def as_dict(self) -> dict[str, Any]:
        payload = {"ok": False, "gate": self.gate}
        payload.update(self.detail)
        return payload


class AmbiguousWriteError(RuntimeError):
    """Remote write was sent; outcome is not confirmed. Do not retry."""

    def __init__(self, reason: str = "ambiguous", diagnostic: dict[str, Any] | None = None) -> None:
        self.reason = reason
        self.diagnostic = diagnostic or {
            "status": "unknown",
            "content_type": "unknown",
            "top_level_keys": [],
            "parser_stage": "unspecified",
            "response_body_retained": False,
        }
        super().__init__(reason)
