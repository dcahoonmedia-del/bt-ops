"""Duplicate checks, creation journal, and catalog-backed work orders. Fake transport only."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from .allowlist import (
    GATE_ADDRESS,
    GATE_CATALOG,
    GATE_DISTINCT_IDS,
    GATE_DUPLICATE_SEARCH,
    GATE_DUPLICATE_UNRESOLVED,
    GATE_PARTIAL,
    GATE_READBACK,
    GATE_RECURRING,
    GATE_ROUTE_STAFF,
    GATE_SCHEDULE,
    GATE_STARTS_AT_POST,
    GATE_TAXABLE,
    GATE_TEMPLATE,
)
from .create_contract import response_id
from .errors import AmbiguousWriteError, GateError

_WORD = re.compile(r"[a-z0-9]+")


def normalize_name(value: Any) -> str:
    return " ".join(_WORD.findall(str(value or "").casefold()))


def normalize_phone(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:]
    return digits


def names_for(payload: dict[str, Any]) -> set[str]:
    found = set()
    for key in ("name", "last_name", "billing_name"):
        text = normalize_name(payload.get(key))
        if text:
            found.add(text)
    combined = normalize_name(" ".join(str(payload.get(key) or "") for key in ("first_name", "last_name")))
    if combined:
        found.add(combined)
    contact = payload.get("contact") if isinstance(payload.get("contact"), dict) else {}
    contact_name = normalize_name(" ".join(str(contact.get(key) or "") for key in ("first_name", "last_name")))
    if contact_name:
        found.add(contact_name)
    return {item for item in found if item}


def phones_for(payload: dict[str, Any]) -> set[str]:
    found = set()
    for key in ("billing_phone",):
        phone = normalize_phone(payload.get(key))
        if phone:
            found.add(phone)
    for item in payload.get("billing_phones") or []:
        phone = normalize_phone(item)
        if phone:
            found.add(phone)
    contact = payload.get("contact") if isinstance(payload.get("contact"), dict) else {}
    phone = normalize_phone(contact.get("phone"))
    if phone:
        found.add(phone)
    return found


def money(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise GateError(GATE_CATALOG, reason="money_missing")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise GateError(GATE_CATALOG, reason="money_unparsed") from None


def money_equal(left: Any, right: Any) -> bool:
    return money(left) == money(right)


def money_number(value: Any) -> int | str:
    amount = money(value)
    if amount == amount.to_integral_value():
        return int(amount)
    return format(amount, "f")


def response_labels(client: Any) -> dict[str, Any]:
    fake = bool(getattr(getattr(client, "transport", None), "is_fake_double", False))
    if fake:
        return {"test_double": True, "response_schema": "fake_test_double_not_live_schema", "response_schema_verified": False}
    return {"test_double": False, "response_schema_verified": False}


def calendar_day(starts_at: str) -> str:
    if len(starts_at) >= 10 and starts_at[4] == "-" and starts_at[7] == "-" and "T" not in starts_at:
        return starts_at[:10]
    from datetime import datetime

    return datetime.fromisoformat(starts_at).date().isoformat()


def _search_pages(client: Any, path: str, query: dict[str, Any]) -> dict[str, Any]:
    try:
        found = client._pages(path, query)
    except GateError as exc:
        raise GateError(GATE_DUPLICATE_SEARCH, path=path, status=exc.detail.get("status")) from exc
    if not found.get("complete") or found.get("truncated") or found.get("repeated_page") or found.get("partial_error"):
        raise GateError(GATE_DUPLICATE_SEARCH, path=path, repeated_page=bool(found.get("repeated_page")), truncated=bool(found.get("truncated")))
    return found


def duplicate_search(client: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Complete name and phone scans. An incomplete page is not proof of no duplicate."""
    wanted_names = names_for(payload)
    wanted_phones = phones_for(payload)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name in sorted(wanted_names):
        pages = _search_pages(client, "/customers/search", {"query": name})
        for row in pages["items"]:
            identity = str(row.get("id"))
            if identity not in seen:
                rows.append(row)
                seen.add(identity)
    for phone in wanted_phones:
        status, body = client.transport.request("GET", "/customers/search_by_phone", query={"phone": phone, "as_object": True})
        if status != 200:
            raise GateError(GATE_DUPLICATE_SEARCH, path="/customers/search_by_phone", status=status)
        from .fieldwork import _as_list

        for row in _as_list(body):
            if str(row.get("id")) not in seen:
                rows.append(row)
                seen.add(str(row.get("id")))
    candidates = []
    for row in rows:
        candidate = _inspect_candidate(client, row)
        names = {normalize_name(candidate.get("name")), normalize_name(candidate.get("billing_name"))}
        names.add(normalize_name(" ".join(str(candidate.get(key) or "") for key in ("first_name", "last_name"))))
        phones = {normalize_phone(candidate.get("billing_phone"))}
        phones.update(normalize_phone(item) for item in candidate.get("phones") or [])
        if (wanted_names & {item for item in names if item}) or (wanted_phones & {item for item in phones if item}):
            candidates.append(candidate)
    return {"complete": True, "candidates": candidates, "normalized_names": sorted(wanted_names), "normalized_phones": sorted(wanted_phones)}


def _inspect_candidate(client: Any, row: dict[str, Any]) -> dict[str, Any]:
    customer_id = str(row.get("id"))
    customer = client.get_customer(customer_id)
    locations = client.list_service_locations(customer_id)
    if not locations.get("complete") or locations.get("truncated"):
        raise GateError(GATE_DUPLICATE_SEARCH, path="/service_locations", customer_id=customer_id)
    return {
        "id": customer.get("id"),
        "name": customer.get("name"),
        "first_name": customer.get("first_name"),
        "last_name": customer.get("last_name"),
        "billing_name": customer.get("billing_name"),
        "email": customer.get("email"),
        "billing_phone": customer.get("billing_phone"),
        "phones": list(customer.get("billing_phones") or []),
        "billing_address": customer.get("billing_address"),
        "status": customer.get("status") or customer.get("customer_status"),
        "locations": [
            {"id": item.get("id"), "name": item.get("name"), "address": item.get("address"), "email": item.get("email")}
            for item in locations.get("items") or []
        ],
    }


