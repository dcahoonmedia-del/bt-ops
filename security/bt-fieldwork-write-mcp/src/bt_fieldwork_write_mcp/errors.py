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
