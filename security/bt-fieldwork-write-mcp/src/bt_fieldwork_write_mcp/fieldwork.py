"""Typed Fieldwork calls only. No generic HTTP passthrough. Key stays in memory."""

from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo
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
        raise GateError("read_shape_unverified")
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "work_orders", "results", "items", "customers"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if payload.get("id") is not None:
            return [payload]
    raise GateError("read_shape_unverified")


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
        "arrival_time_window_str": row.get("arrival_time_window_str"),
        "starts_at": row.get("starts_at"),
        "finished_at": row.get("finished_at") or row.get("ends_at"),
        "timezone": "America/New_York",
        "technician_id": row.get("technician_id"),
        "technician_id_means_unassigned": False,
        "service_route_ids": row.get("service_route_ids") if isinstance(row.get("service_route_ids"), list) else [],
        "service_routes": [
            {"id": route.get("id"), "name": route.get("name")}
            for route in row.get("service_routes") or []
            if isinstance(route, dict)
        ],
        "assignment": "service_routes and service_route_ids are the route metadata. A null technician_id was observed on routed work and is not treated as proof that nobody is assigned.",
        "starts_at_date": row.get("starts_at_date"),
        "starts_at_time": row.get("starts_at_time"),
        "ends_at": row.get("ends_at"),
        "duration": row.get("duration"),
        "status": row.get("status"),
        "specific": row.get("specific"),
        "locked": row.get("locked"),
        "confirmed": row.get("confirmed"),
        "instructions": row.get("instructions") if "instructions" in row else None,
        "private_notes": row.get("private_notes") if "private_notes" in row else None,
    }


def work_order_view(record: dict[str, Any]) -> dict[str, Any]:
    row = unwrap_occurrence(record)
    ids = occurrence_ids(record)
    for key in ("customer_name", "customer_display_name", "service_location_name", "service_location_address", "location_address", "location_city", "location_state", "location_zip", "location_note", "address", "name", "service_type", "notes", "unspecified"):
        if key in row:
            ids[key] = row[key]
    ids["promised_arrival_window"] = {
        "arrival_time_window": ids.get("arrival_time_window"),
        "arrival_time_window_start": ids.get("arrival_time_window_start"),
        "arrival_time_window_end": ids.get("arrival_time_window_end"),
        "arrival_time_window_str": ids.get("arrival_time_window_str"),
    }
    ids["start_finish"] = {"starts_at": ids.get("starts_at"), "finished_at": ids.get("finished_at")}
    return ids


def location_snapshot(customer: dict[str, Any], location: dict[str, Any]) -> dict[str, Any]:
    location = unwrap_service_location(location)
    address = location.get("address") if isinstance(location.get("address"), dict) else {}
    if not address and isinstance(location.get("address_attributes"), dict):
        address = location["address_attributes"]
    return {
        "customer_id": customer.get("id"),
        "customer_status": customer.get("customer_status") or customer.get("status") or customer.get("type"),
        "location_id": location.get("id"),
        "name": location.get("name"),
        "tax_rate_id": location.get("tax_rate_id"),
        "address_id": address.get("id"),
        "notes": address.get("notes") if "notes" in address else location.get("notes"),
    }


def _service_status(customer: dict[str, Any]) -> str:
    """One normalized status from present non-null status fields. Empty means unverified."""
    found: list[str] = []
    for key in ("status", "customer_status"):
        if key not in customer or customer[key] is None:
            continue
        text = str(customer[key]).strip().lower()
        if text:
            found.append(text)
    unique = set(found)
    if len(unique) != 1:
        raise GateError("customer_status_unverified")
    return unique.pop()


def _positive_id(value: Any) -> str | None:
    if isinstance(value, bool) or isinstance(value, float):
        return None
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, str) and value.strip().isdigit():
        text = str(int(value.strip()))
    else:
        return None
    if int(text) <= 0:
        return None
    return text


def _required_id(value: Any) -> str:
    result = _positive_id(value)
    if result is None:
        raise GateError("identity_mismatch")
    return result


