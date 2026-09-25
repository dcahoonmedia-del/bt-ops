"""Duplicate checks, creation journal, and catalog-backed work orders. Fake transport only."""

from __future__ import annotations

import re
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
    pages = _search_pages(client, "/customers/search", {"query": next(iter(wanted_names), "")})
    rows = list(pages["items"])
    seen = {str(row.get("id")) for row in rows}
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


def resolve_duplicates(search: dict[str, Any], *, confirmed_new: bool, existing_customer_id: int | None) -> dict[str, Any]:
    candidates = search["candidates"]
    if confirmed_new and existing_customer_id is not None:
        raise GateError("unknown_field", fields=["confirmed_new", "existing_customer_id"])
    if candidates and not confirmed_new and existing_customer_id is None:
        raise GateError(GATE_DUPLICATE_UNRESOLVED, candidates=candidates)
    if existing_customer_id is not None and not any(str(item.get("id")) == str(existing_customer_id) for item in candidates):
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
    if str(template.get("repeat_type") or "") != "none":
        raise GateError(GATE_RECURRING)
    if template.get("tax_amount") not in (0, None) or template.get("discount") not in (0, None):
        raise GateError(GATE_TAXABLE, reason="template_tax_not_accepted")
    if template.get("billing_frequency") not in (0, None):
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
    if service.get("description") != line.get("name") or service.get("price") != line.get("price"):
        raise GateError(GATE_CATALOG, reason="service_disagrees_with_template")
    if line.get("type") != "service" or line.get("payable_type") != "Service":
        raise GateError(GATE_CATALOG, reason="template_line_type")
    return {"template": template, "line": line, "service": {"id": service.get("id"), "description": service.get("description"), "price": service.get("price")}}


