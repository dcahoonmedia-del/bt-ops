"""Documented customer and work-order create bodies. No live Fieldwork calls."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from .allowlist import (
    ADDITIONAL_LOCATION_FIELDS,
    CONTACT_FIELDS,
    CALLER_OCCURRENCE_FIELDS,
    CREATE_FIELDS,
    CUSTOMER_CREATE_FIELDS,
    CUSTOMER_LOCATION_FIELDS,
    GATE_CONTACT,
    GATE_LEAD_STATUS,
    GATE_RECURRING,
    GATE_STARTS_AT_DATETIME,
    GATE_STARTS_AT_POST,
    GATE_TAXABLE,
    LINE_ITEM_FIELDS,
    OCCURRENCE_FIELDS,
    REJECTED_OCCURRENCE_FIELDS,
    SERVICE_ADDRESS_FIELDS,
    UnknownFieldError,
    assert_only,
    is_lead_status,
)
from .errors import GateError

CUSTOMER_TYPES = ("Residential", "Commercial")
CUSTOMER_STATUSES = frozenset({"active", "inactive", "financial_hold", "sent_to_collections"})
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
PHONE_KINDS = frozenset({"Home", "Office", "Mobile", "Fax", "Other"})
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
    loc = _caller_location(payload)
    assert_only(loc, CUSTOMER_LOCATION_FIELDS, label="service_location")
    name = loc.get("name")
    if not isinstance(name, str) or not name.strip():
        _unknown("name")
    same = loc.get("same_as_billing_address")
    if not isinstance(same, bool):
        _unknown("same_as_billing_address")
    customer["service_locations_attributes"] = [{"name": name, "same_as_billing_address": same}]
    plan: dict[str, Any] = {"customer": customer, "contact": None, "location_patch": None, "additional_location": None}
    if same:
        if "service_address" in payload or "location_tax_rate_id" in payload:
            _unknown("service_address" if "service_address" in payload else "location_tax_rate_id")
    else:
        address = _address(payload.get("service_address"))
        if "location_tax_rate_id" not in payload:
            _unknown("location_tax_rate_id")
        plan["location_patch"] = {
            "name": name,
            "tax_rate_id": _int(payload.get("location_tax_rate_id"), "location_tax_rate_id", positive=True),
            "address_attributes": address,
        }
    if "additional_location" in payload:
        plan["additional_location"] = _additional_location(payload["additional_location"])
    if "contact" in payload:
        plan["contact"] = _contact(payload["contact"])
    if "primary_email" in payload:
        email = payload["primary_email"]
        if not isinstance(email, str) or not email.strip():
            _unknown("primary_email")
        plan["primary_email"] = email.strip()
        plan["invoice_email"] = {
            "caller_field": "primary_email",
            "api_field": "invoice_email",
            "value": email.strip(),
            "post_supported": False,
            "patch_supported": True,
            "sole_form_field": "customer[invoice_email]",
            "observed_http_status": 200,
            "observed_at": "2026-09-25T17:02:00-04:00",
            "candidate_body": {"customer": {"invoice_email": email.strip()}},
            "reason": "observed_customer_patch_not_customer_post",
        }
    if "location_email" in payload:
        location_email = payload["location_email"]
        if not isinstance(location_email, str) or not location_email.strip():
            _unknown("location_email")
        plan["location_email"] = location_email.strip()
    if "location_type_id" in payload:
        plan["location_type_id"] = _int(payload.get("location_type_id"), "location_type_id", positive=True)
    plan["billing_phone_kind"] = customer.get("billing_phone_kind")
    plan["phone_kind_supplied"] = "billing_phone_kind" in payload
    plan["contact_count"] = 1 if plan.get("contact") else 0
    if "confirmed_new" in payload and payload["confirmed_new"] is not True:
        _unknown("confirmed_new")
    if "existing_customer_id" in payload:
        plan["existing_customer_id"] = _int(payload.get("existing_customer_id"), "existing_customer_id", positive=True)
    if "acknowledge_duplicate_coverage" in payload:
        ack = payload["acknowledge_duplicate_coverage"]
        if not isinstance(ack, list) or len(ack) != len(set(ack)) or any(item not in {"email", "address"} for item in ack):
            _unknown("acknowledge_duplicate_coverage")
        plan["acknowledge_duplicate_coverage"] = sorted(ack)
    plan["confirmed_new"] = payload.get("confirmed_new") is True
    plan["api_steps"] = _customer_api_steps(plan)
    return plan


def _caller_location(payload: dict[str, Any]) -> dict[str, Any]:
    """One nested location. A single object and a one-item list are the same caller input.

    The Fieldwork customer POST key is service_locations_attributes. The plural
    service_locations name is only the caller wrapper. Omitting it is a missing
    location, not an unknown field injected into the payload.
    """
    if "service_locations" not in payload:
        raise GateError("nested_location_required", fields=["name", "same_as_billing_address"])
    locations = payload["service_locations"]
    if isinstance(locations, dict):
        return locations
    if isinstance(locations, list) and len(locations) == 1 and isinstance(locations[0], dict):
        return locations[0]
    _unknown("service_locations")
    return {}


def _customer_api_steps(plan: dict[str, Any]) -> list[dict[str, Any]]:
    steps = [{"method": "POST", "path": "/customers", "body": {"customer": plan["customer"]}}]
    if plan.get("main_location") or plan.get("location_patch"):
        service_location = dict(plan.get("main_location") or {})
        if plan.get("location_patch"):
            service_location.update(plan["location_patch"])
        steps.append(
            {
                "method": "PATCH",
                "path": "/customers/{customer_id}/service_locations/{location_id}",
                "body": {"service_location": service_location},
            }
        )
    if plan.get("primary_email"):
        steps.append(
            {
                "method": "PATCH",
                "path": "/customers/{customer_id}",
                "body": {"customer": {"invoice_email": plan["primary_email"]}},
            }
        )
    if plan.get("deferred_location_email"):
        steps.append(
            {
                "method": "PATCH",
                "path": "/customers/{customer_id}/service_locations/{location_id}",
                "body": {"service_location": {"email": plan["deferred_location_email"]}},
            }
        )
    if plan.get("additional_location"):
        steps.append(
            {
                "method": "POST",
                "path": "/customers/{customer_id}/service_locations",
                "body": {"service_location": plan["additional_location"]},
            }
        )
    if plan.get("contact"):
        steps.append(
            {
                "method": "POST",
                "path": "/customers/{customer_id}/contacts",
                "body": {"contact": plan["contact"]},
            }
        )
    return steps


def _address(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        _unknown("service_address")
    assert_only(value, SERVICE_ADDRESS_FIELDS, label="service_address")
    address: dict[str, Any] = {}
    for key, item in value.items():
        if key == "phone_kind":
            if item not in PHONE_KINDS:
                _unknown("phone_kind")
        elif not isinstance(item, str):
            _unknown(key)
        address[key] = item
    if not any(str(address.get(key) or "").strip() for key in ("street", "city", "state", "zip")):
        _unknown("service_address")
    return address


def _contact(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateError(GATE_CONTACT, reason="first_name_last_name_and_email_required")
    assert_only(value, CONTACT_FIELDS, label="contact")
    first_name = value.get("first_name")
    last_name = value.get("last_name")
    email = value.get("email")
    if not isinstance(first_name, str) or not first_name.strip() or not isinstance(last_name, str) or not last_name.strip() or not isinstance(email, str) or not email.strip():
        raise GateError(GATE_CONTACT, reason="first_name_last_name_and_email_required")
    contact = {"first_name": first_name, "last_name": last_name, "email": email}
    for key in ("phone", "phone_ext", "phone_note", "description"):
        if key in value:
            if not isinstance(value[key], str):
                _unknown(key)
            contact[key] = value[key]
    if "title" in value:
        if value["title"] not in {"Dr.", "Mr.", "Ms.", "Mrs."}:
            _unknown("title")
        contact["title"] = value["title"]
    if "phone_kind" in value:
        if value["phone_kind"] not in PHONE_KINDS:
            _unknown("phone_kind")
        contact["phone_kind"] = value["phone_kind"]
    return contact


def _additional_location(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        _unknown("additional_location")
    assert_only(value, ADDITIONAL_LOCATION_FIELDS, label="additional_location")
    name = value.get("name")
    if not isinstance(name, str) or not name.strip():
        _unknown("name")
    body: dict[str, Any] = {
        "name": name,
        "tax_rate_id": _int(value.get("tax_rate_id"), "tax_rate_id", positive=True),
    }
    if "address" in value:
        body["address_attributes"] = _address(value["address"])
    return body


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


def classify_starts_at(value: Any) -> dict[str, Any]:
    """Date-only stays postable. An offset timestamp is preserved and is not a date-only job."""
    if not isinstance(value, str) or not value:
        _unknown("starts_at")
    if _DATE.match(value):
        try:
            date.fromisoformat(value)
        except ValueError:
            _unknown("starts_at")
        return {
            "kind": "date",
            "starts_at": value,
            "calendar_date": value,
            "instant": None,
            "timezone": None,
            "post_ready": True,
        }
    if value.endswith("Z") or "T" not in value:
        raise GateError(
            GATE_STARTS_AT_DATETIME,
            field="starts_at",
            accepted="YYYY-MM-DD or offset-aware timestamp",
            datetime_format_unverified=True,
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise GateError(GATE_STARTS_AT_DATETIME, field="starts_at", datetime_format_unverified=True) from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GateError(GATE_STARTS_AT_DATETIME, field="starts_at", reason="offset_required", datetime_format_unverified=True)
    tail = value[10:]
    if "+" not in tail and "-" not in tail:
        raise GateError(GATE_STARTS_AT_DATETIME, field="starts_at", reason="numeric_offset_required", datetime_format_unverified=True)
    offset = parsed.strftime("%z")
    timezone = f"{offset[:3]}:{offset[3:]}" if len(offset) == 5 else offset
    return {
        "kind": "offset_timestamp",
        "starts_at": value,
        "calendar_date": parsed.date().isoformat(),
        "instant": parsed.isoformat(),
        "timezone": timezone,
        "post_ready": False,
        "post_clock_live_tested": False,
        "gate": GATE_STARTS_AT_POST,
    }


def _occurrence(item: dict[str, Any]) -> dict[str, Any]:
    rejected = sorted(key for key in REJECTED_OCCURRENCE_FIELDS if key in item)
    extra = sorted(key for key in item if key not in OCCURRENCE_FIELDS and key not in REJECTED_OCCURRENCE_FIELDS)
    if rejected or extra:
        raise UnknownFieldError(sorted(set(rejected + extra)))
    classified = classify_starts_at(item.get("starts_at"))
    starts_at = classified["starts_at"]
    routes = item.get("service_route_ids")
    if not isinstance(routes, list) or not routes or any(isinstance(route, bool) or not isinstance(route, int) or route <= 0 for route in routes):
        _unknown("service_route_ids")
    occurrence: dict[str, Any] = {"service_route_ids": list(routes), "starts_at": starts_at, "_starts": classified}
    if "duration" in item:
        occurrence["duration"] = _int(item["duration"], "duration")
    if "instructions" in item:
        if not isinstance(item["instructions"], str):
            _unknown("instructions")
        occurrence["instructions"] = item["instructions"]
    if "production_value" in item:
        occurrence["production_value"] = _int(item["production_value"], "production_value")
    return occurrence


def work_order_request(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        _unknown("work_order")
    assert_only(payload, CREATE_FIELDS, label="create")
    occurrence = _caller_occurrence(payload)
    repeat = payload.get("repeat_type")
    if "repeat_type" not in payload:
        raise GateError("missing_field", fields=["repeat_type"])
    if not isinstance(repeat, str) or repeat not in REPEAT_TYPES:
        _unknown("repeat_type")
    if repeat != "none":
        raise GateError(GATE_RECURRING)
    period = _int(payload.get("repeat_period"), "repeat_period") if "repeat_period" in payload else None
    items = payload.get("line_items")
    if "line_items" in payload and (not isinstance(items, list) or not items):
        raise GateError("missing_field", fields=["line_items"])
    appointment: dict[str, Any] = {
        "customer_id": _int(payload.get("customer_id"), "customer_id", positive=True),
        "service_location_id": _int(payload.get("service_location_id"), "service_location_id", positive=True),
        "repeat_type": "none",
        "appointment_occurrences_attributes": [_occurrence(occurrence)],
    }
    if period is not None:
        appointment["repeat_period"] = period
    if isinstance(items, list):
        appointment["line_items_attributes"] = [_line_item(item) for item in items]
    body: dict[str, Any] = {"service_appointment": appointment}
    if "template_id" in payload:
        body["template_id"] = _int(payload.get("template_id"), "template_id", positive=True)
    return body


def _caller_occurrence(payload: dict[str, Any]) -> dict[str, Any]:
    """One occurrence from a flat caller or from a one-item occurrences list.

    The Fieldwork body key is appointment_occurrences_attributes. A missing
    occurrences key is not an unknown field the caller sent.
    """
    flat = sorted(key for key in CALLER_OCCURRENCE_FIELDS if key in payload)
    if "occurrences" not in payload:
        if "starts_at" not in payload or "service_route_ids" not in payload:
            missing = [key for key in ("starts_at", "service_route_ids") if key not in payload]
            raise GateError("missing_field", fields=missing)
        return {key: payload[key] for key in flat}
    if flat:
        raise UnknownFieldError(flat)
    occurrences = payload.get("occurrences")
    if not isinstance(occurrences, list):
        _unknown("occurrences")
    if len(occurrences) == 0:
        raise GateError("missing_field", fields=["starts_at", "service_route_ids"])
    if len(occurrences) != 1 or not isinstance(occurrences[0], dict):
        if len(occurrences) != 1:
            raise GateError(GATE_RECURRING)
        _unknown("occurrences")
    _occurrence_fields(occurrences[0])
    if "starts_at" not in occurrences[0] or "service_route_ids" not in occurrences[0]:
        missing = [key for key in ("starts_at", "service_route_ids") if key not in occurrences[0]]
        raise GateError("missing_field", fields=missing)
    return occurrences[0]


def _occurrence_fields(item: dict[str, Any]) -> None:
    rejected = sorted(key for key in REJECTED_OCCURRENCE_FIELDS if key in item)
    extra = sorted(str(key) for key in item if key not in OCCURRENCE_FIELDS and key not in REJECTED_OCCURRENCE_FIELDS)
    if rejected or extra:
        raise UnknownFieldError(sorted(set(rejected + extra)))
