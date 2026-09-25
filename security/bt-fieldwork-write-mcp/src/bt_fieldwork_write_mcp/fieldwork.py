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
    is_lead_status,
)
from .config import API_BASE
from .digest import canonical, sha256_hex
from .errors import AmbiguousWriteError, GateError
from .secrets import InMemoryApiKey

_CUSTOMER = re.compile(r"^/customers/\d+$")
_LOCATION = re.compile(r"^/customers/\d+/service_locations/\d+$")
_LOCATION_LIST = re.compile(r"^/customers/\d+/service_locations$")
_CONTACT_LIST = re.compile(r"^/customers/\d+/contacts$")
_TEMPLATE = re.compile(r"^/work_order_templates/\d+$")
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
        if clean == "/work_orders/search":
            allowed = SEARCH_QUERY
        elif clean == "/work_orders":
            allowed = WORK_ORDER_QUERY
        elif clean == "/customers/search":
            allowed = CUSTOMER_SEARCH_QUERY
        elif clean == "/customers/search_by_phone":
            allowed = PHONE_SEARCH_QUERY
        elif _LOCATION_LIST.match(clean):
            allowed = LOCATION_LIST_QUERY
        elif clean == "/users":
            allowed = frozenset()
        else:
            allowed = frozenset({"page", "per_page"})
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
                content_type = resp.headers.get("Content-Type", "") if getattr(resp, "headers", None) else ""
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
            raw = exc.read() if status < 500 else b""
            if sent and status >= 500:
                self._note_write(status=status, content_type=content_type, parser_stage="http_5xx", body=None)
                raise AmbiguousWriteError(f"remote_{status}", diagnostic=self.last_write_diagnostic) from None
            if status in {301, 302, 303, 307, 308}:
                raise GateError("redirect_rejected", status=status) from None
            parsed = self._parse_body(raw, status=status, content_type=content_type, sent=sent)
            return status, parsed
        except AmbiguousWriteError:
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            if sent:
                self._note_write(status="unknown", content_type="unknown", parser_stage="transport_drop", body=None)
                raise AmbiguousWriteError("transport_drop_after_send", diagnostic=self.last_write_diagnostic) from None
            raise GateError("transport_error") from None
        if not raw:
            self._note_write(status=status, content_type=content_type, parser_stage="empty_body", body=None)
            return status, None
        parsed = self._parse_body(raw, status=status, content_type=content_type, sent=sent)
        return status, parsed

    def _note_write(self, *, status: Any, content_type: str, parser_stage: str, body: Any) -> None:
        keys: list[str] = []
        if isinstance(body, dict):
            keys = sorted(str(key) for key in body)[:40]
        self.last_write_diagnostic = {
            "status": status,
            "content_type": (content_type or "unknown").split(";")[0].strip() or "unknown",
            "top_level_keys": keys,
            "parser_stage": parser_stage,
            "response_body_retained": False,
        }

    def _parse_body(self, raw: bytes, *, status: int, content_type: str, sent: bool) -> Any:
        try:
            parsed = json.loads(raw.decode("utf-8")) if raw else None
        except (json.JSONDecodeError, UnicodeError):
            if sent:
                self._note_write(status=status, content_type=content_type, parser_stage="unreadable_json", body=None)
                raise AmbiguousWriteError("unreadable_write_response", diagnostic=self.last_write_diagnostic) from None
            raise GateError("unreadable_response") from None
        stage = "json_object" if isinstance(parsed, dict) else "json_non_object" if parsed is not None else "empty_body"
        self._note_write(status=status, content_type=content_type, parser_stage=stage, body=parsed)
        return parsed


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
CUSTOMER_SEARCH_QUERY = frozenset({
    "query",
    "filter[customer_status]",
    "filter[date_added]",
    "filter[postal_code]",
    "start_date",
    "end_date",
    "page",
    "per_page",
})
PHONE_SEARCH_QUERY = frozenset({"phone", "as_object"})
LOCATION_LIST_QUERY = frozenset({"page", "per_page", "filter[phone]", "filter[updated_after]"})
ALLOWED_QUERY = WORK_ORDER_QUERY | SEARCH_QUERY | CUSTOMER_SEARCH_QUERY | PHONE_SEARCH_QUERY | LOCATION_LIST_QUERY


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

    is_fake_double = True

    def __init__(self) -> None:
        self.customers: dict[str, dict[str, Any]] = {}
        self.locations: dict[str, dict[str, Any]] = {}
        self.work_orders: dict[str, dict[str, Any]] = {}
        self.calls: list[dict[str, Any]] = []
        self.write_mode: str = "ok"  # ok | ambiguous | http_500 | drop
        self.readback_notes: str | None = None
        self.skip_work_order_persist: bool = False
        self.api_role = "readonly"
        self.users: list[dict[str, Any]] | None = None
        self.fail_work_order_page: int | None = None
        self.repeat_work_order_page: bool = False
        self.return_create_id = True
        self._next_id = 900000
        self.customer_search_fault: str | None = None
        self.fail_write_exact: set[str] = set()
        self.fail_write_suffixes: set[str] = set()
        self.raise_after_exact: set[str] = set()
        self.contacts: dict[str, dict[str, Any]] = {}
        self.services = [_catalog_service()]
        self.templates = [_catalog_template()]
        self.readback_line_price = None

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
            if self.write_mode == "ambiguous" or path in self.fail_write_exact or any(path.endswith(suffix) for suffix in self.fail_write_suffixes):
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
            if self.api_role == "readonly":
                return 200, {"roles": [*LIVE_PERMISSION_ROLES, "readonly"]}
            if self.api_role == "writer":
                return 200, {"roles": list(LIVE_PERMISSION_ROLES)}
            return 200, {"roles": ["mystery"]}
        if method == "GET" and path == "/customers/search":
            return self._fake_customer_search(query)
        if method == "GET" and path == "/work_order_templates":
            return 200, [{"id": row["id"], "name": row["name"]} for row in self.templates]
        if method == "GET" and path.startswith("/work_order_templates/"):
            wanted = path.rsplit("/", 1)[-1]
            for row in self.templates:
                if str(row["id"]) == wanted:
                    return 200, {"service_appointment_template": row}
            return 404, None
        if method == "GET" and path == "/services":
            return 200, list(self.services)
        if method == "GET" and path == "/customers/search_by_phone":
            phone = str((query or {}).get("phone") or "")
            found = [row for row in self.customers.values() if phone and phone in json.dumps(row)]
            return 200, {"data": found}
        if method == "GET" and path == "/users":
            if self.users is None:
                return 503, {"error": "users_unavailable"}
            return 200, self.users
        if method == "GET" and path == "/service_routes":
            return 200, []
        if method == "GET" and _LOCATION_LIST.match(path):
            cid = path.split("/")[2]
            rows = [row for row in self.locations.values() if str(row.get("customer_id")) == cid]
            page = int((query or {}).get("page") or 1)
            per_page = int((query or {}).get("per_page") or len(rows) or 1)
            start = max(page - 1, 0) * per_page
            return 200, rows[start : start + per_page]
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
            for field in ("attention", "street", "street2", "city", "state", "zip", "county", "phone", "phone_ext", "phone_note", "phone_kind", "notes"):
                if field in addr:
                    address[field] = addr[field]
            location["address"] = address
            self.locations[key] = location
            return 200, {"service_location": location}
        if method == "GET" and (_WORK_ORDER.match(path) or _WORK_ORDER_PLAIN.match(path) or _WORK_ORDER_SEARCH.match(path)):
            if "/search" in path or path == "/work_orders":
                page = int((query or {}).get("page") or 1)
                if self.fail_work_order_page is not None and page == self.fail_work_order_page:
                    return 500, {"error": "page_failed"}
                rows = list(self.work_orders.values())
                per_page = int((query or {}).get("per_page") or len(rows) or 1)
                if self.repeat_work_order_page and page > 1:
                    page = 1
                start = max(page - 1, 0) * per_page
                return 200, rows[start : start + per_page]
            wid = path.split("/")[2]
            wo = self.work_orders.get(str(wid))
            if wo is None:
                return 404, None
            view = dict(wo)
            if self.readback_line_price is not None and view.get("line_items"):
                view["line_items"] = [dict(item) for item in view["line_items"]]
                view["line_items"][0]["price"] = self.readback_line_price
            return 200, {"appointment_occurrence": view}
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
            if "starts_at" in occ or "duration" in occ:
                from .schedule import apply_fixed_window_double

                apply_fixed_window_double(match)
            if not self.skip_work_order_persist:
                self.work_orders[match_key] = match
            if self.write_mode == "timeout_after_apply":
                self.write_mode = "ok"
                raise AmbiguousWriteError("timeout_after_apply")
            return 200, {"appointment_occurrence": match}
        if method == "GET" and _CONTACT_LIST.match(path):
            cid = path.split("/")[2]
            rows = [row for key, row in self.contacts.items() if key.startswith(f"{cid}:")]
            return 200, rows
        if method == "POST" and _CONTACT_LIST.match(path):
            return self._finish_write(path, self._fake_contact(path, body))
        if method == "POST" and _LOCATION_LIST.match(path):
            return self._finish_write(path, self._fake_location_create(path, body))
        if method == "POST" and path == "/customers":
            return self._finish_write(path, self._fake_customer(body))
        if method == "POST" and path == "/work_orders":
            return self._finish_write(path, self._fake_work_order(body))
        return 404, None

    def _finish_write(self, path: str, response: tuple[int, dict[str, Any]]) -> tuple[int, dict[str, Any]]:
        if path in self.raise_after_exact:
            raise AmbiguousWriteError("timeout_after_apply")
        return response

    def _fake_customer_search(self, query: dict[str, Any] | None) -> tuple[int, Any]:
        if self.customer_search_fault == "error":
            return 500, {"error": "search_failed"}
        page = int((query or {}).get("page") or 1)
        per_page = int((query or {}).get("per_page") or 100)
        rows = list(self.customers.values())
        if self.customer_search_fault == "repeat" and page > 1:
            page = 1
        if self.customer_search_fault == "incomplete":
            seed = rows or [{"id": 1, "name": "pad"}]
            return 200, [seed[index % len(seed)] for index in range(per_page)]
        start = max(page - 1, 0) * per_page
        return 200, rows[start : start + per_page]

    def _fake_customer(self, body: dict[str, Any] | None) -> tuple[int, dict[str, Any]]:
        customer = (body or {}).get("customer") if isinstance(body, dict) else {}
        if not isinstance(customer, dict):
            customer = {}
        created = self._new_id()
        location_id = self._new_id()
        nested = (customer.get("service_locations_attributes") or [{}])[0]
        if not isinstance(nested, dict):
            nested = {}
        display = customer.get("name") or " ".join(part for part in (customer.get("first_name"), customer.get("last_name")) if part) or customer.get("last_name")
        self.customers[str(created)] = {
            "id": created,
            "name": display,
            "customer_status": customer.get("status") or "active",
            "email": None,
            **{key: value for key, value in customer.items() if key != "service_locations_attributes"},
            "status": customer.get("status") or "active",
            "billing_address": {
                "street": customer.get("billing_street"),
                "street2": customer.get("billing_street2"),
                "city": customer.get("billing_city"),
                "state": customer.get("billing_state"),
                "zip": customer.get("billing_zip"),
                "county": customer.get("billing_county"),
            },
        }
        self.locations[f"{created}:{location_id}"] = {
            "id": location_id,
            "customer_id": created,
            "name": nested.get("name"),
            "same_as_billing_address": nested.get("same_as_billing_address"),
            "address": {"id": self._new_id()},
        }
        response: dict[str, Any] = {"echo": body, "test_double": True, "response_schema": "fake_test_double_not_live_schema"}
        if self.return_create_id:
            response["id"] = created
        return 200, response

    def _fake_contact(self, path: str, body: dict[str, Any] | None) -> tuple[int, dict[str, Any]]:
        cid = path.split("/")[2]
        contact = (body or {}).get("contact") if isinstance(body, dict) else {}
        created = self._new_id()
        stored = {"id": created, "customer_id": int(cid), **(contact if isinstance(contact, dict) else {})}
        self.contacts[f"{cid}:{created}"] = stored
        if cid in self.customers:
            self.customers[cid]["email"] = stored.get("email")
        response: dict[str, Any] = {"echo": body, "test_double": True, "response_schema": "fake_test_double_not_live_schema"}
        if self.return_create_id:
            response["id"] = created
        return 200, response

    def _fake_location_create(self, path: str, body: dict[str, Any] | None) -> tuple[int, dict[str, Any]]:
        cid = path.split("/")[2]
        location = (body or {}).get("service_location") if isinstance(body, dict) else {}
        created = self._new_id()
        stored = {
            "id": created,
            "customer_id": int(cid),
            "name": (location or {}).get("name"),
            "tax_rate_id": (location or {}).get("tax_rate_id"),
            "address": {"id": self._new_id(), **(((location or {}).get("address_attributes")) or {})},
        }
        self.locations[f"{cid}:{created}"] = stored
        response: dict[str, Any] = {"echo": body, "test_double": True, "response_schema": "fake_test_double_not_live_schema"}
        if self.return_create_id:
            response["id"] = created
        return 200, response

    def _fake_work_order(self, body: dict[str, Any] | None) -> tuple[int, dict[str, Any]]:
        appointment = (body or {}).get("service_appointment") if isinstance(body, dict) else {}
        if not isinstance(appointment, dict):
            appointment = {}
        occurrence_id = self._new_id()
        appointment_id = self._new_id()
        occ = (appointment.get("appointment_occurrences_attributes") or [{}])[0]
        if not isinstance(occ, dict):
            occ = {}
        lines = appointment.get("line_items_attributes") or []
        stored = {
            "id": occurrence_id,
            "service_appointment_id": appointment_id,
            "customer_id": appointment.get("customer_id"),
            "service_location_id": appointment.get("service_location_id"),
            "repeat_type": appointment.get("repeat_type"),
            "repeat_period": appointment.get("repeat_period"),
            "starts_at": occ.get("starts_at"),
            "starts_at_date": occ.get("starts_at"),
            "duration": occ.get("duration"),
            "instructions": occ.get("instructions"),
            "production_value": occ.get("production_value"),
            "service_route_ids": list(occ.get("service_route_ids") or []),
            "line_items": lines,
            "status": "scheduled",
        }
        self.work_orders[str(occurrence_id)] = stored
        response: dict[str, Any] = {
            "echo": body,
            "test_double": True,
            "response_schema": "fake_test_double_not_live_schema",
            "appointment_occurrence": {"id": occurrence_id, "service_appointment_id": appointment_id},
        }
        if self.return_create_id:
            response["id"] = occurrence_id
            response["service_appointment_id"] = appointment_id
        return 200, response

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