def resolve_duplicates(
    search: dict[str, Any],
    *,
    confirmed_new: bool,
    existing_customer_id: int | None,
    approved_candidate_ids: list[Any] | None = None,
) -> dict[str, Any]:
    candidates = search["candidates"]
    current_ids = {str(item.get("id")) for item in candidates}
    if approved_candidate_ids is not None:
        appeared = sorted(current_ids - {str(item) for item in approved_candidate_ids})
        if appeared:
            raise GateError(GATE_DUPLICATE_UNRESOLVED, reason="new_match_requires_approval", candidate_ids=appeared, candidates=candidates)
    if confirmed_new and existing_customer_id is not None:
        raise GateError("unknown_field", fields=["confirmed_new", "existing_customer_id"])
    if candidates and not confirmed_new and existing_customer_id is None:
        raise GateError(GATE_DUPLICATE_UNRESOLVED, candidates=candidates)
    if existing_customer_id is not None and str(existing_customer_id) not in current_ids:
        raise GateError(GATE_DUPLICATE_UNRESOLVED, reason="existing_id_not_in_matches", candidates=candidates)
    return {
        "confirmed_new": confirmed_new,
        "existing_customer_id": existing_customer_id,
        "candidate_ids": [item.get("id") for item in candidates],
        "complete": True,
    }


def load_catalog(client: Any, template_id: int | None) -> dict[str, Any]:
    listed = client.list_work_order_templates()
    if not listed.get("complete") or listed.get("repeated_page") or listed.get("partial_error"):
        raise GateError(GATE_TEMPLATE, reason="template_list_incomplete")
    items = listed.get("items") or []
    if template_id is not None:
        chosen = [row for row in items if str(row.get("id")) == str(template_id)]
        if len(chosen) != 1:
            raise GateError(GATE_TEMPLATE, reason="template_id_not_in_list")
        chosen_id = chosen[0]["id"]
    elif len(items) == 1:
        chosen_id = items[0].get("id")
    else:
        raise GateError(GATE_TEMPLATE, reason="template_not_unique")
    template = client.get_work_order_template(str(chosen_id))
    defaults = template.get("work_order")
    if not isinstance(defaults, dict):
        raise GateError(GATE_TEMPLATE, reason="work_order_defaults_missing")
    for required in ("duration", "instructions", "production_value"):
        if required not in defaults:
            raise GateError(GATE_TEMPLATE, reason="work_order_default_missing", field=required)
    if str(template.get("repeat_type") or "") != "none":
        raise GateError(GATE_RECURRING)
    if not money_equal(template.get("tax_amount"), 0) or not money_equal(template.get("discount"), 0):
        raise GateError(GATE_TAXABLE, reason="template_tax_not_accepted")
    if not money_equal(template.get("billing_frequency"), 0):
        raise GateError(GATE_CATALOG, reason="billing_frequency_not_accepted")
    lines = template.get("line_items") or []
    if len(lines) != 1 or not isinstance(lines[0], dict):
        raise GateError(GATE_TEMPLATE, reason="template_line_missing")
    line = lines[0]
    if line.get("taxable") is True:
        raise GateError(GATE_TAXABLE)
    services = client.list_services()
    if not services.get("complete") or services.get("repeated_page") or services.get("partial_error"):
        raise GateError(GATE_CATALOG, reason="service_list_incomplete")
    matches = [row for row in services.get("items") or [] if str(row.get("id")) == str(line.get("payable_id"))]
    if len(matches) != 1:
        raise GateError(GATE_CATALOG, reason="payable_not_in_services")
    service = matches[0]
    if "description" not in service:
        raise GateError(GATE_CATALOG, reason="service_label_is_description")
    if service.get("description") != line.get("name") or not money_equal(service.get("price"), line.get("price")):
        raise GateError(GATE_CATALOG, reason="service_disagrees_with_template")
    if line.get("type") != "service" or line.get("payable_type") != "Service":
        raise GateError(GATE_CATALOG, reason="template_line_type")
    normalized = {
        "name": line.get("name"),
        "type": line.get("type"),
        "quantity": money_number(line.get("quantity")),
        "price": money_number(line.get("price")),
        "payable_id": line.get("payable_id"),
        "payable_type": line.get("payable_type"),
        "taxable": False,
    }
    auto = template.get("auto_generates_invoice", None)
    return {
        "template": template,
        "defaults": defaults,
        "line": normalized,
        "observed_line": line,
        "service": {"id": service.get("id"), "description": service.get("description"), "price": service.get("price")},
        "billing_frequency": money_number(template.get("billing_frequency")),
        "invoice_generation_disclosed": True,
        "invoice_generation_reason": "billing_frequency_0_normal_invoice_generation" if auto is None else "auto_generates_invoice" if auto is True else "billing_frequency_0_normal_invoice_generation",
        "auto_generates_invoice": auto,
    }


