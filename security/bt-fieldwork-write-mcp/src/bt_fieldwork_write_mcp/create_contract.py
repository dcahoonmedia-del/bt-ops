"""Documented customer and work-order create bodies. No live Fieldwork calls."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from .allowlist import (
    CREATE_FIELDS,
    CUSTOMER_CREATE_FIELDS,
    CUSTOMER_LOCATION_FIELDS,
    GATE_ARRIVAL_WINDOW,
    GATE_LEAD_STATUS,
    GATE_RECURRING,
    GATE_STARTS_AT_DATETIME,
    GATE_TAXABLE,
    LINE_ITEM_FIELDS,
    OCCURRENCE_FIELDS,
    assert_only,
    is_lead_status,
)
from .errors import GateError

CUSTOMER_TYPES = ("Residential", "Commercial")
CUSTOMER_STATUSES = frozenset({"active", "inactive", "financial_hold", "sent_to_collections"})
PHONE_KINDS = frozenset({"Home", "Office", "Mobile", "Fax", "Other"})
REPEAT_TYPES = frozenset(
    {
        "none",
        "daily",
        "weekly",
        "monthly",
        "bimonthly",
        "quarterly",
        "tri_annually",
        "semi_annually",
        "seasonal",
        "yearly",
    }
)
LINE_TYPES = frozenset({"service", "material", "other", "fee"})
PAYABLE_TYPES = frozenset({"Service", "Material", "Fee"})
PAYABLE_REQUIRED = frozenset({"service", "material"})
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_BILLING_STRINGS = (
    "billing_name",
    "billing_attention",
    "billing_street",
    "billing_street2",
    "billing_city",
    "billing_state",
    "billing_zip",
    "billing_county",
    "billing_phone",
    "billing_phone_ext",
    "billing_phone_note",
)
_BILLING_LISTS = ("billing_phones", "billing_phones_exts", "billing_phones_notes")


def response_id(body: Any) -> int | None:
    """Integer id only. Swagger create responses are null, so other shapes stay unverified."""
    if not isinstance(body, dict):
        return None
    value = body.get("id")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _unknown(field: str) -> None:
    raise GateError("unknown_field", fields=[field])


def _optional_str(payload: dict[str, Any], field: str, target: dict[str, Any]) -> None:
    if field not in payload:
        return
    value = payload[field]
    if not isinstance(value, str):
        _unknown(field)
    target[field] = value


def _int(value: Any, field: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _unknown(field)
    if positive and value <= 0:
        _unknown(field)
    return value


def customer_request(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        _unknown("customer")
    assert_only(payload, CUSTOMER_CREATE_FIELDS, label="customer")
    customer_type = payload.get("customer_type")
    if customer_type not in CUSTOMER_TYPES:
        _unknown("customer_type")
    customer: dict[str, Any] = {"customer_type": customer_type}
    if customer_type == "Commercial":
        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            _unknown("name")
        customer["name"] = name
        _optional_str(payload, "first_name", customer)
        _optional_str(payload, "last_name", customer)
    else:
        last_name = payload.get("last_name")
        last_filled = isinstance(last_name, str) and bool(last_name.strip())
        if not last_filled:
            _unknown("last_name")
        customer["last_name"] = last_name
        if "first_name" in payload:
            if not isinstance(payload["first_name"], str):
                _unknown("first_name")
            customer["first_name"] = payload["first_name"]
        _optional_str(payload, "name", customer)
    if "status" in payload:
        status = payload["status"]
        if isinstance(status, str) and is_lead_status({"status": status}):
            raise GateError(GATE_LEAD_STATUS)
        if not isinstance(status, str) or status not in CUSTOMER_STATUSES:
            _unknown("status")
        customer["status"] = status
    else:
        customer["status"] = "active"
    for field in _BILLING_STRINGS:
        _optional_str(payload, field, customer)
    if "billing_term_id" in payload:
        customer["billing_term_id"] = _int(payload["billing_term_id"], "billing_term_id")
    if "billing_phone_kind" in payload:
        kind = payload["billing_phone_kind"]
        if kind not in PHONE_KINDS:
            _unknown("billing_phone_kind")
        customer["billing_phone_kind"] = kind
    for field in _BILLING_LISTS:
        if field not in payload:
            continue
        values = payload[field]
        if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
            _unknown(field)
        customer[field] = list(values)
    if "billing_phones_kinds" in payload:
        kinds = payload["billing_phones_kinds"]
        if not isinstance(kinds, list) or any(item not in PHONE_KINDS for item in kinds):
            _unknown("billing_phones_kinds")
        customer["billing_phones_kinds"] = list(kinds)
    _optional_str(payload, "note", customer)
    locations = payload.get("service_locations")
    if not isinstance(locations, list) or not locations:
        _unknown("service_locations")
    built: list[dict[str, Any]] = []
    for loc in locations:
        if not isinstance(loc, dict):
            _unknown("service_locations")
        assert_only(loc, CUSTOMER_LOCATION_FIELDS, label="service_location")
        name = loc.get("name")
        if not isinstance(name, str) or not name.strip():
            _unknown("name")
        same = loc.get("same_as_billing_address")
        if not isinstance(same, bool):
            _unknown("same_as_billing_address")
        built.append({"name": name, "same_as_billing_address": same})
    customer["service_locations_attributes"] = built
    return {"customer": customer}


def _line_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        _unknown("line_items")
    assert_only(item, LINE_ITEM_FIELDS, label="line_item")
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        _unknown("name")
    kind = item.get("type")
    if kind not in LINE_TYPES:
        _unknown("type")
    line: dict[str, Any] = {
        "name": name,
        "type": kind,
        "quantity": _int(item.get("quantity"), "quantity"),
        "price": _int(item.get("price"), "price"),
    }
    if kind in PAYABLE_REQUIRED or "payable_id" in item or "payable_type" in item:
        line["payable_id"] = _int(item.get("payable_id"), "payable_id", positive=True)
        payable_type = item.get("payable_type")
        if payable_type not in PAYABLE_TYPES:
            _unknown("payable_type")
        line["payable_type"] = payable_type
    if "taxable" in item:
        if item["taxable"] is True:
            raise GateError(GATE_TAXABLE, reason="tax_rate_id is required if taxable and tax fields are not accepted")
        if item["taxable"] is not False:
            _unknown("taxable")
        line["taxable"] = False
    return line


def _occurrence(item: dict[str, Any]) -> dict[str, Any]:
    starts_at = item.get("starts_at")
    if not isinstance(starts_at, str):
        _unknown("starts_at")
    if "T" in starts_at or starts_at.endswith("Z") or (len(starts_at) > 10 and ("+" in starts_at[10:] or "-" in starts_at[10:])):
        raise GateError(
            GATE_STARTS_AT_DATETIME,
            field="starts_at",
            accepted="YYYY-MM-DD",
            datetime_format_unverified=True,
        )
    if not _DATE.match(starts_at):
        _unknown("starts_at")
    try:
        date.fromisoformat(starts_at)
    except ValueError:
        _unknown("starts_at")
    routes = item.get("service_route_ids")
    if not isinstance(routes, list) or not routes or any(isinstance(route, bool) or not isinstance(route, int) or route <= 0 for route in routes):
        _unknown("service_route_ids")
    occurrence: dict[str, Any] = {"service_route_ids": list(routes), "starts_at": starts_at}
    if "duration" in item:
        occurrence["duration"] = _int(item["duration"], "duration")
    return occurrence


def work_order_request(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        _unknown("work_order")
    assert_only(payload, CREATE_FIELDS, label="create")
    occurrences = payload.get("occurrences")
    if not isinstance(occurrences, list):
        _unknown("occurrences")
    for occ in occurrences:
        if not isinstance(occ, dict):
            _unknown("occurrences")
        assert_only(occ, OCCURRENCE_FIELDS, label="occurrence")
        if "use_time_window" in occ:
            raise GateError(GATE_ARRIVAL_WINDOW)
    repeat = payload.get("repeat_type")
    if not isinstance(repeat, str) or repeat not in REPEAT_TYPES:
        _unknown("repeat_type")
    if repeat != "none":
        raise GateError(GATE_RECURRING)
    period = _int(payload.get("repeat_period"), "repeat_period")
    items = payload.get("line_items")
    missing: list[str] = []
    if not isinstance(items, list) or not items:
        missing.append("line_items")
    if len(occurrences) == 0:
        missing.append("occurrences")
    if missing:
        raise GateError("unknown_field", fields=missing)
    if len(occurrences) != 1:
        raise GateError(GATE_RECURRING)
    return {
        "service_appointment": {
            "customer_id": _int(payload.get("customer_id"), "customer_id", positive=True),
            "service_location_id": _int(payload.get("service_location_id"), "service_location_id", positive=True),
            "repeat_type": "none",
            "repeat_period": period,
            "line_items_attributes": [_line_item(item) for item in items],
            "appointment_occurrences_attributes": [_occurrence(occurrences[0])],
        }
    }
