"""Isolated Fieldwork write MCP. Lead Desk and read-only Fieldwork stay untouched."""

from .service import WriteService

__all__ = ["WriteService"]