def apply_catalog(appointment: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    template = catalog["template"]
    defaults = catalog["defaults"]
    line = catalog["line"]
    sent_line = dict(line)
    supplied = appointment.get("line_items_attributes")
    price_source = "template_standard"
    if supplied is not None:
        if not _line_identity_equal(supplied, sent_line):
            raise GateError(GATE_CATALOG, reason="caller_line_disagrees_with_template")
        sent_line["price"] = money_number(supplied[0]["price"])
        price_source = "caller"
    source = dict(appointment["appointment_occurrences_attributes"][0])
    starts = source.pop("_starts", None) or {}
    occurrence = {key: source[key] for key in ("service_route_ids", "starts_at", "duration", "instructions", "production_value") if key in source}
    if "duration" not in occurrence:
        occurrence["duration"] = defaults["duration"]
    if "instructions" not in occurrence:
        occurrence["instructions"] = defaults["instructions"]
    schedule_starts = occurrence["starts_at"]
    if starts.get("kind") == "offset_timestamp":
        occurrence["starts_at"] = starts["calendar_date"]
    body = {
        "customer_id": appointment["customer_id"],
        "service_location_id": appointment["service_location_id"],
        "repeat_type": "none",
        "repeat_period": appointment.get("repeat_period", template.get("repeat_period")),
        "line_items_attributes": [sent_line],
        "appointment_occurrences_attributes": [occurrence],
    }
    if body["repeat_period"] is None or isinstance(body["repeat_period"], bool):
        raise GateError("unknown_field", fields=["repeat_period"])
    total = money(sent_line["quantity"]) * money(sent_line["price"])
    line_total = int(total) if total == total.to_integral_value() else format(total, "f")
    if "production_value" not in occurrence:
        if price_source == "caller" and not money_equal(sent_line["price"], line["price"]):
            occurrence["production_value"] = line_total
        else:
            occurrence["production_value"] = money_number(defaults["production_value"])
    return {
        "service_appointment": body,
        "starts": starts,
        "line_total": line_total,
        "price": sent_line["price"],
        "standard_price": line["price"],
        "price_source": price_source,
        "schedule_starts_at": schedule_starts,
    }


def _line_identity_equal(supplied: list[dict[str, Any]], expected: dict[str, Any]) -> bool:
    """Service identity and quantity stay on the catalog line. Price is the caller's amount."""
    if len(supplied) != 1 or not isinstance(supplied[0], dict):
        return False
    left = supplied[0]
    for key in ("name", "type", "payable_type"):
        if left.get(key) != expected.get(key):
            return False
    if not money_equal(left.get("quantity"), expected.get("quantity")):
        return False
    if "price" not in left:
        return False
    money(left.get("price"))
    if str(left.get("payable_id")) != str(expected.get("payable_id")):
        return False
    if bool(left.get("taxable")) != bool(expected.get("taxable")):
        return False
    return True


def route_staff(client: Any, route_ids: list[int]) -> list[dict[str, Any]]:
    try:
        users = client.list_users()
    except GateError as exc:
        raise GateError(GATE_ROUTE_STAFF) from exc
    directory = (users or {}).get("directory") or {}
    shown = []
    for route_id in route_ids:
        group = next((row for row in directory.get("routes") or [] if str(row.get("route_id")) == str(route_id)), None)
        if group is None:
            raise GateError(GATE_ROUTE_STAFF, route_id=route_id)
        shown.append({
            "route_id": str(route_id),
            "assignee": None,
            "staff": group.get("staff") or [],
            "ambiguous": bool(group.get("ambiguous")),
        })
    return shown


def schedule_signature(view: dict[str, Any]) -> tuple[Any, ...]:
    return (
        view.get("date"),
        view.get("requested_starts_at"),
        tuple(sorted(str(item.get("id")) for item in view.get("conflicts") or [])),
    )


def schedule_view(client: Any, starts_at: str, route_ids: list[int]) -> dict[str, Any]:
    day = calendar_day(starts_at)
    try:
        found = client.list_work_orders(start_date=day, end_date=day, service_route_ids=route_ids)
    except GateError as exc:
        raise GateError(GATE_SCHEDULE) from exc
    if not found.get("complete") or found.get("truncated") or found.get("repeated_page") or found.get("partial_error"):
        raise GateError(GATE_SCHEDULE, truncated=bool(found.get("truncated")), repeated_page=bool(found.get("repeated_page")))
    return {
        "date": day,
        "requested_starts_at": starts_at,
        "timezone": "America/New_York",
        "clock_time_sent": "T" in str(starts_at),
        "promised_window_enforced": False,
        "complete": True,
        "conflicts": [
            {
                "id": item.get("id") if item.get("id") is not None else item.get("work_order_id"),
                "service_appointment_id": item.get("service_appointment_id"),
                "starts_at": item.get("starts_at"),
                "customer_id": item.get("customer_id"),
            }
            for item in found.get("items") or []
        ],
    }


def journal_partial(rows: list[dict[str, Any]]) -> dict[str, Any]:
    partial: dict[str, Any] = {"customer_id": None, "contact_id": None, "location_id": None, "succeeded_steps": [], "failed_step": None}
    for row in rows:
        for key in ("customer_id", "contact_id", "location_id"):
            if row.get(key):
                partial[key] = row[key]
        if row.get("outcome") == "succeeded":
            partial["succeeded_steps"].append(row.get("step"))
        if row.get("outcome") in {"ambiguous", "failed"}:
            partial["failed_step"] = row.get("step")
            result = row.get("result") if isinstance(row.get("result"), dict) else {}
            if result.get("reason"):
                partial["reason"] = result["reason"]
            if result.get("response"):
                partial["response"] = result["response"]
    partial["recovery"] = "new_exact_approved_proposal"
    partial["retry"] = False
    return partial


def _step(store: Any, proposal_id: str, step: str, intent: dict[str, Any], **ids: str | None) -> str:
    return store.begin_creation_step(proposal_id, step, intent, customer_id=ids.get("customer_id"), contact_id=ids.get("contact_id"), location_id=ids.get("location_id"))


def _succeed(store: Any, step_id: str, result: dict[str, Any], **ids: str | None) -> None:
    store.finish_creation_step(step_id, "succeeded", result, customer_id=ids.get("customer_id"), contact_id=ids.get("contact_id"), location_id=ids.get("location_id"))


def _ambiguous(store: Any, step_id: str, **ids: str | None) -> None:
    store.finish_creation_step(step_id, "ambiguous", {"retry": False}, customer_id=ids.get("customer_id"), contact_id=ids.get("contact_id"), location_id=ids.get("location_id"))


def stop_creation(store: Any, proposal: dict[str, Any], attempt_id: str | None) -> dict[str, Any]:
    if attempt_id is not None:
        store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "ambiguous")
        store.release_ambiguous_guard(proposal["subject_key"], proposal["proposal_id"])
    else:
        store.set_status(proposal["proposal_id"], "ambiguous")
    partial = journal_partial(store.creation_journal(proposal["proposal_id"]))
    gate = GATE_PARTIAL if partial["succeeded_steps"] else "ambiguous_remote_write_no_retry"
    return {"gate": gate, "partial": partial, "failed_step": partial["failed_step"], "retry": False, "recovery": "new_exact_approved_proposal"}


def _mismatch(field: str, sent: Any, got: Any) -> None:
    raise GateError(GATE_READBACK, reason="field_mismatch", field=field, sent=sent, got=got)


def _require_equal(field: str, sent: Any, got: Any) -> Any:
    if sent != got:
        _mismatch(field, sent, got)
    return got