def _assert_typed_path(method: str, path: str) -> None:
    if method == "GET" and path in {"/profile", "/service_routes", "/customers/search", "/customers/search_by_phone", "/customers", "/users", "/work_order_templates", "/services"}:
        return
    if method == "GET" and (
        _CUSTOMER.match(path)
        or _LOCATION.match(path)
        or _LOCATION_LIST.match(path)
        or _CONTACT_LIST.match(path)
        or _TEMPLATE.match(path)
        or _WORK_ORDER.match(path)
        or _WORK_ORDER_PLAIN.match(path)
        or _WORK_ORDER_SEARCH.match(path)
    ):
        return
    if method == "PATCH" and _LOCATION.match(path):
        return
    if method == "PATCH" and _WORK_ORDER.match(path):
        return
    if method == "POST" and path in {"/work_orders", "/customers"}:
        return
    if method == "POST" and (_LOCATION_LIST.match(path) or _CONTACT_LIST.match(path)):
        return
    raise GateError("unknown_operation", method=method, path=path)


def _catalog_service() -> dict[str, Any]:
    """Fake catalog row. Label is description. Not a live schema and not a branch default."""
    return {"id": 38814, "description": "PestGuard - Set-up", "price": "150.0"}


def _catalog_template() -> dict[str, Any]:
    """Observed GET shape. Defaults live under work_order. Money values are strings."""
    return {
        "id": 8835901,
        "name": "PestGuard - Initial 2026",
        "repeat_type": "none",
        "repeat_period": 1,
        "billing_frequency": 0,
        "discount": "0.0",
        "tax_amount": "0.0",
        "line_items": [{
            "id": 105539222,
            "payable_id": 38814,
            "payable_type": "Service",
            "type": "service",
            "name": "PestGuard - Set-up",
            "quantity": "1.0",
            "price": "150.0",
            "total": "150.0",
            "taxable": False,
            "details": "",
        }],
        "work_order": {
            "duration": 60,
            "instructions": "",
            "production_value": "150.0",
            "specific": True,
            "callback": False,
        },
    }


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


