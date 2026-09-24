"""Typed Fieldwork calls only. No generic HTTP passthrough. Key stays in memory."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Protocol
from urllib.request import Request

from .allowlist import (
    GATE_AUTH_UNRESOLVED,
    GATE_LIVE_PATCH_UNTESTED,
    GATE_SCHEMA_UNVERIFIED,
    is_lead_status,
)
from .config import API_BASE
from .digest import canonical, sha256_hex
from .errors import AmbiguousWriteError, GateError
from .secrets import InMemoryApiKey

_CUSTOMER = re.compile(r"^/customers/\d+$")
_LOCATION = re.compile(r"^/customers/\d+/service_locations/\d+$")
_WORK_ORDER = re.compile(r"^/work_orders/\d+$")
_WORK_ORDER_PLAIN = re.compile(r"^/work_orders/\d+/show_plain$")
_WORK_ORDER_SEARCH = re.compile(r"^/work_orders(/search)?$")


def _as_list(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "work_orders", "results", "items", "customers"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if payload.get("id") is not None:
            return [payload]
    return []


def unwrap_service_location(payload: dict[str, Any]) -> dict[str, Any]:
    wrapped = payload.get("service_location")
    if isinstance(wrapped, dict):
        return wrapped
    return payload


def unwrap_occurrence(payload: dict[str, Any]) -> dict[str, Any]:
    wrapped = payload.get("appointment_occurrence")
    if isinstance(wrapped, dict):
        return wrapped
    return payload


def occurrence_ids(record: dict[str, Any]) -> dict[str, Any]:
    row = unwrap_occurrence(record)
    return {
        "work_order_id": row.get("id"),
        "service_appointment_id": row.get("service_appointment_id"),
        "customer_id": row.get("customer_id"),
        "service_location_id": row.get("service_location_id"),
        "arrival_time_window": row.get("arrival_time_window"),
        "arrival_time_window_start": row.get("arrival_time_window_start"),
        "arrival_time_window_end": row.get("arrival_time_window_end"),
        "arrival_window_display": row.get("arrival_window_display") or row.get("arrival_time_window_display"),
    }


def location_snapshot(customer: dict[str, Any], location: dict[str, Any]) -> dict[str, Any]:
    location = unwrap_service_location(location)
    address = location.get("address") if isinstance(location.get("address"), dict) else {}
    if not address and isinstance(location.get("address_attributes"), dict):
        address = location["address_attributes"]
    return {
        "customer_id": customer.get("id") or location.get("customer_id"),
        "customer_status": customer.get("customer_status") or customer.get("status") or customer.get("type"),
        "location_id": location.get("id"),
        "name": location.get("name"),
        "tax_rate_id": location.get("tax_rate_id"),
        "address_id": address.get("id"),
        "notes": address.get("notes") if "notes" in address else location.get("notes"),
    }


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    return sha256_hex(canonical(snapshot))


class Transport(Protocol):
    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
        ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class HttpTransport:
    """Query-parameter auth. Never logs the URL or exception text."""

    def __init__(self, api_key: InMemoryApiKey, api_base: str = API_BASE, opener: Any | None = None) -> None:
        self._key = api_key
        self.api_base = api_base.rstrip("/")
        self._opener = opener or urllib.request.build_opener(_NoRedirect)

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
        if not self._key.present():
            raise GateError(GATE_AUTH_UNRESOLVED, reason="fieldwork_api_key_absent")
        clean = path.split("?", 1)[0]
        query = urllib.parse.urlencode({"api_key": self._key.get()})
        url = f"{self.api_base}{clean}?{query}"
        data = None if body is None else urllib.parse.urlencode(_flatten(body)).encode("utf-8")
        req = Request(url, data=data, method=method)
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        sent = method.upper() in {"POST", "PATCH", "PUT", "DELETE"}
        try:
            with self._opener.open(req, timeout=30) as resp:
                raw = resp.read()
                status = int(resp.status)
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            raw = exc.read() if status < 500 else b""
            if sent and status >= 500:
                raise AmbiguousWriteError(f"remote_{status}") from None
            if status in {301, 302, 303, 307, 308}:
                raise GateError("redirect_rejected", status=status) from None
            try:
                parsed = json.loads(raw.decode("utf-8")) if raw else None
            except (json.JSONDecodeError, UnicodeError):
                parsed = None
            return status, parsed
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            if sent:
                raise AmbiguousWriteError("transport_drop_after_send") from None
            raise GateError("transport_error") from None
        if not raw:
            return status, None
        try:
            return status, json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeError):
            if sent:
                raise AmbiguousWriteError("unreadable_write_response") from None
            raise GateError("unreadable_response") from None


def _flatten(body: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in body.items():
        name = f"{prefix}[{key}]" if prefix else str(key)
        if isinstance(value, dict):
            flat.update(_flatten(value, name))
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                if isinstance(item, dict):
                    flat.update(_flatten(item, f"{name}[]"))
                else:
                    flat[f"{name}[]"] = item if idx == 0 and f"{name}[]" not in flat else item
                    if idx:
                        flat[f"{name}[{idx}]"] = item
        elif value is not None:
            flat[name] = value
    return flat


class FakeTransport:
    """In-process Fieldwork stand-in. Never talks to HQ."""

    def __init__(self) -> None:
        self.customers: dict[str, dict[str, Any]] = {}
        self.locations: dict[str, dict[str, Any]] = {}
        self.work_orders: dict[str, dict[str, Any]] = {}
        self.calls: list[dict[str, Any]] = []
        self.write_mode: str = "ok"  # ok | ambiguous | http_500 | drop
        self.readback_notes: str | None = None

    def add_customer(self, customer: dict[str, Any], location: dict[str, Any]) -> None:
        cid = str(customer["id"])
        lid = str(location["id"])
        self.customers[cid] = customer
        location = dict(location)
        location["customer_id"] = customer["id"]
        self.locations[f"{cid}:{lid}"] = location

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
        self.calls.append({"method": method, "path": path, "body": body})
        if method in {"POST", "PATCH", "PUT", "DELETE"}:
            if self.write_mode == "ambiguous":
                raise AmbiguousWriteError("fake_ambiguous")
            if self.write_mode == "drop":
                raise AmbiguousWriteError("fake_drop")
            if self.write_mode == "http_500":
                raise AmbiguousWriteError("remote_500")
        if method == "GET" and _CUSTOMER.match(path):
            cid = path.rsplit("/", 1)[-1]
            customer = self.customers.get(cid)
            return (200, customer) if customer else (404, None)
        if method == "GET" and _LOCATION.match(path):
            parts = path.split("/")
            key = f"{parts[2]}:{parts[4]}"
            loc = self.locations.get(key)
            if loc is None:
                return 404, None
            view = dict(loc)
            if self.readback_notes is not None:
                address = dict(view.get("address") or {})
                address["notes"] = self.readback_notes
                view["address"] = address
            return 200, {"service_location": view}
        if method == "PATCH" and _LOCATION.match(path):
            parts = path.split("/")
            key = f"{parts[2]}:{parts[4]}"
            loc = self.locations.get(key)
            if loc is None:
                return 404, None
            sl = (body or {}).get("service_location") or {}
            addr = sl.get("address_attributes") or {}
            location = dict(loc)
            if sl.get("name") is not None:
                location["name"] = sl["name"]
            if sl.get("tax_rate_id") is not None:
                location["tax_rate_id"] = sl["tax_rate_id"]
            address = dict(location.get("address") or {})
            if addr.get("id") is not None:
                address["id"] = addr["id"]
            if "notes" in addr:
                address["notes"] = addr["notes"]
            location["address"] = address
            self.locations[key] = location
            return 200, {"service_location": location}
        if method == "GET" and (_WORK_ORDER.match(path) or _WORK_ORDER_PLAIN.match(path) or _WORK_ORDER_SEARCH.match(path)):
            if "/search" in path or path == "/work_orders":
                return 200, list(self.work_orders.values())
            wid = path.split("/")[2]
            wo = self.work_orders.get(str(wid))
            if wo is None:
                return 404, None
            return 200, {"appointment_occurrence": wo}
        if method in {"POST", "PATCH"} and path.startswith("/work_orders"):
            return 403, {"error": "live_patch_untested"}
        return 404, None


def _assert_typed_path(method: str, path: str) -> None:
    if method == "GET" and (
        _CUSTOMER.match(path)
        or _LOCATION.match(path)
        or _WORK_ORDER.match(path)
        or _WORK_ORDER_PLAIN.match(path)
        or _WORK_ORDER_SEARCH.match(path)
    ):
        return
    if method == "PATCH" and _LOCATION.match(path):
        return
    if method == "PATCH" and _WORK_ORDER.match(path):
        raise GateError(GATE_LIVE_PATCH_UNTESTED)
    if method == "POST" and path == "/work_orders":
        raise GateError(GATE_SCHEMA_UNVERIFIED)
    raise GateError("unknown_operation", method=method, path=path)


class TypedFieldworkClient:
    def __init__(self, transport: Transport, *, mapping_verified: bool = False) -> None:
        self.transport = transport
        self.mapping_verified = mapping_verified

    def get_customer(self, customer_id: str) -> dict[str, Any]:
        status, body = self.transport.request("GET", f"/customers/{customer_id}")
        if status != 200 or not isinstance(body, dict):
            raise GateError("customer_not_found", status=status)
        return body

    def get_location(self, customer_id: str, location_id: str) -> dict[str, Any]:
        status, body = self.transport.request("GET", f"/customers/{customer_id}/service_locations/{location_id}")
        if status != 200 or not isinstance(body, dict):
            raise GateError("location_not_found", status=status)
        return unwrap_service_location(body)

    def search_work_orders(self) -> list[dict[str, Any]]:
        status, body = self.transport.request("GET", "/work_orders/search")
        if status != 200:
            return []
        return _as_list(body)

    def reject_if_lead(self, customer: dict[str, Any]) -> None:
        if is_lead_status(customer):
            from .allowlist import GATE_LEAD_STATUS

            raise GateError(GATE_LEAD_STATUS)

    def patch_location_notes(self, snapshot: dict[str, Any], notes: str) -> dict[str, Any]:
        customer_id = snapshot["customer_id"]
        location_id = snapshot["location_id"]
        path = f"/customers/{customer_id}/service_locations/{location_id}"
        _assert_typed_path("PATCH", path)
        body = {
            "service_location": {
                "name": snapshot["name"],
                "tax_rate_id": snapshot["tax_rate_id"],
                "address_attributes": {
                    "id": snapshot["address_id"],
                    "notes": notes,
                },
            }
        }
        status, payload = self.transport.request("PATCH", path, body)
        if status >= 500:
            raise AmbiguousWriteError(f"remote_{status}")
        if status != 200:
            raise GateError("location_patch_rejected", status=status)
        return payload if isinstance(payload, dict) else {}

    def patch_work_order_notes(self, *_args: Any, **_kwargs: Any) -> None:
        raise GateError(GATE_LIVE_PATCH_UNTESTED)

    def create_work_order(self, *_args: Any, **_kwargs: Any) -> None:
        raise GateError(GATE_SCHEMA_UNVERIFIED)
