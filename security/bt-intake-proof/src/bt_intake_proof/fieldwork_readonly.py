"""Read-only Fieldwork client. No create/update/cancel/schedule/charge methods."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import Request

from .store import utc_now

BASE = "https://api3.fieldworkhq.com"
AUTH_PATH = "/v3.1/get_api_key"
HOST = "api3.fieldworkhq.com"

# Documented GET collection/show paths only. POST/PATCH/PUT/DELETE stay forbidden.
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
    "/v3.1/estimates/search",
    "/v3.1/service_agreement_setups",
    "/v3.1/service_agreement_setups/search",
    "/v3.1/service_agreements",
    "/v3.1/agreement_appointments",
    "/v3.1/service_routes",
    "/v3.1/calendar",
)

COLLECTION_KEYS = (
    "data",
    "customers",
    "service_locations",
    "contacts",
    "notes",
    "work_orders",
    "estimates",
    "service_agreement_setups",
    "agreement_appointments",
    "results",
    "items",
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

DEFAULT_PER_PAGE = 10
DEFAULT_MAX_PAGES = 3
DEFAULT_MAX_REQUESTS = 40
RUNNER_MAX_REQUESTS = 200


class FieldworkWriteForbidden(RuntimeError):
    """Raised when any non-read Fieldwork operation is attempted."""


class FieldworkReadError(RuntimeError):
    """Safe read failure. Message never includes credentials or full authenticated URLs."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ListFetch(list):
    """List of dict rows plus completeness. Empty is not the same as failed."""

    def __init__(
        self,
        items: list[dict[str, Any]] | None = None,
        *,
        ok: bool = True,
        reason: str | None = None,
        incomplete: bool = False,
        truncated: bool = False,
        schema_ok: bool = True,
    ) -> None:
        super().__init__(items or [])
        self.ok = ok
        self.reason = reason
        self.incomplete = incomplete
        self.truncated = truncated
        self.schema_ok = schema_ok

    @property
    def items(self) -> list[dict[str, Any]]:
        return list(self)