def _local_schedule_match(row: dict[str, Any], filters: dict[str, Any]) -> bool:
    start = str(filters.get("start_date") or "")
    end = str(filters.get("end_date") or "")
    if start or end:
        raw = str(row.get("starts_at") or "")
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("offset_required")
            day = parsed.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        except ValueError:
            raw = str(row.get("starts_at_date") or "")
            try:
                day = date.fromisoformat(raw).isoformat()
            except ValueError:
                raise GateError("schedule_date_unverified") from None
        if (start and day < start) or (end and day > end):
            return False
    status = str(filters.get("status") or "")
    if status and str(row.get("status") or "").casefold() != status.casefold():
        return False
    requested = {str(item) for item in (filters.get("service_route_ids") or [])}
    if requested:
        found = {str(item) for item in (row.get("service_route_ids") or [])}
        for route in row.get("service_routes") or []:
            if isinstance(route, dict) and route.get("id") is not None:
                found.add(str(route.get("id")))
        if not requested & found:
            return False
    return True


def _schedule_query(filters: dict[str, Any], *, include_route_status: bool) -> dict[str, Any]:
    query: dict[str, Any] = {}
    for key in ("start_date", "end_date"):
        value = str(filters.get(key) or "")
        if value and (len(value) != 10 or value[4] != "-" or value[7] != "-" or not value.replace("-", "").isdigit()):
            raise GateError("unknown_field", fields=[key])
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                raise GateError("unknown_field", fields=[key]) from None
            query[key] = value
    if query.get("start_date") and query.get("end_date") and query["start_date"] > query["end_date"]:
        raise GateError("invalid_date_range")
    direction = str(filters.get("sort_direction") or "")
    if direction:
        if direction not in {"asc", "desc"}:
            raise GateError("unknown_field", fields=["sort_direction"])
        query["sort_direction"] = direction
    if "current_technician" in filters and filters["current_technician"] is not None:
        query["current_technician"] = bool(filters["current_technician"])
    if "work_pool" in filters and filters["work_pool"] is not None:
        query["work_pool"] = bool(filters["work_pool"])
    if include_route_status:
        status = filters.get("status")
        if status:
            query["filter[status]"] = str(status)
        routes = filters.get("service_route_ids") or []
        if routes:
            query["filter[service_routes_ids][]"] = [str(item) for item in routes]
    return query


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    return sha256_hex(canonical(snapshot))


class Transport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
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

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        if not self._key.present():
            raise GateError(GATE_AUTH_UNRESOLVED, reason="fieldwork_api_key_absent")
        clean = path
        _assert_typed_path(method.upper(), clean)
        params: list[tuple[str, str]] = [("api_key", self._key.get())]
        allowed = SEARCH_QUERY if clean == "/work_orders/search" else WORK_ORDER_QUERY if clean == "/work_orders" else CUSTOMER_SEARCH_QUERY if clean == "/customers/search" else frozenset({"page", "per_page"})
        for key, value in (query or {}).items():
            if key == "api_key" or key not in allowed or value is None or value == "":
                continue
            if isinstance(value, (list, tuple)):
                for item in value:
                    params.append((key, "true" if item is True else "false" if item is False else str(item)))
            else:
                params.append((key, "true" if value is True else "false" if value is False else str(value)))
        url = f"{self.api_base}{clean}?{urllib.parse.urlencode(params)}"
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


WORK_ORDER_QUERY = frozenset({
    "start_date",
    "end_date",
    "page",
    "per_page",
    "current_technician",
    "sort_direction",
    "work_pool",
    "filter[status]",
    "filter[service_routes_ids][]",
})
SEARCH_QUERY = frozenset({
    "start_date",
    "end_date",
    "page",
    "per_page",
    "current_technician",
    "sort_direction",
    "work_pool",
    "query",
})
CUSTOMER_SEARCH_QUERY = frozenset({"query", "page", "per_page"})
ALLOWED_QUERY = WORK_ORDER_QUERY | SEARCH_QUERY | CUSTOMER_SEARCH_QUERY


def _flatten(body: dict[str, Any], prefix: str = "") -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for key, value in body.items():
        name = f"{prefix}[{key}]" if prefix else str(key)
        if isinstance(value, dict):
            pairs.extend(_flatten(value, name))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    pairs.extend(_flatten(item, f"{name}[]"))
                else:
                    pairs.append((f"{name}[]", str(item)))
        elif value is not None:
            pairs.append((name, str(value)))
    return pairs