def customer_readback(client: Any, customer_id: str, *, sent_customer: dict[str, Any], contact: dict[str, Any] | None, location_id: str, address: dict[str, Any] | None, wrote_customer: bool = True) -> dict[str, Any]:
    customer = client.get_customer(customer_id)
    status = str(customer.get("status") or customer.get("customer_status") or "").strip().lower()
    if status != "active":
        raise GateError(GATE_READBACK, reason="customer_not_active", status=status)
    if str(customer.get("id")) != str(customer_id):
        _mismatch("customer_id", customer_id, customer.get("id"))
    compared: dict[str, Any] = {}
    fields = sent_customer if wrote_customer else {}
    for key, value in fields.items():
        if key == "service_locations_attributes":
            continue
        got = customer.get(key)
        if key in {"billing_phone", "phone"} or key.endswith("_phone"):
            if normalize_phone(value) != normalize_phone(got):
                _mismatch(key, value, got)
        elif value != got:
            _mismatch(key, value, got)
        compared[key] = got
    location = client.get_location(customer_id, location_id)
    if str(location.get("id")) != str(location_id) or str(location.get("customer_id")) != str(customer_id):
        raise GateError(GATE_READBACK, reason="location_identity_mismatch")
    if wrote_customer:
        sent_location = (sent_customer.get("service_locations_attributes") or [{}])[0]
        _require_equal("location_name", sent_location.get("name"), location.get("name"))
        _require_equal("same_as_billing_address", sent_location.get("same_as_billing_address"), location.get("same_as_billing_address"))
    got_address = location.get("address") if isinstance(location.get("address"), dict) else {}
    compared_address = {}
    if address:
        for key, value in address.items():
            compared_address[key] = _require_equal(f"address.{key}", value, got_address.get(key))
    contacts = client.list_contacts(customer_id)
    if not contacts.get("complete") or contacts.get("truncated") or contacts.get("repeated_page"):
        raise GateError(GATE_READBACK, reason="contact_list_incomplete")
    items = contacts.get("items") or []
    contact_row = None
    compared_contact: dict[str, Any] = {}
    if contact is not None:
        contact_row = next((item for item in items if str(item.get("email") or "").casefold() == str(contact.get("email") or "").casefold()), None)
        if contact_row is None:
            raise GateError(GATE_READBACK, reason="contact_missing")
        for key, value in contact.items():
            compared_contact[key] = _require_equal(f"contact.{key}", value, contact_row.get(key))
    search = duplicate_search(client, {"name": customer.get("name"), "last_name": customer.get("last_name"), "first_name": customer.get("first_name"), "billing_phone": customer.get("billing_phone")})
    if not any(str(item.get("id")) == str(customer_id) for item in search["candidates"]):
        raise GateError(GATE_READBACK, reason="customer_not_discoverable")
    labels = response_labels(client)
    return {
        "id": customer.get("id"),
        "customer_id": customer.get("id"),
        "location_id": location.get("id"),
        "location_customer_id": location.get("customer_id"),
        "customer": compared,
        "location_name": location.get("name"),
        "address": got_address,
        "compared_address": compared_address,
        "contact_id": None if contact_row is None else contact_row.get("id"),
        "contact": compared_contact,
        "contact_count": len(items),
        "status": status,
        "discoverable": True,
        "matched_sent_fields": True,
        **labels,
    }


