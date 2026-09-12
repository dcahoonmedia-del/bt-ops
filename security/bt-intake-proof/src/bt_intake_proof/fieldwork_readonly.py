"""Read-only Fieldwork client. No create/update/cancel/schedule/charge methods."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable
from urllib.request import Request

from .store import utc_now

BASE = "https://api3.fieldworkhq.com"
AUTH_PATH = "/v3.1/get_api_key"

ALLOWED_GET = (
    "/v3.1/check_connection",
    "/v3.1/customers",
    "/v3.1/customers/search",
    "/v3.1/customers/search_by_phone",
    "/v3.1/service_locations",
    "/v3.1/work_orders",
    "/v3.1/work_orders/search",
    "/v3.1/contacts",
    "/v3.1/notes",
    "/v3.1/estimates",
    "/v3.1/service_agreement_setups",
    "/v3.1/service_agreements",
    "/v3.1/agreement_appointments",
    "/v3.1/service_routes",
    "/v3.1/calendar",
)

REDACT_KEYS = {
    "credit_card",
    "card_number",
    "card_last4",
    "cvv",
    "cvc",
    "stripe_card_token",
    "stripe_customer_id",
    "setup_intent_id",
    "access_code",
    "gate_code",
    "lockbox",
    "lock_box",
    "alarm_code",
    "ssn",
    "social_security",
    "bank_account",
    "routing_number",
    "password",
    "api_key",
    "auth_token",
    "calls_auth_token",
}


class FieldworkWriteForbidden(RuntimeError):
    """Raised when any non-read Fieldwork operation is attempted."""


def _path_allowed(path: str) -> bool:
    clean = path.split("?", 1)[0]
    if clean in ALLOWED_GET:
        return True
    if re.fullmatch(r"/v3\.1/customers/\d+", clean):
        return True
    if re.fullmatch(r"/v3\.1/customers/\d+/service_locations(/\d+)?", clean):
        return True
    if re.fullmatch(r"/v3\.1/customers/\d+/contacts(/\d+)?", clean):
        return True
    if re.fullmatch(r"/v3\.1/customers/\d+/notes", clean):
        return True
    if re.fullmatch(r"/v3\.1/work_orders/\d+", clean):
        return True
    if re.fullmatch(r"/v3\.1/service_locations/\d+", clean):
        return True
    if re.fullmatch(r"/v3\.1/service_agreement_setups/\d+", clean):
        return True
    if re.fullmatch(r"/v3\.1/estimates/\d+", clean):
        return True
    return False


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if str(key).lower() in REDACT_KEYS:
                continue
            out[key] = redact(item)
        return out
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class ReadOnlyFieldworkClient:
    """Host-side Fieldwork adapter. Isolated Codex never receives this object or its credentials."""

    def __init__(self, token: str | None = None, getter: Callable[..., Any] | None = None) -> None:
        self.token = token
        self._getter = getter
        self.calls: list[dict[str, Any]] = []
        self.write_attempts = 0

    @classmethod
    def from_env(cls) -> "ReadOnlyFieldworkClient":
        token = os.environ.get("FIELDWORK_API_KEY") or ""
        secret_file = os.environ.get("FIELDWORK_API_KEY_FILE", "")
        if not token and secret_file and os.path.exists(secret_file):
            token = open(secret_file, encoding="utf-8").read().strip()
        client = cls(token=token or None)
        if not client.token:
            client.login_for_token()
        return client

    def login_for_token(self) -> dict[str, Any]:
        email = os.environ.get("FIELDWORK_EMAIL")
        password = os.environ.get("FIELDWORK_PASSWORD")
        if not email or not password:
            return {"ok": False, "reason": "missing_fieldwork_login"}
        qs = urllib.parse.urlencode({"email": email, "password": password})
        req = Request(f"{BASE}{AUTH_PATH}?{qs}", method="POST", data=b"")
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return {"ok": False, "reason": f"login_http_{exc.code}"}
        token = body.get("api_key") or body.get("auth_token")
        self.token = token or None
        return {
            "ok": bool(self.token),
            "reason": None if self.token else "fieldwork_api_key_not_issued",
            "user_id": body.get("user_id"),
            "roles": body.get("roles"),
            "customer_access": body.get("customer_access"),
        }

    def _request(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
        method = method.upper()
        if method != "GET":
            self.write_attempts += 1
            raise FieldworkWriteForbidden(f"Fieldwork {method} {path} is forbidden in Phase D")
        if not _path_allowed(path):
            self.write_attempts += 1
            raise FieldworkWriteForbidden(f"Fieldwork path not on the read allowlist: {path}")
        self.calls.append({"method": "GET", "path": path, "at": utc_now(), "params": sorted((params or {}).keys())})
        if self._getter is not None:
            return redact(self._getter(path, params or {}))
        if not self.token:
            raise RuntimeError("fieldwork_api_key_not_issued")
        qs = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{BASE}{path}"
        if qs:
            url = f"{url}?{qs}"
        req = Request(url, method="GET")
        req.add_header("Accept", "application/json")
        req.add_header("Authorization", f"Token token={self.token}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
        if not raw:
            return None
        return redact(json.loads(raw))

    def get(self, path: str, **params: Any) -> Any:
        return self._request("GET", path, params)

    def search_customers(self, query: str, customer_status: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"query": query, "per_page": 10}
        if customer_status:
            params["filter[customer_status]"] = customer_status
        payload = self.get("/v3.1/customers/search", **params)
        return _as_list(payload)

    def search_customers_by_phone(self, phone: str) -> list[dict[str, Any]]:
        payload = self.get("/v3.1/customers/search_by_phone", phone=phone, as_object=True)
        return _as_list(payload)

    def get_customer(self, customer_id: int | str) -> dict[str, Any]:
        payload = self.get(f"/v3.1/customers/{customer_id}")
        return payload if isinstance(payload, dict) else {}

    def list_locations(self, customer_id: int | str) -> list[dict[str, Any]]:
        return _as_list(self.get(f"/v3.1/customers/{customer_id}/service_locations", per_page=25))

    def list_contacts(self, customer_id: int | str) -> list[dict[str, Any]]:
        return _as_list(self.get(f"/v3.1/customers/{customer_id}/contacts", per_page=25))

    def list_notes(self, customer_id: int | str) -> list[dict[str, Any]]:
        try:
            return _as_list(self.get(f"/v3.1/customers/{customer_id}/notes", per_page=10))
        except Exception:
            return []

    def search_work_orders(self, **params: Any) -> list[dict[str, Any]]:
        payload = self.get("/v3.1/work_orders/search", per_page=10, **params)
        return _as_list(payload)

    def list_agreements(self, **params: Any) -> list[dict[str, Any]]:
        try:
            return _as_list(self.get("/v3.1/service_agreement_setups", per_page=10, **params))
        except Exception:
            return []

    def list_estimates(self, **params: Any) -> list[dict[str, Any]]:
        try:
            return _as_list(self.get("/v3.1/estimates", per_page=5, **params))
        except Exception:
            return []

    def create_customer(self, *_args: Any, **_kwargs: Any) -> None:
        self._request("POST", "/v3.1/customers")

    def update_customer(self, customer_id: int | str, **_kwargs: Any) -> None:
        self._request("PATCH", f"/v3.1/customers/{customer_id}")

    def create_work_order(self, *_args: Any, **_kwargs: Any) -> None:
        self._request("POST", "/v3.1/work_orders")


def grok_bot_client() -> ReadOnlyFieldworkClient:
    """Read-only fixture by default. Live HQ is not used for Phase D matching."""
    from .fieldwork_fixture import GrokBotFieldwork

    snapshot = os.environ.get("BT_FIELDWORK_SNAPSHOT") or None
    return GrokBotFieldwork(snapshot=snapshot)


def _as_list(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "customers", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if payload.get("id") is not None:
            return [payload]
    return []