class FakeTransport:
    """In-process Fieldwork stand-in. Never talks to HQ."""

    def __init__(self) -> None:
        self.customers: dict[str, dict[str, Any]] = {}
        self.locations: dict[str, dict[str, Any]] = {}
        self.work_orders: dict[str, dict[str, Any]] = {}
        self.calls: list[dict[str, Any]] = []
        self.write_mode: str = "ok"  # ok | ambiguous | http_500 | drop
        self.readback_notes: str | None = None
        self.skip_work_order_persist: bool = False
        self.api_role = "readonly"

    def add_customer(self, customer: dict[str, Any], location: dict[str, Any]) -> None:
        cid = str(customer["id"])
        lid = str(location["id"])
        self.customers[cid] = customer
        location = dict(location)
        location["customer_id"] = customer["id"]
        self.locations[f"{cid}:{lid}"] = location

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        self.calls.append({"method": method, "path": path, "body": body, "query": query})
        if method in {"POST", "PATCH", "PUT", "DELETE"}:
            if self.write_mode == "ambiguous":
                raise AmbiguousWriteError("fake_ambiguous")
            if self.write_mode == "drop":
                raise AmbiguousWriteError("fake_drop")
            if self.write_mode == "http_500":
                raise AmbiguousWriteError("remote_500")
        if method == "GET" and path == "/profile":
            if self.api_role == "fail":
                return 500, {"error": "profile_down"}
            if self.api_role == "unknown":
                return 200, {"roles": ["mystery"]}
            roles = ["schedule", "work_orders"]
            if self.api_role == "readonly":
                roles.append("readonly")
            elif self.api_role == "writer":
                roles.append("writer")
            return 200, {"roles": roles}
        if method == "GET" and path == "/customers/search":
            return 200, list(self.customers.values())
        if method == "GET" and path == "/service_routes":
            return 200, []
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
                rows = list(self.work_orders.values())
                page = int((query or {}).get("page") or 1)
                per_page = int((query or {}).get("per_page") or len(rows) or 1)
                start = max(page - 1, 0) * per_page
                return 200, rows[start : start + per_page]
            wid = path.split("/")[2]
            wo = self.work_orders.get(str(wid))
            if wo is None:
                return 404, None
            return 200, {"appointment_occurrence": wo}
        if method == "PATCH" and _WORK_ORDER.match(path):
            appointment_id = path.split("/")[2]
            match = None
            match_key = None
            for key, wo in self.work_orders.items():
                if str(wo.get("service_appointment_id")) == appointment_id:
                    match = dict(wo)
                    match_key = key
                    break
            if match is None:
                return 404, None
            entries = ((body or {}).get("service_appointment") or {}).get("appointment_occurrences_attributes") or []
            if len(entries) != 1:
                return 422, {"error": "invalid_occurrence_contract"}
            occ = entries[0]
            if str(occ.get("id")) != str(match.get("id")):
                return 409, {"error": "identity_mismatch"}
            for field in ("instructions", "private_notes", "starts_at", "duration", "service_route_ids"):
                if field in occ:
                    match[field] = occ[field]
            if not self.skip_work_order_persist:
                self.work_orders[match_key] = match
            return 200, {"appointment_occurrence": match}
        if method == "POST" and path.startswith("/work_orders"):
            return 403, {"error": "schema_unverified"}
        return 404, None


def _assert_typed_path(method: str, path: str) -> None:
    if method == "GET" and path in {"/profile", "/service_routes", "/customers/search", "/customers"}:
        return
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
        return
    if method == "POST" and path == "/work_orders":
        raise GateError(GATE_SCHEMA_UNVERIFIED)
    raise GateError("unknown_operation", method=method, path=path)


def load_route_directory(path: str) -> dict[str, Any] | None:
    """Optional operator snapshot. Empty path means disabled. Not live staff data."""
    if not str(path or "").strip():
        return None
    import json
    from pathlib import Path

    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError("route_directory_unreadable") from exc
    if not isinstance(raw, dict) or not str(raw.get("source") or "").strip() or not str(raw.get("verified_at") or "").strip():
        raise GateError("route_directory_unreadable")
    routes = []
    for row in raw.get("routes") or []:
        if not isinstance(row, dict) or row.get("route_id") is None:
            continue
        routes.append({
            "route_id": str(row.get("route_id")),
            "name": row.get("name"),
            "user_id": None if row.get("user_id") is None else str(row.get("user_id")),
            "user_name": row.get("user_name"),
        })
    return {
        "kind": "configured_snapshot",
        "not_live_api_staff": True,
        "source": str(raw["source"]),
        "verified_at": str(raw["verified_at"]),
        "routes": routes,
    }