# Verified by a live read-only GET /profile. These names are permissions, not a literal writer role.
LIVE_PERMISSION_ROLES = ("schedule", "customers", "invoicing", "reporting", "agreements", "tasks", "work_orders")
_KNOWN_PERMISSION_ROLES = frozenset(LIVE_PERMISSION_ROLES)


_WORK_ORDER_FILTERS = frozenset({
    "technician", "start_date", "end_date", "current_technician", "sort_direction", "work_pool",
    "status", "service_route_ids", "page", "per_page", "max_pages", "customer_id", "service_location_id",
})
_CUSTOMER_FILTERS = frozenset({
    "customer_status", "name", "phone", "postal_code", "billing_postal_code", "date_added",
    "start_date", "end_date", "page", "per_page", "include_details",
})
_SECRET_MARKERS = ("stripe", "card", "cvv", "pan", "secret", "password", "token", "api_key", "account_number")
_CUSTOMER_DETAIL_KEYS = (
    "id", "name", "first_name", "last_name", "customer_status", "status", "balance", "terms", "tags",
    "contacts", "service_locations", "locations", "billing_address", "email", "phone", "phones", "date_added",
)
_LOCATION_KEYS = ("id", "customer_id", "name", "email", "tax_rate_id", "service_route_id", "address")
_ADDRESS_KEYS = ("id", "street", "street2", "city", "state", "zip", "county", "notes", "phone")
_USER_KEYS = ("id", "first_name", "last_name", "email", "phone_number", "is_technician", "is_admin", "job_title", "service_route_id", "service_route_name")
_BRANCH_KEYS = ("id", "name", "company_name", "address", "time_zone")


