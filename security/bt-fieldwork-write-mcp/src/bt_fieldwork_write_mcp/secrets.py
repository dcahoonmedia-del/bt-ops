"""Load the Fieldwork key into memory only. Never persist or echo it."""

from __future__ import annotations

import os
from pathlib import Path


class InMemoryApiKey:
    """Holds the vendor key for this process. Repr/str never include it."""

    def __init__(self, value: str) -> None:
        self._value = value

    def get(self) -> str:
        return self._value

    def present(self) -> bool:
        return bool(self._value)

    def __repr__(self) -> str:
        return "InMemoryApiKey(present=%s)" % self.present()

    def __str__(self) -> str:
        return self.__repr__()


def load_api_key() -> InMemoryApiKey:
    """Read env or file. Secret Manager is a later host step; this process does not call GCP."""
    raw = os.environ.get("FIELDWORK_API_KEY", "").strip()
    path = os.environ.get("FIELDWORK_API_KEY_FILE", "").strip()
    if not raw and path:
        dest = Path(path)
        if dest.is_file():
            raw = dest.read_text(encoding="utf-8").strip()
    return InMemoryApiKey(raw)