class TypedFieldworkClient:
    def __init__(self, transport: Transport, *, mapping_verified: bool = False, route_directory: dict[str, Any] | None = None) -> None:
        self.transport = transport
        self.mapping_verified = mapping_verified
        self.route_directory = route_directory
        self.auth_verified = False
        self.observed_api_role = "unknown"

    def api_key_present(self) -> bool:
        key = getattr(self.transport, "_key", None)
        return bool(key and key.present())

    def get_api_role(self) -> str:
        status, body = self.transport.request("GET", "/profile")
        if status != 200 or not isinstance(body, dict):
            raise GateError("fieldwork_api_auth_unresolved", status=status)
        roles = body.get("roles")
        if not isinstance(roles, list) or not roles or not all(isinstance(role, str) for role in roles):
            raise GateError("api_role_unverified")
        names = {role.lower() for role in roles}
        if "readonly" in names:
            observed = "readonly"
        elif "writer" in names:
            observed = "writer"
        else:
            raise GateError("api_role_unverified")
        self.auth_verified = True
        self.observed_api_role = observed
        return observed

    def get_customer(self, customer_id: str) -> dict[str, Any]:
        customer_id = _required_id(customer_id)
        status, body = self.transport.request("GET", f"/customers/{customer_id}")
        if status != 200 or not isinstance(body, dict):
            raise GateError("customer_not_found", status=status)
        if "customer" in body or "service_location" in body or "appointment_occurrence" in body:
            raise GateError("customer_shape_unverified")
        if _positive_id(body.get("id")) is None:
            raise GateError("customer_shape_unverified")
        return body

    def get_location(self, customer_id: str, location_id: str) -> dict[str, Any]:
        customer_id, location_id = _required_id(customer_id), _required_id(location_id)
        status, body = self.transport.request("GET", f"/customers/{customer_id}/service_locations/{location_id}")
        if status != 200 or not isinstance(body, dict) or "service_location" not in body:
            raise GateError("location_shape_unverified", status=status)
        return unwrap_service_location(body)

    def assert_location_identity(self, requested_customer: str, requested_location: str, customer: dict[str, Any], location: dict[str, Any]) -> None:
        customer_id = _positive_id(requested_customer)
        location_id = _positive_id(requested_location)
        body_customer = _positive_id(customer.get("id"))
        body_location = _positive_id(location.get("id"))
        body_owner = _positive_id(location.get("customer_id"))
        if not customer_id or not location_id or body_customer != customer_id or body_location != location_id or body_owner != body_customer:
            raise GateError("identity_mismatch")
        status = _service_status(customer)
        if status in {"lead", "leads"}:
            raise GateError("never_lead_status_accounts")
        if status == "inactive":
            raise GateError("customer_status_rejected")
        if status != "active":
            raise GateError("customer_status_unverified")
        address = location.get("address") if isinstance(location.get("address"), dict) else {}
        name = location.get("name")
        if not isinstance(name, str) or not name.strip() or _positive_id(location.get("tax_rate_id")) is None or _positive_id(address.get("id")) is None:
            raise GateError("identity_mismatch")

    def search_work_orders(self) -> list[dict[str, Any]]:
        status, body = self.transport.request("GET", "/work_orders/search")
        if status != 200:
            return []
        return _as_list(body)

    def _pages(self, path: str, query: dict[str, Any] | None = None, *, per_page: int = 100, max_pages: int = 20) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        page = 1
        while page <= max_pages:
            status, body = self.transport.request("GET", path, query={**(query or {}), "page": page, "per_page": per_page})
            if status != 200:
                raise GateError("read_rejected", status=status, path=path.split("?", 1)[0])
            batch = _as_list(body)
            rows.extend(batch)
            if len(batch) < per_page:
                return {"items": rows, "complete": True, "truncated": False, "pages_read": page, "per_page": per_page}
            page += 1
        return {"items": rows, "complete": False, "truncated": True, "pages_read": max_pages, "per_page": per_page}

    def search_customers(self, query: str) -> dict[str, Any]:
        if not str(query or "").strip():
            raise GateError("unknown_field")
        return self._pages("/customers/search", {"query": query})

    def list_service_routes(self) -> dict[str, Any]:
        result = self._pages("/service_routes")
        return {**result, "ok": True, "empty_directory_is_not_no_staff": True,
                "route_names_on": "work_order.service_routes", "configured_snapshot": self.route_directory}

    def list_work_orders(self, **filters: Any) -> dict[str, Any]:
        technician = str(filters.pop("technician", "") or "").strip()
        resolved_from = None
        if technician:
            if not self.route_directory:
                raise GateError("route_directory_not_configured")
            wanted = technician.casefold()
            ids = [
                row["route_id"]
                for row in self.route_directory["routes"]
                if wanted in {str(row.get("user_id") or "").casefold(), str(row.get("user_name") or "").casefold()}
            ]
            if not ids:
                raise GateError("route_directory_unmatched")
            filters["service_route_ids"] = ids
            resolved_from = "configured_snapshot"
        query = _schedule_query(filters, include_route_status=True)
        per_page = int(filters.pop("per_page", 100) or 100)
        max_pages = int(filters.pop("max_pages", 20) or 20)
        matched: list[dict[str, Any]] = []
        page = int(filters.pop("page", 1) or 1)
        if not 1 <= per_page <= 100 or not 1 <= max_pages <= 20 or page < 1:
            raise GateError("invalid_pagination")
        final_page = page + max_pages - 1
        pages_read = 0
        complete = False
        while page <= final_page:
            status, body = self.transport.request("GET", "/work_orders", query={**query, "page": page, "per_page": per_page})
            if status != 200:
                raise GateError("read_rejected", status=status, path="/work_orders")
            batch = _as_list(body)
            pages_read = page
            matched.extend(item for item in batch if _local_schedule_match(item, filters))
            if len(batch) < per_page:
                complete = True
                break
            page += 1
        matched.sort(key=lambda row: str(row.get("starts_at") or ""), reverse=filters.get("sort_direction") == "desc")
        by_route = {row["route_id"]: row for row in (self.route_directory or {}).get("routes", [])}
        items = []
        for item in matched:
            view = work_order_view(item)
            route_ids = {str(route) for route in view.get("service_route_ids") or []}
            snapshot = next((by_route[route] for route in route_ids if route in by_route), None)
            if snapshot is not None:
                view["configured_route_assignee"] = {**snapshot, "kind": "configured_snapshot", "not_live_api_staff": True}
            items.append(view)
        return {
            "items": items,
            "technician_resolved_from": resolved_from,
            "complete": complete,
            "truncated": not complete,
            "pages_read": pages_read,
            "next_page": None if complete else pages_read + 1,
            "per_page": per_page,
            "server_side_filtering": False,
            "local_filter": [name for name, present in (("date", filters.get("start_date") or filters.get("end_date")), ("status", filters.get("status")), ("service_route_ids", filters.get("service_route_ids"))) if present],
            "upstream_route_filter_observed_ignored": True,
            "timezone": "America/New_York",
        }

    def search_work_orders_filtered(self, **filters: Any) -> dict[str, Any]:
        query = _schedule_query(filters, include_route_status=False)
        if filters.get("text"):
            query["query"] = str(filters["text"])
        found = self._pages("/work_orders/search", query)
        found["items"] = [work_order_view(item) for item in found["items"]]
        found["filters_applied"] = sorted(query)
        found["route_and_status_filters"] = "not_sent_on_search"
        return found

    def get_work_order(self, work_order_id: str) -> dict[str, Any]:
        work_order_id = _required_id(work_order_id)
        status, body = self.transport.request("GET", f"/work_orders/{work_order_id}")
        if status != 200 or not isinstance(body, dict) or "appointment_occurrence" not in body:
            raise GateError("work_order_shape_unverified", status=status)
        return unwrap_occurrence(body)

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

    def patch_work_order_fields(self, before: dict[str, Any], after: dict[str, Any], fields: Any) -> dict[str, Any]:
        allowed = {"instructions", "private_notes", "starts_at", "duration", "service_route_ids"}
        if not fields or set(fields) - allowed:
            raise GateError("unknown_field")
        path = f"/work_orders/{_required_id(before['service_appointment_id'])}"
        occurrence = {"id": _required_id(before["work_order_id"])}
        occurrence.update({field: after[field] for field in fields})
        body = {"service_appointment": {"appointment_occurrences_attributes": [occurrence]}}
        status, payload = self.transport.request("PATCH", path, body)
        if status >= 500:
            raise AmbiguousWriteError(f"remote_{status}")
        if status != 200:
            raise GateError("work_order_patch_rejected", status=status)
        return payload if isinstance(payload, dict) else {}

    def patch_work_order_notes(self, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        fields = [key for key in ("instructions", "private_notes") if after.get(key) != before.get(key)]
        return self.patch_work_order_fields(before, after, fields)

    def create_work_order(self, *_args: Any, **_kwargs: Any) -> None:
        raise GateError(GATE_SCHEMA_UNVERIFIED)