def _secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in _SECRET_MARKERS)


def _project_customer(row: dict[str, Any], *, include_details: bool) -> dict[str, Any]:
    keys = _CUSTOMER_DETAIL_KEYS if include_details else ("id", "name", "customer_status", "status")
    projected = {key: row[key] for key in keys if key in row and not _secret_key(key)}
    billing = row.get("billing_address")
    if include_details and isinstance(billing, dict):
        projected["billing_address"] = {key: billing[key] for key in ("street", "city", "state", "zip", "postal_code") if key in billing and not _secret_key(key)}
    return projected


def _project_location(row: dict[str, Any]) -> dict[str, Any]:
    projected = {key: row[key] for key in _LOCATION_KEYS if key in row and key != "address"}
    address = row.get("address") if isinstance(row.get("address"), dict) else {}
    if address:
        projected["address"] = {key: address[key] for key in _ADDRESS_KEYS if key in address}
    return projected


def _project_user(row: dict[str, Any]) -> dict[str, Any]:
    projected = {key: row[key] for key in _USER_KEYS if key in row}
    branches = []
    for branch in row.get("branches") or []:
        if isinstance(branch, dict):
            branches.append({key: branch[key] for key in _BRANCH_KEYS if key in branch and not _secret_key(key)})
    projected["branches"] = branches
    return projected