def post_customer_steps(service: Any, proposal: dict[str, Any], attempt_id: str) -> dict[str, Any]:
    plan = proposal["after"]["documented_request"]
    client = service.client
    store = service.store
    search = duplicate_search(client, proposal["payload"])
    resolve_duplicates(
        search,
        confirmed_new=bool(plan.get("confirmed_new")),
        existing_customer_id=plan.get("existing_customer_id"),
        approved_candidate_ids=(plan.get("duplicate_resolution") or {}).get("candidate_ids"),
    )
    customer_id = str(plan["existing_customer_id"]) if plan.get("existing_customer_id") else None
    recovered_customer = False
    if customer_id is None:
        step_id = _step(store, proposal["proposal_id"], "customer_post", plan["customer"])
        response, diagnostic = _sent_write(lambda: client.create_customer({"customer": plan["customer"]}), client)
        created = response_id(response)
        if created is not None and _id_status_accepted(diagnostic):
            customer_id = str(created)
            _succeed(store, step_id, {"id": created, "response": _public_diagnostic(diagnostic)}, customer_id=customer_id)
        else:
            proved = _prove_new_customer(client, search, proposal["payload"], plan["customer"]) if _mutation_may_have_landed(diagnostic) else {"ok": False, "reason": "response_not_success"}
            if proved.get("ok"):
                customer_id = proved["customer_id"]
                recovered_customer = True
                _succeed(
                    store,
                    step_id,
                    {"id": int(customer_id), "reconciled": True, "location_id": proved["location_id"], "response": _public_diagnostic(diagnostic), "reason": "authoritative_get"},
                    customer_id=customer_id,
                    location_id=proved["location_id"],
                )
            else:
                _ambiguous(store, step_id)
                store.finish_creation_step(
                    step_id,
                    "ambiguous",
                    {"retry": False, "reason": proved.get("reason"), "response": _public_diagnostic(diagnostic)},
                )
                return stop_creation(store, proposal, attempt_id)
    locations = client.list_service_locations(customer_id)
    if not locations.get("complete"):
        raise GateError(GATE_DUPLICATE_SEARCH, path="/service_locations")
    location_rows = locations.get("items") or []
    if plan.get("existing_customer_id"):
        location_id = str(location_rows[0]["id"]) if len(location_rows) == 1 else None
        if location_id is None:
            raise GateError(GATE_READBACK, reason="existing_location_not_unique")
    else:
        created_locations = [row for row in location_rows]
        if len(created_locations) != 1:
            raise GateError(GATE_READBACK, reason="nested_location_not_unique")
        location_id = str(created_locations[0]["id"])
        last = store.creation_journal(proposal["proposal_id"])[-1]
        result = dict(last.get("result") or {})
        result["location_id"] = location_id
        store.finish_creation_step(last["step_id"], "succeeded", result, customer_id=customer_id, location_id=location_id)
    nested_location_id = location_id
    if not _proposal_current(service, proposal):
        return stop_creation(store, proposal, attempt_id)
    if plan.get("location_patch"):
        location = client.get_location(customer_id, location_id)
        address_id = (location.get("address") or {}).get("id")
        if not isinstance(address_id, int) or isinstance(address_id, bool):
            raise GateError(GATE_ADDRESS)
        patch = {
            "service_location": {
                "name": plan["location_patch"]["name"],
                "tax_rate_id": plan["location_patch"]["tax_rate_id"],
                "address_attributes": {"id": address_id, **plan["location_patch"]["address_attributes"]},
            }
        }
        step_id = _step(store, proposal["proposal_id"], "location_patch", patch, customer_id=customer_id, location_id=location_id)
        response, diagnostic = _sent_write(lambda: client.patch_service_location(customer_id, location_id, patch), client)
        if response is None or _public_diagnostic(diagnostic).get("status") not in {200, "unknown"}:
            matched = _location_matches(client, customer_id, location_id, plan["location_patch"])
            if not matched:
                _ambiguous(store, step_id, customer_id=customer_id, location_id=location_id)
                store.finish_creation_step(step_id, "ambiguous", {"retry": False, "reason": "location_patch_unresolved", "response": _public_diagnostic(diagnostic)}, customer_id=customer_id, location_id=location_id)
                return stop_creation(store, proposal, attempt_id)
        _succeed(store, step_id, {"location_id": location_id, "response": _public_diagnostic(diagnostic)}, customer_id=customer_id, location_id=location_id)
    if plan.get("additional_location"):
        if not _proposal_current(service, proposal):
            return stop_creation(store, proposal, attempt_id)
        body = {"service_location": plan["additional_location"]}
        existing_extra = _one_extra_location(client, customer_id, nested_location_id, plan["additional_location"])
        if existing_extra in {"ambiguous", "conflict"}:
            if existing_extra == "conflict":
                _stop_unsent(store, proposal, "location_post", body, "location_field_conflict", customer_id=customer_id, location_id=nested_location_id)
            return stop_creation(store, proposal, attempt_id)
        if existing_extra:
            location_id = existing_extra
        else:
            step_id = _step(store, proposal["proposal_id"], "location_post", body, customer_id=customer_id)
            response, diagnostic = _sent_write(lambda: client.create_service_location(customer_id, body), client)
            new_id = response_id(response) if _id_status_accepted(diagnostic) else None
            if new_id is None:
                found = _one_extra_location(client, customer_id, nested_location_id, plan["additional_location"])
                if not found or found in {"ambiguous", "conflict"}:
                    reason = "location_field_conflict" if found == "conflict" else "location_post_unresolved"
                    _ambiguous(store, step_id, customer_id=customer_id, location_id=location_id)
                    store.finish_creation_step(step_id, "ambiguous", {"retry": False, "reason": reason, "response": _public_diagnostic(diagnostic)}, customer_id=customer_id, location_id=location_id)
                    return stop_creation(store, proposal, attempt_id)
                new_id = int(found)
            location_id = str(new_id)
            _succeed(store, step_id, {"id": int(location_id), "response": _public_diagnostic(diagnostic)}, customer_id=customer_id, location_id=location_id)
    contact = plan.get("contact")
    contact_id = None
    if contact:
        if not _proposal_current(service, proposal):
            return stop_creation(store, proposal, attempt_id)
        already = _one_contact(client, customer_id, contact)
        if already in {"ambiguous", "conflict"}:
            if already == "conflict":
                _stop_unsent(store, proposal, "contact_post", {"contact": contact}, "contact_field_conflict", customer_id=customer_id, location_id=location_id)
            return stop_creation(store, proposal, attempt_id)
        if already:
            contact_id = int(already)
        else:
            body = {"contact": contact}
            step_id = _step(store, proposal["proposal_id"], "contact_post", body, customer_id=customer_id, location_id=location_id)
            response, diagnostic = _sent_write(lambda: client.create_contact(customer_id, body), client)
            contact_id = response_id(response) if _id_status_accepted(diagnostic) else None
            if contact_id is None:
                found = _one_contact(client, customer_id, contact)
                if not found or found in {"ambiguous", "conflict"}:
                    reason = "contact_field_conflict" if found == "conflict" else "contact_post_unresolved"
                    _ambiguous(store, step_id, customer_id=customer_id, location_id=location_id)
                    store.finish_creation_step(step_id, "ambiguous", {"retry": False, "reason": reason, "response": _public_diagnostic(diagnostic)}, customer_id=customer_id, location_id=location_id)
                    return stop_creation(store, proposal, attempt_id)
                contact_id = int(found)
            _succeed(store, step_id, {"id": contact_id, "response": _public_diagnostic(diagnostic)}, customer_id=customer_id, contact_id=str(contact_id), location_id=location_id)
    address = None if not plan.get("location_patch") else plan["location_patch"]["address_attributes"]
    readback = customer_readback(
        client,
        customer_id,
        sent_customer=plan["customer"],
        contact=contact,
        location_id=nested_location_id,
        address=address,
        wrote_customer=not plan.get("existing_customer_id"),
    )
    if plan.get("additional_location"):
        extra = client.get_location(customer_id, location_id)
        if str(extra.get("id")) != str(location_id) or str(extra.get("customer_id")) != str(customer_id):
            raise GateError(GATE_READBACK, reason="additional_location_identity")
        wanted = plan["additional_location"]
        if extra.get("name") != wanted.get("name") or extra.get("tax_rate_id") != wanted.get("tax_rate_id"):
            raise GateError(GATE_READBACK, reason="additional_location_mismatch")
        extra_address = extra.get("address") if isinstance(extra.get("address"), dict) else {}
        for key, value in (wanted.get("address_attributes") or {}).items():
            if extra_address.get(key) != value:
                raise GateError(GATE_READBACK, reason="additional_location_address_mismatch", field=key)
        readback["additional_location_id"] = extra.get("id")
        readback["additional_location_customer_id"] = extra.get("customer_id")
    if contact_id is not None:
        readback["contact_id"] = contact_id
    return {"ok": True, "readback": readback, "created_id": int(customer_id), "reconciled": recovered_customer}


def _public_diagnostic(diagnostic: dict[str, Any] | None) -> dict[str, Any]:
    diagnostic = diagnostic or {}
    status = diagnostic.get("status", "unknown")
    if status is None:
        status = "unknown"
    keys = diagnostic.get("top_level_keys") if isinstance(diagnostic.get("top_level_keys"), list) else []
    return {
        "status": status,
        "content_type": str(diagnostic.get("content_type") or "unknown").split(";")[0][:80],
        "top_level_keys": [str(key) for key in keys][:40],
        "parser_stage": str(diagnostic.get("parser_stage") or "unknown"),
        "response_body_retained": False,
    }


def _sent_write(call: Any, client: Any) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    try:
        response = call()
    except AmbiguousWriteError as exc:
        return None, _public_diagnostic(exc.diagnostic)
    return response if isinstance(response, dict) else {}, _public_diagnostic(getattr(client, "last_write_diagnostic", None))


def _id_status_accepted(diagnostic: dict[str, Any]) -> bool:
    return diagnostic.get("status") in {200, 201, "unknown"}


def _mutation_may_have_landed(diagnostic: dict[str, Any]) -> bool:
    status = diagnostic.get("status")
    if status in {200, 201, 204, "unknown"}:
        return True
    return isinstance(status, int) and status >= 500


def _proposal_current(service: Any, proposal: dict[str, Any]) -> bool:
    from datetime import datetime, timezone

    expires = datetime.fromisoformat(str(proposal["expires_at"]).replace("Z", "+00:00"))
    now = service._now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return expires > now


def _customer_matches(customer: dict[str, Any], sent: dict[str, Any]) -> bool:
    if customer.get("customer_type") != sent.get("customer_type"):
        return False
    status = str(customer.get("status") or customer.get("customer_status") or "").strip().lower()
    if status != "active":
        return False
    for key in ("first_name", "last_name", "name"):
        if key in sent and customer.get(key) != sent.get(key):
            return False
    if "billing_phone" in sent and normalize_phone(customer.get("billing_phone")) != normalize_phone(sent.get("billing_phone")):
        return False
    address = customer.get("billing_address") if isinstance(customer.get("billing_address"), dict) else {}
    for key, short in (("billing_street", "street"), ("billing_city", "city"), ("billing_state", "state"), ("billing_zip", "zip")):
        if key not in sent:
            continue
        got = customer.get(key)
        if got in (None, ""):
            got = address.get(short)
        if got != sent[key]:
            return False
    return True