class _SameHostRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse credential-bearing redirects to a different host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        old_host = urlparse(req.full_url).netloc
        new_host = urlparse(newurl).netloc
        if new_host and old_host and new_host.lower() != old_host.lower():
            raise FieldworkReadError("redirect_other_host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


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
    if re.fullmatch(r"/v3\.1/service_agreement_setups/\d+/agreement_appointments(/\d+)?", clean):
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


def parse_collection(payload: Any) -> ListFetch:
    """Map documented Fieldwork list wrappers. Unknown objects are schema failures, not []."""
    if payload is None:
        return ListFetch([], ok=True, schema_ok=True)
    if isinstance(payload, list):
        return ListFetch([item for item in payload if isinstance(item, dict)])
    if isinstance(payload, dict):
        for key in COLLECTION_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                return ListFetch([item for item in value if isinstance(item, dict)])
        if payload.get("id") is not None:
            return ListFetch([payload])
        return ListFetch([], ok=False, reason="schema_mismatch", schema_ok=False, incomplete=True)
    return ListFetch([], ok=False, reason="schema_mismatch", schema_ok=False, incomplete=True)


def as_fetch(result: Any) -> ListFetch:
    """Normalize fixture lists and live ListFetch rows. A plain [] is complete, not failed."""
    if isinstance(result, ListFetch):
        return result
    if isinstance(result, list):
        return ListFetch([item for item in result if isinstance(item, dict)])
    if result is None:
        return ListFetch([])
    return ListFetch([], ok=False, reason="not_a_list", incomplete=True)


def _as_list(payload: Any) -> list[dict[str, Any]]:
    fetched = parse_collection(payload)
    return list(fetched) if fetched.ok else []


def sanitize_reason(exc: BaseException) -> str:
    if isinstance(exc, FieldworkReadError):
        return exc.reason
    if isinstance(exc, FieldworkWriteForbidden):
        return "write_forbidden"
    if isinstance(exc, urllib.error.HTTPError):
        return f"http_{exc.code}"
    if isinstance(exc, urllib.error.URLError):
        return "network_error"
    name = type(exc).__name__
    if name in {"JSONDecodeError", "UnicodeDecodeError"}:
        return "schema_mismatch"
    return "read_failed"


class ReadOnlyFieldworkClient:
    """Host-side Fieldwork adapter. Isolated Codex never receives this object or its credentials."""

    def __init__(
        self,
        token: str | None = None,
        getter: Callable[..., Any] | None = None,
        *,
        live: bool = False,
        max_requests: int = DEFAULT_MAX_REQUESTS,
        max_pages: int = DEFAULT_MAX_PAGES,
        per_page: int = DEFAULT_PER_PAGE,
    ) -> None:
        self.token = token
        self._getter = getter
        self.live = live
        self.max_requests = max_requests
        self.max_pages = max_pages
        self.per_page = per_page
        self.calls: list[dict[str, Any]] = []
        self.write_attempts = 0
        self.fetch_issues: list[dict[str, Any]] = []
        self.provider_token_scope_verified = False
        self.adapter_enforced_read_only = True
        self.work_order_query_supported = False

    @classmethod
    def from_env(cls) -> "ReadOnlyFieldworkClient":
        token = os.environ.get("FIELDWORK_API_KEY") or ""
        secret_file = os.environ.get("FIELDWORK_API_KEY_FILE", "")
        if not token and secret_file and os.path.exists(secret_file):
            token = open(secret_file, encoding="utf-8").read().strip()
        client = cls(token=token or None, live=True)
        return client

    def snapshot_meta(self) -> dict[str, Any]:
        return {}

    def login_for_token(self) -> dict[str, Any]:
        """Existing host login helper. Never prints the token. Not used by the always-on receiver."""
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
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "reason": sanitize_reason(exc)}
        token = body.get("api_key") or body.get("auth_token")
        self.token = token or None
        return {
            "ok": bool(self.token),
            "reason": None if self.token else "fieldwork_api_key_not_issued",
            "user_id": body.get("user_id"),
            "roles": body.get("roles"),
            "customer_access": body.get("customer_access"),
            "provider_token_scope_verified": False,
            "adapter_enforced_read_only": True,
        }

    def _budget(self) -> None:
        if len(self.calls) >= self.max_requests:
            raise FieldworkReadError("request_budget_exhausted")

    def _request(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
        method = method.upper()
        if method != "GET":
            self.write_attempts += 1
            raise FieldworkWriteForbidden(f"Fieldwork {method} {path} is forbidden")
        if not _path_allowed(path):
            self.write_attempts += 1
            raise FieldworkWriteForbidden(f"Fieldwork path not on the read allowlist: {path}")
        self._budget()
        self.calls.append({"method": "GET", "path": path, "at": utc_now(), "params": sorted((params or {}).keys())})
        if self._getter is not None:
            return redact(self._getter(path, params or {}))
        if not self.token:
            raise FieldworkReadError("fieldwork_api_key_not_issued")
        qs = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{BASE}{path}"
        if qs:
            url = f"{url}?{qs}"
        req = Request(url, method="GET")
        req.add_header("Accept", "application/json")
        req.add_header("Authorization", f"Token token={self.token}")
        opener = urllib.request.build_opener(_SameHostRedirect)
        try:
            with opener.open(req, timeout=30) as resp:
                raw = resp.read()
                final = urlparse(resp.geturl())
                if final.netloc and final.netloc.lower() != HOST:
                    raise FieldworkReadError("redirect_other_host")
        except FieldworkReadError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FieldworkReadError(sanitize_reason(exc)) from None
        if not raw:
            return None
        try:
            return redact(json.loads(raw))
        except Exception as exc:  # noqa: BLE001
            raise FieldworkReadError(sanitize_reason(exc)) from None

    def get(self, path: str, **params: Any) -> Any:
        return self._request("GET", path, params)

    def fetch_collection(self, path: str, **params: Any) -> ListFetch:
        merged = dict(params)
        merged.setdefault("per_page", self.per_page)
        page = int(merged.get("page") or 1)
        rows: list[dict[str, Any]] = []
        truncated = False
        try:
            for index in range(self.max_pages):
                merged["page"] = page + index
                payload = self.get(path, **merged)
                parsed = parse_collection(payload)
                if not parsed.ok:
                    self.fetch_issues.append({"path": path, "reason": parsed.reason})
                    return parsed
                rows.extend(parsed)
                if len(parsed) < int(merged.get("per_page") or self.per_page):
                    return ListFetch(rows)
            if len(rows) >= int(merged.get("per_page") or self.per_page) * self.max_pages:
                truncated = True
                self.fetch_issues.append({"path": path, "reason": "pagination_truncated"})
                return ListFetch(rows, incomplete=True, truncated=True, reason="pagination_truncated")
            return ListFetch(rows, incomplete=truncated, truncated=truncated)
        except FieldworkReadError as exc:
            self.fetch_issues.append({"path": path, "reason": exc.reason})
            return ListFetch([], ok=False, reason=exc.reason, incomplete=True)
        except FieldworkWriteForbidden as exc:
            self.fetch_issues.append({"path": path, "reason": "write_forbidden"})
            raise exc

    def search_customers(self, query: str, customer_status: str | None = None) -> ListFetch:
        params: dict[str, Any] = {"query": query}
        if customer_status:
            params["filter[customer_status]"] = customer_status
        return self.fetch_collection("/v3.1/customers/search", **params)

    def search_customers_by_phone(self, phone: str) -> ListFetch:
        return self.fetch_collection("/v3.1/customers/search_by_phone", phone=phone, as_object=True)

    def get_customer(self, customer_id: int | str) -> dict[str, Any]:
        payload = self.get(f"/v3.1/customers/{customer_id}")
        if isinstance(payload, dict) and payload.get("id") is not None:
            return payload
        raise FieldworkReadError("customer_schema_invalid")

    def get_location(self, location_id: int | str, customer_id: int | str | None = None) -> dict[str, Any]:
        if customer_id:
            payload = self.get(f"/v3.1/customers/{customer_id}/service_locations/{location_id}")
        else:
            payload = self.get(f"/v3.1/service_locations/{location_id}")
        if isinstance(payload, dict) and payload.get("id") is not None:
            return payload
        raise FieldworkReadError("location_schema_invalid")

    def list_locations(self, customer_id: int | str) -> ListFetch:
        return self.fetch_collection(f"/v3.1/customers/{customer_id}/service_locations")

    def list_contacts(self, customer_id: int | str) -> ListFetch:
        return self.fetch_collection(f"/v3.1/customers/{customer_id}/contacts")

    def list_notes(self, customer_id: int | str) -> ListFetch:
        return self.fetch_collection(f"/v3.1/customers/{customer_id}/notes")

    def search_work_orders(self, **params: Any) -> ListFetch:
        return self.fetch_collection("/v3.1/work_orders/search", **params)

    def list_agreements(self, **params: Any) -> ListFetch:
        return self.fetch_collection("/v3.1/service_agreement_setups", **params)

    def list_estimates(self, **params: Any) -> ListFetch:
        return self.fetch_collection("/v3.1/estimates", **params)

    def list_agreement_appointments(self, agreement_id: int | str) -> ListFetch:
        return self.fetch_collection(f"/v3.1/service_agreement_setups/{agreement_id}/agreement_appointments")

    def check_connection(self) -> dict[str, Any]:
        try:
            payload = self.get("/v3.1/check_connection")
            return {"ok": True, "live": self.live, "payload_type": type(payload).__name__}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "live": self.live, "reason": sanitize_reason(exc)}

    def create_customer(self, *_args: Any, **_kwargs: Any) -> None:
        self._request("POST", "/v3.1/customers")

    def update_customer(self, customer_id: int | str, **_kwargs: Any) -> None:
        self._request("PATCH", f"/v3.1/customers/{customer_id}")

    def create_work_order(self, *_args: Any, **_kwargs: Any) -> None:
        self._request("POST", "/v3.1/work_orders")


def grok_bot_client() -> ReadOnlyFieldworkClient:
    """Fixture client for the always-on receiver. Never a live HQ client."""
    from .fieldwork_fixture import GrokBotFieldwork

    snapshot = os.environ.get("BT_FIELDWORK_SNAPSHOT") or None
    return GrokBotFieldwork(snapshot=snapshot)


def live_read_client() -> ReadOnlyFieldworkClient:
    """Explicit live reader only. Requires BT_FIELDWORK_LIVE_READ=1. Does not change the receiver."""
    if os.environ.get("BT_FIELDWORK_LIVE_READ") != "1":
        raise FieldworkReadError("live_read_not_enabled")
    client = ReadOnlyFieldworkClient.from_env()
    client.max_requests = RUNNER_MAX_REQUESTS
    if not client.token:
        raise FieldworkReadError("fieldwork_api_key_not_issued")
    return client
