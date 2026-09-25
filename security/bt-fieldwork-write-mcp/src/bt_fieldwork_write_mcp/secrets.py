"""One-secret read into memory. Never persist, log, or echo the value."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .config import SECRET_RESOURCE
from .errors import GateError


class InMemoryApiKey:
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


def read_one_secret(client: Any, resource: str = SECRET_RESOURCE) -> InMemoryApiKey:
    """Call an injected or SDK client. Exceptions are replaced with a closed gate."""
    if resource != SECRET_RESOURCE:
        raise GateError("secret_resource_rejected")
    try:
        response = client.access_secret_version(request={"name": resource})
        payload = getattr(response, "payload", None)
        if payload is None and isinstance(response, dict):
            payload = response.get("payload")
        data = getattr(payload, "data", None)
        if data is None and isinstance(payload, dict):
            data = payload.get("data")
        if isinstance(data, bytes):
            raw = data.decode("utf-8")
        elif isinstance(data, str):
            raw = data
        else:
            raise GateError("secret_read_failed")
    except GateError:
        raise
    except Exception:
        raise GateError("secret_read_failed") from None
    return InMemoryApiKey(raw.strip())


def secret_manager_client() -> Any:
    try:
        from google.cloud import secretmanager
    except Exception:
        raise GateError("secret_client_unavailable") from None
    try:
        return secretmanager.SecretManagerServiceClient()
    except Exception:
        raise GateError("secret_client_unavailable") from None


def load_api_key(client: Any | None = None) -> InMemoryApiKey:
    """Production path reads Secret Manager in memory. Env/file is offline-only."""
    if client is not None or os.environ.get("FIELDWORK_USE_SECRET_MANAGER", "").strip() in {"1", "true", "yes"}:
        return read_one_secret(client or secret_manager_client(), SECRET_RESOURCE)
    raw = os.environ.get("FIELDWORK_API_KEY", "").strip()
    path = os.environ.get("FIELDWORK_API_KEY_FILE", "").strip()
    if not raw and path:
        dest = Path(path)
        if dest.is_file():
            raw = dest.read_text(encoding="utf-8").strip()
    return InMemoryApiKey(raw)