def _owned(row: dict[str, Any], customer_id: str, row_id: str) -> bool:
    return response_id({"id": row.get("id")}) is not None and str(row.get("id")) == str(row_id) and str(row.get("customer_id")) == str(customer_id)


def _address_equal(address: dict[str, Any], sent: dict[str, Any]) -> bool:
    for key, value in sent.items():
        if address.get(key) != value:
            return False
    return True


def _primary_location_matches(location: dict[str, Any], sent: dict[str, Any], customer_id: str, location_id: str) -> bool:
    nested = (sent.get("service_locations_attributes") or [{}])[0]
    if not _owned(location, customer_id, location_id):
        return False
    if location.get("name") != nested.get("name") or location.get("same_as_billing_address") is not nested.get("same_as_billing_address"):
        return False
    if nested.get("same_as_billing_address") is True:
        address = location.get("address") if isinstance(location.get("address"), dict) else {}
        expected = {
            addr_key: sent[src]
            for src, addr_key in (("billing_street", "street"), ("billing_street2", "street2"), ("billing_city", "city"), ("billing_state", "state"), ("billing_zip", "zip"), ("billing_county", "county"))
            if src in sent
        }
        if not _address_equal(address, expected):
            return False
    return True


def _prove_new_customer(client: Any, before: dict[str, Any], payload: dict[str, Any], sent: dict[str, Any]) -> dict[str, Any]:
    try:
        after = duplicate_search(client, payload)
    except GateError:
        return {"ok": False, "reason": "duplicate_search_incomplete"}
    previous = {str(item.get("id")) for item in before.get("candidates") or []}
    fresh = [item for item in after["candidates"] if str(item.get("id")) not in previous]
    if len(fresh) != 1:
        if len(fresh) > 1:
            return {"ok": False, "reason": "multiple_new_matches"}
        if any(str(item.get("id")) in previous for item in after["candidates"]):
            return {"ok": False, "reason": "preexisting_match"}
        return {"ok": False, "reason": "no_new_match"}
    customer_id = str(fresh[0]["id"])
    try:
        customer = client.get_customer(customer_id)
        locations = client.list_service_locations(customer_id)
    except GateError:
        return {"ok": False, "reason": "authoritative_read_failed"}
    if str(customer.get("id")) != customer_id or response_id({"id": customer.get("id")}) is None or not _customer_matches(customer, sent):
        return {"ok": False, "reason": "identity_not_proved"}
    if not locations.get("complete") or locations.get("truncated") or locations.get("repeated_page"):
        return {"ok": False, "reason": "duplicate_search_incomplete"}
    rows = locations.get("items") or []
    if len(rows) != 1 or response_id({"id": rows[0].get("id")}) is None:
        return {"ok": False, "reason": "identity_not_proved"}
    location_id = str(rows[0]["id"])
    try:
        location = client.get_location(customer_id, location_id)
    except GateError:
        return {"ok": False, "reason": "authoritative_read_failed"}
    if not _primary_location_matches(location, sent, customer_id, location_id):
        return {"ok": False, "reason": "identity_not_proved"}
    return {"ok": True, "customer_id": customer_id, "location_id": location_id}


def _contact_kind(item: dict[str, Any], contact: dict[str, Any], customer_id: str) -> str:
    if str(item.get("email") or "").casefold() != str(contact.get("email") or "").casefold() or item.get("first_name") != contact.get("first_name") or item.get("last_name") != contact.get("last_name"):
        return "different"
    if response_id({"id": item.get("id")}) is None or str(item.get("customer_id")) != str(customer_id):
        return "conflict"
    for key, value in contact.items():
        if key == "phone":
            if normalize_phone(item.get(key)) != normalize_phone(value):
                return "conflict"
        elif item.get(key) != value:
            return "conflict"
    return "match"


def _one_contact(client: Any, customer_id: str, contact: dict[str, Any]) -> str | None:
    try:
        listed = client.list_contacts(customer_id)
    except GateError:
        return "ambiguous"
    if not listed.get("complete") or listed.get("truncated") or listed.get("repeated_page"):
        return "ambiguous"
    kinds = [_contact_kind(item, contact, customer_id) for item in listed.get("items") or [] if isinstance(item, dict)]
    if "conflict" in kinds or kinds.count("match") > 1:
        return "conflict"
    if kinds.count("match") == 1:
        item = next(row for row in listed.get("items") or [] if isinstance(row, dict) and _contact_kind(row, contact, customer_id) == "match")
        return str(item["id"])
    return None


def _extra_kind(location: dict[str, Any], wanted: dict[str, Any], customer_id: str) -> str:
    if location.get("name") != wanted.get("name"):
        return "different"
    if response_id({"id": location.get("id")}) is None or str(location.get("customer_id")) != str(customer_id):
        return "conflict"
    if location.get("tax_rate_id") != wanted.get("tax_rate_id"):
        return "conflict"
    address = location.get("address") if isinstance(location.get("address"), dict) else {}
    if not _address_equal(address, wanted.get("address_attributes") or {}):
        return "conflict"
    return "match"


def _one_extra_location(client: Any, customer_id: str, nested_location_id: str, wanted: dict[str, Any]) -> str | None:
    try:
        listed = client.list_service_locations(customer_id)
    except GateError:
        return "ambiguous"
    if not listed.get("complete") or listed.get("truncated") or listed.get("repeated_page"):
        return "ambiguous"
    kinds: list[str] = []
    matched: str | None = None
    for item in listed.get("items") or []:
        if not isinstance(item, dict) or str(item.get("id")) == str(nested_location_id):
            continue
        if item.get("name") != wanted.get("name"):
            continue
        try:
            location = client.get_location(customer_id, str(item.get("id")))
        except GateError:
            return "ambiguous"
        kind = "conflict" if str(location.get("id")) != str(item.get("id")) else _extra_kind(location, wanted, customer_id)
        kinds.append(kind)
        if kind == "match":
            matched = str(location.get("id"))
    if "conflict" in kinds or kinds.count("match") != (1 if matched else 0):
        return "conflict" if kinds else None
    return matched