def apply_catalog(appointment: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    template = catalog["template"]
    line = catalog["line"]
    sent_line = {
        "name": line.get("name"),
        "type": line.get("type"),
        "quantity": line.get("quantity"),
        "price": line.get("price"),
        "payable_id": line.get("payable_id"),
        "payable_type": line.get("payable_type"),
        "taxable": False if line.get("taxable") is False else line.get("taxable"),
    }
    supplied = appointment.get("line_items_attributes")
    if supplied is not None and supplied != [sent_line]:
        raise GateError(GATE_CATALOG, reason="caller_line_disagrees_with_template")
    occurrence = dict(appointment["appointment_occurrences_attributes"][0])
    if "duration" not in occurrence and template.get("duration") is not None:
        occurrence["duration"] = template["duration"]
    if "instructions" not in occurrence and template.get("instructions") is not None:
        occurrence["instructions"] = template["instructions"]
    if "production_value" not in occurrence and template.get("production_value") is not None:
        occurrence["production_value"] = template["production_value"]
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
    return {"service_appointment": body}


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


def schedule_view(client: Any, starts_at: str, route_ids: list[int]) -> dict[str, Any]:
    try:
        found = client.list_work_orders(start_date=starts_at, end_date=starts_at, service_route_ids=route_ids)
    except GateError as exc:
        raise GateError(GATE_SCHEDULE) from exc
    if not found.get("complete") or found.get("truncated") or found.get("repeated_page") or found.get("partial_error"):
        raise GateError(GATE_SCHEDULE, truncated=bool(found.get("truncated")), repeated_page=bool(found.get("repeated_page")))
    return {
        "date": starts_at,
        "timezone": "America/New_York",
        "clock_time_sent": False,
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


def customer_readback(client: Any, customer_id: str, *, contact: dict[str, Any] | None, location_id: str, address: dict[str, Any] | None) -> dict[str, Any]:
    customer = client.get_customer(customer_id)
    status = str(customer.get("status") or customer.get("customer_status") or "").strip().lower()
    if status != "active":
        raise GateError(GATE_READBACK, reason="customer_not_active", status=status)
    location = client.get_location(customer_id, location_id)
    if str(location.get("id")) != str(location_id):
        raise GateError(GATE_READBACK, reason="location_missing")
    if address:
        got = (location.get("address") or {})
        for key, value in address.items():
            if got.get(key) != value:
                raise GateError(GATE_READBACK, reason="address_mismatch", field=key)
    contacts = client.list_contacts(customer_id)
    if not contacts.get("complete") or contacts.get("truncated") or contacts.get("repeated_page"):
        raise GateError(GATE_READBACK, reason="contact_list_incomplete")
    items = contacts.get("items") or []
    if contact is None:
        contact_row = None
    else:
        contact_row = next((item for item in items if str(item.get("email") or "").casefold() == str(contact["email"]).casefold()), None)
        if contact_row is None:
            raise GateError(GATE_READBACK, reason="contact_missing")
    search = duplicate_search(client, {"name": customer.get("name"), "last_name": customer.get("last_name"), "billing_phone": customer.get("billing_phone")})
    if not any(str(item.get("id")) == str(customer_id) for item in search["candidates"]):
        raise GateError(GATE_READBACK, reason="customer_not_discoverable")
    return {
        "id": customer.get("id"),
        "customer_id": customer.get("id"),
        "location_id": location.get("id"),
        "contact_id": None if contact_row is None else contact_row.get("id"),
        "contact_count": len(items),
        "status": status,
        "discoverable": True,
        "test_double": True,
        "response_schema": "fake_test_double_not_live_schema",
        "response_schema_verified": False,
        "matched_sent_fields": True,
    }


def post_customer_steps(service: Any, proposal: dict[str, Any], attempt_id: str) -> dict[str, Any]:
    plan = proposal["after"]["documented_request"]
    client = service.client
    store = service.store
    search = duplicate_search(client, proposal["payload"])
    resolve_duplicates(search, confirmed_new=bool(plan.get("confirmed_new")), existing_customer_id=plan.get("existing_customer_id"))
    customer_id = str(plan["existing_customer_id"]) if plan.get("existing_customer_id") else None
    if customer_id is None:
        step_id = _step(store, proposal["proposal_id"], "customer_post", plan["customer"])
        try:
            response = client.create_customer({"customer": plan["customer"]})
        except AmbiguousWriteError:
            _ambiguous(store, step_id)
            found = _reconcile_customer(client, search, proposal["payload"])
            if found:
                store.finish_creation_step(step_id, "ambiguous", {"reconciled_customer_id": found}, customer_id=found)
            return stop_creation(store, proposal, attempt_id)
        created = response_id(response)
        if created is None:
            _ambiguous(store, step_id)
            return stop_creation(store, proposal, attempt_id)
        customer_id = str(created)
        _succeed(store, step_id, {"id": created}, customer_id=customer_id)
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
        store.finish_creation_step(store.creation_journal(proposal["proposal_id"])[-1]["step_id"], "succeeded", {"location_id": location_id}, customer_id=customer_id, location_id=location_id)
    nested_location_id = location_id
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
        try:
            client.patch_service_location(customer_id, location_id, patch)
        except AmbiguousWriteError:
            _ambiguous(store, step_id, customer_id=customer_id, location_id=location_id)
            return stop_creation(store, proposal, attempt_id)
        _succeed(store, step_id, {"location_id": location_id}, customer_id=customer_id, location_id=location_id)
    if plan.get("additional_location"):
        body = {"service_location": plan["additional_location"]}
        step_id = _step(store, proposal["proposal_id"], "location_post", body, customer_id=customer_id)
        try:
            response = client.create_service_location(customer_id, body)
        except AmbiguousWriteError:
            _ambiguous(store, step_id, customer_id=customer_id, location_id=location_id)
            return stop_creation(store, proposal, attempt_id)
        new_id = response_id(response)
        if new_id is None:
            _ambiguous(store, step_id, customer_id=customer_id, location_id=location_id)
            return stop_creation(store, proposal, attempt_id)
        location_id = str(new_id)
        _succeed(store, step_id, {"id": new_id}, customer_id=customer_id, location_id=location_id)
    contact = plan.get("contact")
    contact_id = None
    if contact:
        body = {"contact": contact}
        step_id = _step(store, proposal["proposal_id"], "contact_post", body, customer_id=customer_id, location_id=location_id)
        try:
            response = client.create_contact(customer_id, body)
        except AmbiguousWriteError:
            _ambiguous(store, step_id, customer_id=customer_id, location_id=location_id)
            return stop_creation(store, proposal, attempt_id)
        contact_id = response_id(response)
        if contact_id is None:
            _ambiguous(store, step_id, customer_id=customer_id, location_id=location_id)
            return stop_creation(store, proposal, attempt_id)
        _succeed(store, step_id, {"id": contact_id}, customer_id=customer_id, contact_id=str(contact_id), location_id=location_id)
    address = None if not plan.get("location_patch") else plan["location_patch"]["address_attributes"]
    readback = customer_readback(client, customer_id, contact=contact, location_id=nested_location_id, address=address)
    if plan.get("additional_location"):
        extra = client.get_location(customer_id, location_id)
        if str(extra.get("id")) != str(location_id) or extra.get("name") != plan["additional_location"]["name"]:
            raise GateError(GATE_READBACK, reason="additional_location_missing")
        if extra.get("tax_rate_id") != plan["additional_location"]["tax_rate_id"]:
            raise GateError(GATE_READBACK, reason="additional_location_tax_mismatch")
        readback["additional_location_id"] = extra.get("id")
    if contact_id is not None:
        readback["contact_id"] = contact_id
    return {"ok": True, "readback": readback, "created_id": int(customer_id)}


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


def work_order_readback(client: Any, sent: dict[str, Any], occurrence_id: str) -> dict[str, Any]:
    row = client.get_work_order(occurrence_id)
    appointment_id = row.get("service_appointment_id")
    if response_id({"id": row.get("id")}) is None or response_id({"id": appointment_id}) is None:
        raise GateError(GATE_READBACK, reason="ids_missing")
    if str(row.get("id")) == str(appointment_id):
        raise GateError(GATE_DISTINCT_IDS)
    occurrence = sent["appointment_occurrences_attributes"][0]
    schedule = schedule_view(client, str(occurrence["starts_at"]), list(occurrence["service_route_ids"]))
    if str(row.get("id")) not in {str(item.get("id")) for item in schedule["conflicts"]}:
        raise GateError(GATE_READBACK, reason="occurrence_not_on_schedule")
    if str(row.get("customer_id")) != str(sent["customer_id"]) or str(row.get("service_location_id")) != str(sent["service_location_id"]):
        raise GateError(GATE_READBACK, reason="association_mismatch")
    if str(row.get("starts_at_date") or row.get("starts_at")) != str(occurrence["starts_at"]):
        raise GateError(GATE_READBACK, reason="date_mismatch")
    if row.get("duration") != occurrence.get("duration"):
        raise GateError(GATE_READBACK, reason="duration_mismatch")
    if list(row.get("service_route_ids") or []) != list(occurrence["service_route_ids"]):
        raise GateError(GATE_READBACK, reason="route_mismatch")
    if row.get("instructions") != occurrence.get("instructions"):
        raise GateError(GATE_READBACK, reason="instructions_mismatch")
    sent_line = sent["line_items_attributes"][0]
    got_line = (row.get("line_items") or [{}])[0]
    if got_line.get("price") != sent_line.get("price") or got_line.get("name") != sent_line.get("name"):
        raise GateError(GATE_READBACK, reason="service_price_mismatch")
    return {
        "id": row.get("id"),
        "occurrence_id": row.get("id"),
        "service_appointment_id": appointment_id,
        "customer_id": row.get("customer_id"),
        "service_location_id": row.get("service_location_id"),
        "starts_at": occurrence["starts_at"],
        "timezone": "America/New_York",
        "clock_time_sent": False,
        "duration": row.get("duration"),
        "service_route_ids": row.get("service_route_ids"),
        "instructions": row.get("instructions"),
        "price": got_line.get("price"),
        "service_name": got_line.get("name"),
        "promised_window_enforced": False,
        "test_double": True,
        "response_schema": "fake_test_double_not_live_schema",
        "response_schema_verified": False,
        "matched_sent_fields": True,
        "schedule_complete": True,
    }


def post_work_order(service: Any, proposal: dict[str, Any], attempt_id: str) -> dict[str, Any]:
    client = service.client
    store = service.store
    sent = proposal["after"]["documented_request"]["service_appointment"]
    catalog = load_catalog(client, proposal["after"].get("template_id"))
    rebuilt = apply_catalog(proposal["after"]["caller_appointment"], catalog)
    if rebuilt["service_appointment"] != sent:
        raise GateError("stale_state", reason="template_changed")
    service._require_active_location(proposal["payload"])
    occurrence = sent["appointment_occurrences_attributes"][0]
    before = schedule_view(client, str(occurrence["starts_at"]), list(occurrence["service_route_ids"]))
    route_staff(client, list(occurrence["service_route_ids"]))
    step_id = _step(store, proposal["proposal_id"], "work_order_post", sent, customer_id=str(sent["customer_id"]), location_id=str(sent["service_location_id"]))
    try:
        response = client.create_work_order({"service_appointment": sent})
    except AmbiguousWriteError:
        _ambiguous(store, step_id, customer_id=str(sent["customer_id"]), location_id=str(sent["service_location_id"]))
        reconciled = _reconcile_work_order(client, sent, before)
        if reconciled is None:
            return stop_creation(store, proposal, attempt_id)
        store.finish_creation_step(step_id, "ambiguous", {"reconciled": True}, customer_id=str(sent["customer_id"]), location_id=str(sent["service_location_id"]))
        try:
            readback = work_order_readback(client, sent, reconciled)
        except GateError:
            return stop_creation(store, proposal, attempt_id)
        store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "success")
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
    readback = work_order_readback(client, sent, str(created))
    return {"ok": True, "readback": readback, "created_id": created}


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