def _try_users(client: "TypedFieldworkClient") -> list[dict[str, Any]] | None:
    try:
        status, body = client.transport.request("GET", "/users")
    except Exception:
        return None
    if status != 200:
        return None
    return [_project_user(row) for row in _as_list(body)]


def _route_directory_from_users(users: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    unassigned = []
    for user in users:
        route_id = user.get("service_route_id")
        if route_id is None or str(route_id) == "-1":
            unassigned.append(user)
            continue
        grouped.setdefault(str(route_id), []).append(user)
    routes = []
    for route_id, staff in grouped.items():
        names = {person.get("service_route_name") for person in staff}
        routes.append({
            "route_id": route_id,
            "service_route_name": next(iter(names)) if len(names) == 1 else None,
            "staff": staff,
            "assignee": None,
            "ambiguous": len(staff) > 1,
            "source": "live_user_directory",
        })
    return {"source": "live_user_directory", "routes": routes, "unassigned": unassigned}


def _routes_for_person(directory: dict[str, Any], technician: str) -> list[str]:
    wanted = technician.casefold()
    found = []
    for route in directory["routes"]:
        for person in route["staff"]:
            full = " ".join(str(person.get(key) or "") for key in ("first_name", "last_name")).strip().casefold()
            if wanted in {full, str(person.get("id") or "").casefold()}:
                found.append(route["route_id"])
    return list(dict.fromkeys(found))


def search_customers_typed(client: "TypedFieldworkClient", query: str = "", **filters: Any) -> dict[str, Any]:
    unknown = sorted(set(filters) - _CUSTOMER_FILTERS)
    if unknown:
        raise GateError("unsupported_filter", fields=unknown)
    phone = str(filters.get("phone") or "")
    include_details = bool(filters.get("include_details"))
    page = filters.get("page")
    per_page = int(filters.get("per_page") or 100)
    if not 1 <= per_page <= 100 or (page is not None and int(page) < 1):
        raise GateError("invalid_pagination")
    if phone and (str(query or "").strip() or any(filters.get(key) for key in ("customer_status", "postal_code", "billing_postal_code", "date_added", "start_date", "end_date", "page"))):
        raise GateError("unsupported_filter", fields=["phone_with_search_filters"])
    if phone:
        status, body = client.transport.request("GET", "/customers/search_by_phone", query={"phone": phone, "as_object": True})
        if status != 200:
            raise GateError("read_rejected", status=status, path="/customers/search_by_phone")
        rows = _as_list(body)
        found = {"items": rows, "complete": True, "truncated": False, "pages_read": 1, "per_page": None, "endpoint": "/customers/search_by_phone"}
    else:
        if not str(query or "").strip() and not str(filters.get("name") or "").strip() and not any(filters.get(key) for key in ("customer_status", "postal_code", "billing_postal_code", "date_added", "start_date", "end_date")):
            raise GateError("unknown_field")
        upstream: dict[str, Any] = {}
        if str(query or "").strip():
            upstream["query"] = str(query)
        if filters.get("customer_status"):
            upstream["filter[customer_status]"] = str(filters["customer_status"])
        postal = filters.get("billing_postal_code") or filters.get("postal_code")
        if postal:
            upstream["filter[postal_code]"] = str(postal)
        if filters.get("date_added"):
            upstream["filter[date_added]"] = str(filters["date_added"])
        for key in ("start_date", "end_date"):
            if filters.get(key):
                upstream[key] = str(filters[key])
        if page is None:
            found = client._pages("/customers/search", upstream, per_page=per_page)
        else:
            status, body = client.transport.request("GET", "/customers/search", query={**upstream, "page": int(page), "per_page": per_page})
            if status != 200:
                raise GateError("read_rejected", status=status, path="/customers/search")
            rows = _as_list(body)
            short = len(rows) < per_page
            found = {"items": rows, "complete": short, "truncated": not short, "pages_read": 1, "per_page": per_page, "next_page": None if short else int(page) + 1}
        found["endpoint"] = "/customers/search"
        found["date_range_semantics"] = "start_date_and_end_date_are_documented_labels_not_verified_as_created"
        found["postal_code_scope"] = "documented_as_postal_code_not_billing_specific"
        found["date_added_is_single_day"] = True
    name = str(filters.get("name") or "").strip().casefold()
    if name:
        found["items"] = [row for row in found["items"] if name in str(row.get("name") or "").casefold()]
        found["name_filter"] = "local_only"
        if found.get("truncated"):
            found["complete"] = False
    found["items"] = [_project_customer(row, include_details=include_details) for row in found["items"]]
    found["include_details"] = include_details
    return found


def list_service_locations_typed(client: "TypedFieldworkClient", customer_id: str, **filters: Any) -> dict[str, Any]:
    unknown = sorted(set(filters) - {"page", "per_page", "phone", "updated_after"})
    if unknown:
        raise GateError("unsupported_filter", fields=unknown)
    customer_id = _required_id(customer_id)
    per_page = int(filters.get("per_page") or 100)
    page = int(filters.get("page") or 1)
    if not 1 <= per_page <= 100 or page < 1:
        raise GateError("invalid_pagination")
    query: dict[str, Any] = {"page": page, "per_page": per_page}
    if filters.get("phone"):
        query["filter[phone]"] = str(filters["phone"])
    if filters.get("updated_after"):
        query["filter[updated_after]"] = str(filters["updated_after"])
    status, body = client.transport.request("GET", f"/customers/{customer_id}/service_locations", query=query)
    if status != 200:
        raise GateError("read_rejected", status=status, path="/customers/{customer_id}/service_locations")
    rows = []
    for row in _as_list(body):
        owner = row.get("customer_id")
        if owner is not None and str(owner) != customer_id:
            continue
        rows.append(_project_location(row))
    short = len(_as_list(body)) < per_page
    return {
        "items": rows,
        "customer_id": customer_id,
        "customer_required": True,
        "global_endpoint": False,
        "complete": short,
        "truncated": not short,
        "next_page": None if short else page + 1,
        "page": page,
        "per_page": per_page,
        "unsupported_filters": ["query", "active", "branch"],
    }


def list_users_typed(client: "TypedFieldworkClient") -> dict[str, Any]:
    status, body = client.transport.request("GET", "/users")
    if status != 200:
        raise GateError("read_rejected", status=status, path="/users")
    users = [_project_user(row) for row in _as_list(body)]
    return {"ok": True, "items": users, "count": len(users), "directory": _route_directory_from_users(users), "projection": list(_USER_KEYS) + ["branches"]}


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
        elif names & _KNOWN_PERMISSION_ROLES:
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
        pages_read = 0
        seen: list[tuple[str, ...]] = []
        while page <= max_pages:
            try:
                status, body = self.transport.request("GET", path, query={**(query or {}), "page": page, "per_page": per_page})
            except Exception:
                if pages_read == 0:
                    raise
                return {"items": rows, "complete": False, "truncated": True, "pages_read": pages_read, "per_page": per_page, "next_page": page, "partial_error": {"page": page}, "repeated_page": False}
            if status != 200:
                if pages_read == 0:
                    raise GateError("read_rejected", status=status, path=path.split("?", 1)[0])
                return {"items": rows, "complete": False, "truncated": True, "pages_read": pages_read, "per_page": per_page, "next_page": page, "partial_error": {"status": status, "page": page}, "repeated_page": False}
            batch = _as_list(body)
            signature = tuple(str(item.get("id")) for item in batch)
            if signature in seen:
                return {"items": rows, "complete": False, "truncated": True, "pages_read": pages_read, "per_page": per_page, "next_page": None, "repeated_page": True}
            seen.append(signature)
            pages_read += 1
            rows.extend(batch)
            if len(batch) < per_page:
                return {"items": rows, "complete": True, "truncated": False, "pages_read": pages_read, "per_page": per_page, "next_page": None, "repeated_page": False}
            page += 1
        return {"items": rows, "complete": False, "truncated": True, "pages_read": pages_read, "per_page": per_page, "next_page": page, "repeated_page": False}

    def search_customers(self, query: str = "", **filters: Any) -> dict[str, Any]:
        return search_customers_typed(self, query, **filters)

    def list_service_locations(self, customer_id: str, **filters: Any) -> dict[str, Any]:
        return list_service_locations_typed(self, customer_id, **filters)

    def list_users(self) -> dict[str, Any]:
        return list_users_typed(self)

    def list_service_routes(self) -> dict[str, Any]:
        result = self._pages("/service_routes")
        users = _try_users(self)
        body = {**result, "ok": True, "empty_directory_is_not_no_staff": True,
                "route_names_on": "work_order.service_routes", "configured_snapshot": self.route_directory}
        if users is None:
            body["directory_source"] = "configured_snapshot" if self.route_directory else "service_routes_only"
            body["live_user_directory"] = None
            body["fallback_reason"] = "live_users_unavailable"
        else:
            body["live_user_directory"] = _route_directory_from_users(users)
            body["directory_source"] = "live_user_directory" if not result["items"] else "service_routes"
            body["fallback_reason"] = None
        return body

    def list_work_orders(self, **filters: Any) -> dict[str, Any]:
        unknown = sorted(set(filters) - _WORK_ORDER_FILTERS)
        if unknown:
            raise GateError("unsupported_filter", fields=unknown)
        _schedule_query(filters, include_route_status=True)
        technician = str(filters.pop("technician", "") or "").strip()
        users = _try_users(self)
        directory = _route_directory_from_users(users) if users is not None else None
        resolved_from = None
        fallback_reason = None
        if technician:
            if directory is not None:
                ids = _routes_for_person(directory, technician)
                resolved_from = "live_user_directory"
            else:
                if not self.route_directory:
                    raise GateError("route_directory_not_configured")
                wanted = technician.casefold()
                ids = [
                    row["route_id"]
                    for row in self.route_directory["routes"]
                    if wanted in {str(row.get("user_id") or "").casefold(), str(row.get("user_name") or "").casefold()}
                ]
                resolved_from = "configured_snapshot"
                fallback_reason = "live_users_unavailable"
            if not ids:
                raise GateError("route_directory_unmatched")
            filters["service_route_ids"] = ids
        query = _schedule_query(filters, include_route_status=True)
        per_page = int(filters.pop("per_page", 100) or 100)
        max_pages = int(filters.pop("max_pages", 20) or 20)
        customer_id = str(filters.pop("customer_id", "") or "")
        location_id = str(filters.pop("service_location_id", "") or "")
        matched: list[dict[str, Any]] = []
        page = int(filters.pop("page", 1) or 1)
        if not 1 <= per_page <= 100 or not 1 <= max_pages <= 20 or page < 1:
            raise GateError("invalid_pagination")
        final_page = page + max_pages - 1
        pages_read = 0
        last_page = page - 1
        scanned = 0
        complete = False
        repeated_page = False
        partial_error = None
        missing_fields = 0
        seen_pages: list[tuple[str, ...]] = []
        seen_ids: set[str] = set()
        while page <= final_page:
            status, body = self.transport.request("GET", "/work_orders", query={**query, "page": page, "per_page": per_page})
            if status != 200:
                if pages_read == 0:
                    raise GateError("read_rejected", status=status, path="/work_orders")
                partial_error = {"gate": "read_rejected", "status": status, "page": page}
                break
            batch = _as_list(body)
            signature = tuple(str(item.get("id")) for item in batch)
            if signature in seen_pages:
                repeated_page = True
                complete = False
                break
            seen_pages.append(signature)
            pages_read += 1
            last_page = page
            scanned += len(batch)
            for item in batch:
                if not _local_schedule_match(item, filters):
                    continue
                if customer_id:
                    if item.get("customer_id") is None:
                        missing_fields += 1
                        continue
                    if str(item.get("customer_id")) != customer_id:
                        continue
                if location_id:
                    if item.get("service_location_id") is None:
                        missing_fields += 1
                        continue
                    if str(item.get("service_location_id")) != location_id:
                        continue
                identity = str(item.get("id"))
                if identity in seen_ids:
                    continue
                seen_ids.add(identity)
                matched.append(item)
            if len(batch) < per_page:
                complete = True
                break
            page += 1
        if repeated_page or partial_error is not None or missing_fields:
            complete = False
        matched.sort(key=lambda row: str(row.get("starts_at") or ""), reverse=filters.get("sort_direction") == "desc")
        by_route = {row["route_id"]: row for row in (self.route_directory or {}).get("routes", [])}
        live_staff = {entry["route_id"]: entry for entry in (directory or {}).get("routes", [])}
        items = []
        for item in matched:
            view = work_order_view(item)
            route_ids = {str(route) for route in view.get("service_route_ids") or []}
            if directory is not None:
                staff_groups = [live_staff[route] for route in route_ids if route in live_staff]
                view["route_staff"] = [person for group in staff_groups for person in group["staff"]]
                view["route_assignee"] = None
                view["route_staff_ambiguous"] = any(group["ambiguous"] for group in staff_groups)
            else:
                snapshot = next((by_route[route] for route in route_ids if route in by_route), None)
                if snapshot is not None:
                    view["configured_route_assignee"] = {**snapshot, "kind": "configured_snapshot", "not_live_api_staff": True}
            items.append(view)
        local_filter = [name for name, present in (
            ("date", filters.get("start_date") or filters.get("end_date")),
            ("status", filters.get("status")),
            ("service_route_ids", filters.get("service_route_ids")),
            ("customer_id", customer_id),
            ("service_location_id", location_id),
        ) if present]
        return {
            "items": items,
            "technician_resolved_from": resolved_from,
            "fallback_reason": fallback_reason,
            "complete": complete,
            "truncated": not complete,
            "pages_read": pages_read,
            "scanned_count": scanned,
            "next_page": None if complete or repeated_page or partial_error or missing_fields else last_page + 1,
            "per_page": per_page,
            "repeated_page": repeated_page,
            "partial_error": partial_error,
            "rows_missing_filter_field": missing_fields,
            "server_side_filtering": False,
            "local_filter": local_filter,
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
        if status not in {200, 204}:
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

    def list_contacts(self, customer_id: str) -> dict[str, Any]:
        customer_id = _required_id(customer_id)
        found = self._pages(f"/customers/{customer_id}/contacts")
        found["customer_id"] = customer_id
        return found

    def _capture_write(self, status: int, payload: Any) -> dict[str, Any]:
        diagnostic = dict(getattr(self.transport, "last_write_diagnostic", {}) or {})
        diagnostic.setdefault("status", status)
        diagnostic.setdefault("response_body_retained", False)
        self.last_write_diagnostic = diagnostic
        return payload if isinstance(payload, dict) else {}

    def create_contact(self, customer_id: str, body: dict[str, Any]) -> dict[str, Any]:
        path = f"/customers/{_required_id(customer_id)}/contacts"
        _assert_typed_path("POST", path)
        status, payload = self.transport.request("POST", path, body)
        captured = self._capture_write(status, payload)
        if status >= 500:
            raise AmbiguousWriteError(f"remote_{status}", diagnostic=self.last_write_diagnostic)
        return captured

    def create_service_location(self, customer_id: str, body: dict[str, Any]) -> dict[str, Any]:
        path = f"/customers/{_required_id(customer_id)}/service_locations"
        _assert_typed_path("POST", path)
        status, payload = self.transport.request("POST", path, body)
        captured = self._capture_write(status, payload)
        if status >= 500:
            raise AmbiguousWriteError(f"remote_{status}", diagnostic=self.last_write_diagnostic)
        return captured

    def patch_service_location(self, customer_id: str, location_id: str, body: dict[str, Any]) -> dict[str, Any]:
        path = f"/customers/{_required_id(customer_id)}/service_locations/{_required_id(location_id)}"
        _assert_typed_path("PATCH", path)
        status, payload = self.transport.request("PATCH", path, body)
        captured = self._capture_write(status, payload)
        if status >= 500:
            raise AmbiguousWriteError(f"remote_{status}", diagnostic=self.last_write_diagnostic)
        if status != 200:
            raise GateError("location_patch_rejected", status=status)
        return captured

    def list_work_order_templates(self) -> dict[str, Any]:
        return self._pages("/work_order_templates")

    def get_work_order_template(self, template_id: str) -> dict[str, Any]:
        template_id = _required_id(template_id)
        status, body = self.transport.request("GET", f"/work_order_templates/{template_id}")
        if status != 200 or not isinstance(body, dict) or not isinstance(body.get("service_appointment_template"), dict):
            raise GateError("template_unverified", status=status)
        return body["service_appointment_template"]

    def list_services(self) -> dict[str, Any]:
        return self._pages("/services")

    def create_customer(self, body: dict[str, Any]) -> dict[str, Any]:
        path = "/customers"
        _assert_typed_path("POST", path)
        status, payload = self.transport.request("POST", path, body)
        captured = self._capture_write(status, payload)
        if status >= 500:
            raise AmbiguousWriteError(f"remote_{status}", diagnostic=self.last_write_diagnostic)
        return captured

    def create_work_order(self, body: dict[str, Any]) -> dict[str, Any]:
        path = "/work_orders"
        _assert_typed_path("POST", path)
        status, payload = self.transport.request("POST", path, body)
        if status >= 500:
            raise AmbiguousWriteError(f"remote_{status}")
        if not isinstance(payload, dict):
            return {}
        return payload