def _location_matches(client: Any, customer_id: str, location_id: str, patch: dict[str, Any]) -> bool:
    try:
        location = client.get_location(customer_id, location_id)
    except GateError:
        return False
    if not _owned(location, customer_id, location_id):
        return False
    if location.get("name") != patch.get("name") or location.get("tax_rate_id") != patch.get("tax_rate_id"):
        return False
    address = location.get("address") if isinstance(location.get("address"), dict) else {}
    expected = {key: value for key, value in (patch.get("address_attributes") or {}).items() if key != "id"}
    return _address_equal(address, expected)


def _stop_unsent(store: Any, proposal: dict[str, Any], step: str, intent: dict[str, Any], reason: str, **ids: str | None) -> None:
    step_id = _step(store, proposal["proposal_id"], step, intent, **ids)
    store.finish_creation_step(
        step_id,
        "ambiguous",
        {"retry": False, "reason": reason, "sent": False, "response": {"status": "unknown", "content_type": "unknown", "top_level_keys": [], "parser_stage": "not_sent", "response_body_retained": False}},
        customer_id=ids.get("customer_id"),
        contact_id=ids.get("contact_id"),
        location_id=ids.get("location_id"),
    )


def _reconcile_customer(client: Any, before: dict[str, Any], payload: dict[str, Any]) -> str | None:
    try:
        after = duplicate_search(client, payload)
    except GateError:
        return None
    previous = {str(item.get("id")) for item in before.get("candidates") or []}
    fresh = [item for item in after["candidates"] if str(item.get("id")) not in previous]
    if len(fresh) == 1 and fresh[0].get("id") is not None:
        return str(fresh[0]["id"])
    return None


def _same_instant(sent: str, got: Any) -> bool:
    if str(got) == str(sent):
        return True
    if "T" not in str(sent):
        return str(got) == str(sent) or str(got).startswith(str(sent))
    from datetime import datetime

    try:
        left = datetime.fromisoformat(str(sent))
        right = datetime.fromisoformat(str(got).replace("Z", "+00:00"))
    except ValueError:
        return False
    return left.tzinfo is not None and right.tzinfo is not None and left == right


def work_order_readback(client: Any, sent: dict[str, Any], occurrence_id: str) -> dict[str, Any]:
    row = client.get_work_order(occurrence_id)
    appointment_id = row.get("service_appointment_id")
    if response_id({"id": row.get("id")}) is None or response_id({"id": appointment_id}) is None:
        raise GateError(GATE_READBACK, reason="ids_missing")
    if str(row.get("id")) == str(appointment_id):
        raise GateError(GATE_DISTINCT_IDS)
    if str(row.get("id")) != str(occurrence_id):
        _mismatch("occurrence_id", occurrence_id, row.get("id"))
    occurrence = sent["appointment_occurrences_attributes"][0]
    schedule = schedule_view(client, str(occurrence["starts_at"]), list(occurrence["service_route_ids"]))
    if str(row.get("id")) not in {str(item.get("id")) for item in schedule["conflicts"]}:
        raise GateError(GATE_READBACK, reason="occurrence_not_on_schedule")
    _require_equal("customer_id", sent["customer_id"], row.get("customer_id"))
    _require_equal("service_location_id", sent["service_location_id"], row.get("service_location_id"))
    actual_start = row.get("starts_at")
    if not _same_instant(str(occurrence["starts_at"]), actual_start) and str(row.get("starts_at_date") or "") != str(occurrence["starts_at"]):
        _mismatch("starts_at", occurrence["starts_at"], actual_start)
    _require_equal("duration", occurrence.get("duration"), row.get("duration"))
    _require_equal("service_route_ids", list(occurrence["service_route_ids"]), list(row.get("service_route_ids") or []))
    _require_equal("instructions", occurrence.get("instructions"), row.get("instructions"))
    if not money_equal(occurrence.get("production_value"), row.get("production_value")):
        _mismatch("production_value", occurrence.get("production_value"), row.get("production_value"))
    sent_lines = sent["line_items_attributes"]
    got_lines = row.get("line_items") or []
    if len(got_lines) != len(sent_lines):
        raise GateError(GATE_READBACK, reason="line_item_count_mismatch")
    compared_lines = []
    for sent_line, got_line in zip(sent_lines, got_lines):
        compared = {
            "payable_id": _require_equal("payable_id", sent_line.get("payable_id"), got_line.get("payable_id")),
            "payable_type": _require_equal("payable_type", sent_line.get("payable_type"), got_line.get("payable_type")),
            "type": _require_equal("type", sent_line.get("type"), got_line.get("type")),
            "name": _require_equal("name", sent_line.get("name"), got_line.get("name")),
            "taxable": _require_equal("taxable", sent_line.get("taxable"), got_line.get("taxable")),
        }
        if not money_equal(sent_line.get("quantity"), got_line.get("quantity")) or not money_equal(sent_line.get("price"), got_line.get("price")):
            _mismatch("price", sent_line.get("price"), got_line.get("price"))
        sent_total = money(sent_line["quantity"]) * money(sent_line["price"])
        got_total = money(got_line["quantity"]) * money(got_line["price"])
        if sent_total != got_total:
            _mismatch("line_total", sent_total, got_total)
        compared["quantity"] = got_line.get("quantity")
        compared["price"] = got_line.get("price")
        compared["total"] = int(got_total) if got_total == got_total.to_integral_value() else format(got_total, "f")
        compared_lines.append(compared)
    labels = response_labels(client)
    return {
        "id": row.get("id"),
        "occurrence_id": row.get("id"),
        "service_appointment_id": appointment_id,
        "customer_id": row.get("customer_id"),
        "service_location_id": row.get("service_location_id"),
        "starts_at": actual_start,
        "timezone": "America/New_York",
        "clock_time_sent": "T" in str(occurrence["starts_at"]),
        "duration": row.get("duration"),
        "production_value": row.get("production_value"),
        "service_route_ids": row.get("service_route_ids"),
        "instructions": row.get("instructions"),
        "price": compared_lines[0]["price"],
        "line_total": compared_lines[0]["total"],
        "line_items": compared_lines,
        "service_name": compared_lines[0]["name"],
        "after_state": {
            "occurrence_id": row.get("id"),
            "service_appointment_id": appointment_id,
            "starts_at": actual_start,
            "duration": row.get("duration"),
            "production_value": row.get("production_value"),
            "line_items": compared_lines,
        },
        "promised_window_enforced": False,
        "matched_sent_fields": True,
        "schedule_complete": True,
        **labels,
    }


def post_work_order(service: Any, proposal: dict[str, Any], attempt_id: str) -> dict[str, Any]:
    client = service.client
    store = service.store
    sent = proposal["after"]["documented_request"]["service_appointment"]
    schedule_patch = proposal["after"].get("schedule_patch")
    if proposal["after"].get("starts_at_post_ready") is False and not schedule_patch:
        raise GateError(GATE_STARTS_AT_POST, starts_at_post_clock_live_tested=False, timed_create_ready=False, first_live_creation_approval_required=True)
    catalog = load_catalog(client, proposal["after"].get("template_id"))
    rebuilt = apply_catalog(proposal["after"]["caller_appointment"], catalog)
    if rebuilt["service_appointment"] != sent:
        raise GateError("stale_state", reason="template_changed")
    service._require_active_location(proposal["payload"])
    occurrence = sent["appointment_occurrences_attributes"][0]
    schedule_at = str((schedule_patch or {}).get("starts_at") or occurrence["starts_at"])
    current_schedule = schedule_view(client, schedule_at, list(occurrence["service_route_ids"]))
    approved_schedule = proposal["after"].get("schedule") or {}
    if schedule_signature(current_schedule) != schedule_signature(approved_schedule):
        raise GateError("stale_state", reason="schedule_changed")
    before = current_schedule
    route_staff(client, list(occurrence["service_route_ids"]))
    step_id = _step(store, proposal["proposal_id"], "work_order_post", sent, customer_id=str(sent["customer_id"]), location_id=str(sent["service_location_id"]))
    try:
        response = client.create_work_order({"service_appointment": sent})
    except AmbiguousWriteError:
        _ambiguous(store, step_id, customer_id=str(sent["customer_id"]), location_id=str(sent["service_location_id"]))
        reconciled = _reconcile_work_order(client, sent, before)
        if reconciled is None:
            return stop_creation(store, proposal, attempt_id)
        store.finish_creation_step(step_id, "succeeded", {"reconciled": True, "occurrence_id": int(reconciled)}, customer_id=str(sent["customer_id"]), location_id=str(sent["service_location_id"]))
        row = client.get_work_order(reconciled)
        appointment_id = row.get("service_appointment_id")
        if response_id({"id": appointment_id}) is None or str(reconciled) == str(appointment_id):
            return stop_creation(store, proposal, attempt_id)
        sent = _finish_schedule_patch(service, proposal, attempt_id, sent, reconciled, appointment_id)
        if not isinstance(sent, dict):
            return sent
        readback = work_order_readback(client, sent, reconciled)
        return {"ok": True, "readback": readback, "created_id": readback["occurrence_id"], "reconciled": True}
    created = response_id(response)
    appointment_id = response.get("service_appointment_id") if isinstance(response, dict) else None
    if created is None or response_id({"id": appointment_id}) is None or str(created) == str(appointment_id):
        _ambiguous(store, step_id, customer_id=str(sent["customer_id"]), location_id=str(sent["service_location_id"]))
        stopped = stop_creation(store, proposal, attempt_id)
        if created is None or response_id({"id": appointment_id}) is None:
            stopped["gate"] = "create_response_unverified"
        elif str(created) == str(appointment_id):
            stopped["gate"] = GATE_DISTINCT_IDS
        return stopped
    _succeed(store, step_id, {"occurrence_id": created, "service_appointment_id": appointment_id}, customer_id=str(sent["customer_id"]), location_id=str(sent["service_location_id"]))
    sent = _finish_schedule_patch(service, proposal, attempt_id, sent, str(created), appointment_id)
    if not isinstance(sent, dict):
        return sent
    readback = work_order_readback(client, sent, str(created))
    return {"ok": True, "readback": readback, "created_id": created}


def _finish_schedule_patch(service: Any, proposal: dict[str, Any], attempt_id: str, sent: dict[str, Any], occurrence_id: str, appointment_id: Any) -> dict[str, Any]:
    patch = proposal["after"].get("schedule_patch")
    if not patch:
        return sent
    if not _proposal_current(service, proposal):
        return stop_creation(service.store, proposal, attempt_id)
    client = service.client
    store = service.store
    before = {"work_order_id": occurrence_id, "service_appointment_id": appointment_id}
    after = {"starts_at": patch["starts_at"], "duration": patch["duration"], "service_route_ids": list(patch["service_route_ids"])}
    step_id = _step(store, proposal["proposal_id"], "work_order_schedule_patch", after, customer_id=str(sent["customer_id"]), location_id=str(sent["service_location_id"]))
    try:
        client.patch_work_order_fields(before, after, ["starts_at", "duration", "service_route_ids"])
    except AmbiguousWriteError:
        if not _schedule_patch_landed(client, occurrence_id, appointment_id, patch):
            _ambiguous(store, step_id, customer_id=str(sent["customer_id"]), location_id=str(sent["service_location_id"]))
            store.finish_creation_step(step_id, "ambiguous", {"retry": False, "reason": "schedule_patch_unresolved"}, customer_id=str(sent["customer_id"]), location_id=str(sent["service_location_id"]))
            return stop_creation(store, proposal, attempt_id)
    _succeed(store, step_id, {"occurrence_id": int(occurrence_id), "service_appointment_id": int(appointment_id)}, customer_id=str(sent["customer_id"]), location_id=str(sent["service_location_id"]))
    timed = dict(sent)
    occurrence = dict(sent["appointment_occurrences_attributes"][0])
    occurrence["starts_at"] = patch["starts_at"]
    occurrence["duration"] = patch["duration"]
    occurrence["service_route_ids"] = list(patch["service_route_ids"])
    timed["appointment_occurrences_attributes"] = [occurrence]
    return timed


def _schedule_patch_landed(client: Any, occurrence_id: str, appointment_id: Any, patch: dict[str, Any]) -> bool:
    try:
        row = client.get_work_order(str(occurrence_id))
    except GateError:
        return False
    if str(row.get("id")) != str(occurrence_id) or str(row.get("service_appointment_id")) != str(appointment_id):
        return False
    return _same_instant(str(patch["starts_at"]), row.get("starts_at")) and row.get("duration") == patch["duration"] and list(row.get("service_route_ids") or []) == list(patch["service_route_ids"])


def _reconcile_work_order(client: Any, sent: dict[str, Any], before: dict[str, Any]) -> str | None:
    occurrence = sent["appointment_occurrences_attributes"][0]
    try:
        after = schedule_view(client, str(occurrence["starts_at"]), list(occurrence["service_route_ids"]))
    except GateError:
        return None
    previous = {str(item.get("id")) for item in before.get("conflicts") or []}
    fresh = [item for item in after["conflicts"] if str(item.get("id")) not in previous and str(item.get("customer_id")) == str(sent["customer_id"])]
    if len(fresh) != 1:
        return None
    return str(fresh[0]["id"])
