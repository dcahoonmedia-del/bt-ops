"""Official MCP SDK resource server. OAuth validation is required for HTTP."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer

from .allowlist import FORBIDDEN_OPS, GATE_AUTH, current_gates
from .auth0_bridge import bridge_blockers
from .config import Settings
from .oauth_rs import JwtTokenVerifier, identity_from_claims
from .redact import redact
from .secrets import load_api_key
from .service import WriteService

PUBLIC_INSTRUCTIONS = (
    "Read the Fieldwork record, propose one change, inspect it, and show the user the exact before and after. "
    "Obtain explicit user approval of that before and after. Then execute only with approved=true and the exact digest "
    "from that proposal, and show the readback. Do not execute a draft, a stale proposal, a different proposal, "
    "or a change the user did not approve. "
    "Customer and work-order creation are schema-ready and are not live-tested. "
    "Customer create accepts Residential or Commercial, documented billing fields, and service_locations as one object or a one-item list with only name and same_as_billing_address. That caller wrapper becomes customer[service_locations_attributes] on POST /customers. primary_email is not on the customer POST. After the customer and Main Location are posted, one PATCH sends only customer[invoice_email]. That PATCH was observed once on 2026-09-25 at 17:02 Eastern, HTTP 200, and a same-as-billing Main Location email copied it. Other location configurations and notice delivery are not proven. It is not turned into a contact. An explicit contact still requires first_name, last_name, and email. Location email, location_type_id, and reminders_type 0 go on one documented location PATCH as service_location[reminders_type]=0. A later GET that omits reminders_type is write-sent and readback-unverified. HTTP success does not prove the inactive state. Later invoice and location-email patches do not send reminders_type, and their order is not changed. Persistence of inactive appointment reminders is unresolved. send_report_email is not sent; an inherited true value may still send a completion report once a location email exists. Inactive appointment reminders do not disable every notice. A nonblank billing_phone with omitted billing_phone_kind defaults to Mobile on new-customer creation only. Explicit Home, Office, Mobile, Fax, or Other is preserved. An invalid explicit type is rejected. No phone means no fabricated phone or type. Existing-customer updates and standalone contacts do not receive that default. A supplied email or street has no documented search query. Name and phone are still searched, returned rows are inspected, and creation requires acknowledge_duplicate_coverage for the exact gap. That acknowledgment is not a claim of no duplicates. confirmed_new does not replace it. Omitting the location is nested_location_required, not an unknown service_locations field. "
    "Name and phone duplicate search must finish without a repeated or partial page. Email and street coverage can stay incomplete when acknowledge_duplicate_coverage names that exact gap. That is not a complete no-duplicate result. Possible matches still require confirmed_new or an existing customer id. "
    "Work-order create accepts starts_at, duration, service_route_ids, and instructions on the caller or inside one occurrences item. A missing schedule is missing_field, not unknown_field occurrences. The catalog price is the standard initial price. An explicit line price is the approved amount and is not replaced by that standard. A date-only starts_at is one POST. An offset timestamp is a disclosed date POST plus one schedule PATCH of that instant. POST clock acceptance is not live-tested. No promised arrival window. "
    "If work-order readback fails after those writes, at most two more reads use the same occurrence and service appointment. They do not repeat the POST or the PATCH. "
    "update_customer_primary_email reads the customer and, after explicit approval, sends one customer PATCH of customer[invoice_email]. It does not write a location, a contact, or a portal setting. Same-as-billing location-email copy was observed once and is not proven for every location. Not live-tested. "
    "update_work_order_status reads the work order and GET /v3.1/statuses. The observed custom catalog is a bare array of objects; value is the PATCH string, name is the label, and id is not the write value. The i18n map is a separate label map and is not the write catalog. Unknown or ambiguous statuses are rejected. After explicit approval it sends one PATCH /v3.1/work_orders/{service_appointment_id} with only the work-order id and the catalog status string. HTTP 204 still requires readback. An unavailable or still-prior read uses at most two more GETs and does not send the PATCH again. Catalog membership does not prove transition side effects. No other field is sent. Not live-tested. create_work_order still rejects a caller status. "
    "create_work_order can use another current Service from GET /v3.1/services. A matching price is catalog/default. A different supplied price is explicit_approved_override. Production is independent and is not copied from the price. Omitting production does not invent a price-equivalent value. Another service does not inherit PestGuard duration, instructions, production, repeat period, invoice, or tax, and it does not read the PestGuard template. Generic execution is blocked with service_selectability_unverified. GET /v3.1/services is only Fetches all Services, with no parameters and no response schema, and there is no GET /services/{id}. POST /v3.1/work_orders payable_id does not document catalog selectability. List membership is not an active flag and is not the selection contract. Explicit inactive, disabled, deleted, archived, or contradictory flags fail closed. The PestGuard initial template path stays available when those flags are absent. Active eligibility is unverified when the catalog omits it. Not live-tested. "
    "add_customer_contact reads the customer and contacts, proposes one new contact, and after explicit approval POSTs it once. Email and name whitespace and case are duplicate candidates. The same email with a different person is shared_email_not_merged and is not merged or posted. The customer is read again immediately before the POST. A duplicate or an ambiguous response is not posted again. It does not edit a contact or change portal access or notifications. Not live-tested. "
    "update_customer_phone is not implemented because there is no verified billing-phone PATCH. "
    "Writes stay off unless FIELDWORK_WRITES_ENABLED is set and the live API role is writer. "
    "Work-order note and schedule writes also require FIELDWORK_MAPPING_VERIFIED. GET /check_connection is not auth proof. "
    "MCP execution requires FW_WRITE_APPROVAL_MODE=chatgpt_confirmation. A separate approval string is not accepted."
)

CREATE_CUSTOMER_EXAMPLE = {
    "customer_type": "Residential",
    "last_name": "Example",
    "primary_email": "ada@example.test",
    "billing_street": "1 Example St",
    "billing_city": "Buffalo",
    "billing_state": "NY",
    "billing_zip": "14201",
    "service_locations": {"name": "Main Location", "same_as_billing_address": True},
    "acknowledge_duplicate_coverage": ["address", "email"],
}

PROPOSE_DESCRIPTION = (
    "Prepare one exact before/after proposal and do not change Fieldwork. "
    "Supported: update_service_location_notes(customer_id, location_id, notes); "
    "update_work_order_notes(work_order_id, service_appointment_id, instructions and/or private_notes); "
    "update_work_order_schedule(work_order_id, service_appointment_id, starts_at with a numeric offset, duration minutes, service_route_ids); "
    "create_customer is schema-ready and not live-tested: Residential or Commercial; service_locations is one object or a one-item list with only name and same_as_billing_address, posted as service_locations_attributes; flat billing fields such as billing_street, billing_city, billing_state, and billing_zip stay on the customer; billing_phone stays on the customer; a nonblank billing_phone with omitted billing_phone_kind defaults to Mobile on new-customer creation only and is serialized as customer[billing_phone_kind]; explicit Home, Office, Mobile, Fax, or Other is preserved; an invalid explicit type is rejected; no phone means no fabricated phone or type; existing-customer updates and standalone contacts do not receive that default; primary_email is one later customer PATCH of customer[invoice_email], not a customer POST field and not a contact; contact is only for a separately requested additional contact and is not required for primary_email; location email, property type, and reminders_type 0 are a documented location PATCH of service_location[reminders_type]=0; a GET that omits the field is write-sent and readback-unverified; HTTP success does not prove inactive; later invoice and location-email patches do not send reminders_type; name and phone are the only documented duplicate queries; a supplied email or street stays an incomplete coverage gap unless acknowledge_duplicate_coverage lists that exact gap; that acknowledgment names unsupported or incomplete email and address coverage and does not assert that searches succeeded; the proposal does not claim no duplicates; confirmed_new does not replace that acknowledgment; "
    "Canonical create_customer example, with no contact: " + json.dumps(CREATE_CUSTOMER_EXAMPLE, separators=(",", ":")) + ". "
    "A successful proposal does not mark creation or response schemas live-verified. "
    "create_work_order is schema-ready and not live-tested: one initial occurrence, repeat_type none. starts_at, duration, service_route_ids, and instructions may be top-level or inside one occurrences item. Omitting starts_at or service_route_ids is missing_field. The template service uses its verified catalog price as the standard; a different caller price for that service is an approved override. A caller line for another Service uses that service's verified catalog price as the standard when the caller price matches, and a different caller price is an explicit approved override labeled explicit_approved_override. Equal prices are catalog/default. Another work order's line price is not the catalog price. Production is not derived from price. Another service does not inherit PestGuard duration, instructions, or template defaults, and generic execution stays blocked with service_selectability_unverified because GET /v3.1/services and POST payable_id do not establish catalog membership as selectable. callback is optional and independent. Date-only starts_at is one POST. An offset timestamp posts the calendar date because the saved create spec types starts_at as date, then one PATCH sets the approved offset. That POST clock is not live-tested. No use_time_window, agreement, or recurrence. "
    "A failed work-order readback is followed by at most two more reads of the same occurrence and service appointment and does not repeat the POST or PATCH. creation_live_tested stays false. "
    "update_customer_primary_email(customer_id, primary_email) is separate from create_customer: one customer PATCH of customer[invoice_email] after explicit approval, then GET verification. It does not write a location, a contact, or a portal setting. Same-as-billing location-email copy was observed once and is not proven for every location. Not live-tested. "
    "update_work_order_status(work_order_id, service_appointment_id, status) resolves status through GET /v3.1/statuses. value is the catalog status string, name is only a label, and id is not written. Unknown or ambiguous text is rejected. The approved PATCH sends only the catalog status string. HTTP 204 is a successful empty response and is verified by readback. An unavailable or still-prior read uses at most two more GETs and does not send the PATCH again. The i18n string map is not the write catalog. Transitions are not in the spec. Not live-tested. "
    "add_customer_contact(customer_id, contact) proposes one new contact after reading the customer and existing contacts. Whitespace and case on the email or name are duplicate candidates. A shared family email is reported and is not merged. Approval POSTs that contact once only when the customer still matches and no candidate exists. Duplicates and ambiguous responses are not retried. No contact edit, portal change, or notification change. Not live-tested. "
    "update_customer_phone is not implemented. There is no verified billing-phone PATCH. "
    "Rejected: lead status, incomplete duplicate search, recurrence, taxable lines, portal or autopay fields, and caller fields started_at_time, finished_at_time, private_notes, status, or use_time_window."
)

EXECUTE_DESCRIPTION = (
    "After the user has explicitly approved the exact before and after shown by inspect_proposal, "
    "execute that one proposal with approved=true and the exact digest. The result includes readback. "
    "Rejects missing approval, a missing or wrong digest, a stale before, an expired proposal, a tampered stored proposal, "
    "another proposal id, or another user's proposal. "
    "Customer create can POST the customer, PATCH a distinct service address, POST one caller-supplied extra location, and POST an explicit contact. add_customer_contact POSTs one contact on an existing customer and does not replay an ambiguous response. Work-order create sends one POST. A timed visit adds one schedule PATCH of the approved offset after distinct ids are known. A later readback failure does not repeat either write. update_customer_primary_email sends one customer PATCH of invoice_email. update_work_order_status sends one status-only PATCH. HTTP 204 is verified by readback, an unavailable or still-prior read uses at most two more GETs, and the PATCH is not sent again. "
    "A crashed or ambiguous POST is not replayed. An ambiguous customer POST is bound only when one new account matches the approved identity on a later GET. Remaining approved contact or location steps continue once in that same execution. A lost contact or location response is read back, not resent. "
    "Creation is schema-ready and not live-tested. Readback is the fake client's echoed records, not a verified live schema. "
    "Requires FW_WRITE_APPROVAL_MODE=chatgpt_confirmation."
)


def _auth_settings(settings: Settings) -> AuthSettings | None:
    if not settings.oauth_ready():
        return None
    return AuthSettings(
        issuer_url=settings.oauth_issuer,  # type: ignore[arg-type]
        resource_server_url=settings.oauth_resource,  # type: ignore[arg-type]
        required_scopes=list(settings.required_scopes),
        validate_token_resource=False,
    )


def request_identity() -> dict[str, str] | None:
    token = get_access_token()
    if token is None:
        return None
    claims = dict(token.claims or {})
    email = str(claims.get("email") or "").strip().lower()
    sub = str(token.subject or claims.get("sub") or "").strip()
    if not email or not sub:
        return None
    return {"sub": sub, "email": email}


def build_mcp(service: WriteService, settings: Settings, verifier: JwtTokenVerifier) -> MCPServer:
    auth = _auth_settings(settings)
    server = MCPServer(
        name="bt-fieldwork-write-mcp",
        title="B&T Fieldwork write MCP",
        instructions=PUBLIC_INSTRUCTIONS,
        token_verifier=verifier if auth is not None else None,
        auth=auth,
    )

    @server.tool(name="report_gates", description="Report auth configuration, the live Fieldwork API role, write and mapping flags, and which operations can propose or execute. Does not change Fieldwork.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def report_gates() -> dict[str, Any]:
        return report_gates_body(service, settings)

    @server.tool(name="propose_write", description=PROPOSE_DESCRIPTION)
    async def propose_write(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        identity = request_identity()
        if identity is None:
            return {"ok": False, "gate": GATE_AUTH, "gates": service.gates()}
        return redact(service.propose(operation, payload, identity))

    @server.tool(
        name="execute_approved_write",
        description=EXECUTE_DESCRIPTION,
        annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
    )
    async def execute_approved_write(
        proposal_id: str,
        approved: bool | None = None,
        expected_digest: str = "",
    ) -> dict[str, Any]:
        if settings.approval_mode != "chatgpt_confirmation":
            return {"ok": False, "gate": "approval_mode_unsupported", "reason": "mcp_execution_requires_chatgpt_confirmation", "gates": service.readiness(settings)["gates"]}
        identity = request_identity()
        if identity is None:
            return {"ok": False, "gate": GATE_AUTH, "gates": service.gates()}
        return redact(
            service.execute(
                proposal_id,
                identity,
                approved=approved,
                expected_digest=expected_digest,
            )
        )

    @server.tool(name="reconcile_ambiguous_write", description="Read the live work order for a proposal already marked ambiguous. Does not send another PATCH and does not change the stored payload or digest.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def reconcile_ambiguous_write(proposal_id: str) -> dict[str, Any]:
        identity = request_identity()
        if identity is None:
            return {"ok": False, "gate": GATE_AUTH, "gates": service.gates()}
        return redact(service.reconcile_ambiguous(proposal_id, identity))

    @server.tool(name="inspect_proposal", description="Return one stored proposal, including its digest, before, after, and expiry. Does not write. No secrets.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def inspect_proposal(proposal_id: str) -> dict[str, Any]:
        identity = request_identity()
        if identity is None:
            return {"ok": False, "gate": GATE_AUTH, "gates": service.gates()}
        return redact(service.inspect(proposal_id, identity))

    _register_reads(server, service)
    return server


def build_bridge_server(settings: Settings, service: WriteService, fieldwork_key: str = "") -> Any:
    """FastMCP Auth0 bridge. Not used by the default direct-JWT server."""
    from fastmcp import FastMCP

    from .auth0_bridge import bridge_identity_from_token, build_auth0_provider

    provider = build_auth0_provider(settings, fieldwork_key=fieldwork_key)
    mcp = FastMCP(name="bt-fieldwork-write-mcp", auth=provider, instructions=PUBLIC_INSTRUCTIONS)

    def _identity() -> dict[str, str] | None:
        from fastmcp.server.dependencies import get_access_token

        token = get_access_token()
        identity = bridge_identity_from_token(token, settings)
        if identity is not None:
            service.authenticated_call_observed = True
            service.offline_access_observed = "offline_access" in (getattr(token, "scopes", None) or [])
        return identity

    @mcp.tool(name="report_gates", description="Report auth configuration, the live Fieldwork API role, write and mapping flags, and which operations can propose or execute. Does not change Fieldwork.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def report_gates() -> dict[str, Any]:
        if _identity() is None:
            return {"ok": False, "gate": GATE_AUTH}
        return report_gates_body(service, settings)

    @mcp.tool(name="propose_write", description=PROPOSE_DESCRIPTION)
    async def propose_write(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        identity = _identity()
        if identity is None:
            return {"ok": False, "gate": GATE_AUTH, "gates": service.gates()}
        return redact(service.propose(operation, payload, identity))

    @mcp.tool(name="execute_approved_write", description=EXECUTE_DESCRIPTION, annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True})
    async def execute_approved_write(proposal_id: str, approved: bool | None = None, expected_digest: str = "") -> dict[str, Any]:
        if settings.approval_mode != "chatgpt_confirmation":
            return {"ok": False, "gate": "approval_mode_unsupported", "reason": "mcp_execution_requires_chatgpt_confirmation", "gates": service.readiness(settings)["gates"]}
        identity = _identity()
        if identity is None:
            return {"ok": False, "gate": GATE_AUTH, "gates": service.gates()}
        return redact(service.execute(proposal_id, identity, approved=approved, expected_digest=expected_digest))

    @mcp.tool(name="reconcile_ambiguous_write", description="Read the live work order for a proposal already marked ambiguous. Does not send another PATCH and does not change the stored payload or digest.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def reconcile_ambiguous_write(proposal_id: str) -> dict[str, Any]:
        identity = _identity()
        if identity is None:
            return {"ok": False, "gate": GATE_AUTH, "gates": service.gates()}
        return redact(service.reconcile_ambiguous(proposal_id, identity))

    @mcp.tool(name="inspect_proposal", description="Return one stored proposal, including its digest, before, after, and expiry. Does not write. No secrets.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def inspect_proposal(proposal_id: str) -> dict[str, Any]:
        identity = _identity()
        if identity is None:
            return {"ok": False, "gate": GATE_AUTH, "gates": service.gates()}
        return redact(service.inspect(proposal_id, identity))

    _register_reads(mcp, service, identity_getter=_identity)
    return mcp


def _register_reads(server: Any, service: WriteService, identity_getter: Any = None) -> None:
    from .fieldwork import work_order_view

    def _who() -> dict[str, str] | None:
        if identity_getter is not None:
            return identity_getter()
        return request_identity()

    def _guard() -> dict[str, Any] | None:
        if _who() is None:
            return {"ok": False, "gate": GATE_AUTH}
        return None

    @server.tool(name="search_customers", description="Search customers. Documented search accepts query, filter[customer_status], filter[postal_code], filter[date_added], start_date, end_date, page, and per_page. start_date/end_date are spec labels and are not claimed to be a created-date range. Phone uses GET /customers/search_by_phone and cannot be combined with those filters. name is applied locally and is incomplete when the page scan is truncated. Branch and other undocumented filters are rejected. Does not write.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def search_customers(query: str = "", customer_status: str = "", name: str = "", phone: str = "", postal_code: str = "", billing_postal_code: str = "", date_added: str = "", start_date: str = "", end_date: str = "", page: int = 0, per_page: int = 100, include_details: bool = False) -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.search_customers(query, customer_status=customer_status, name=name, phone=phone, postal_code=postal_code, billing_postal_code=billing_postal_code, date_added=date_added, start_date=start_date, end_date=end_date, page=page or None, per_page=per_page, include_details=include_details))
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected"), "fields": getattr(exc, "detail", {}).get("fields")}

    @server.tool(name="get_customer", description="Read one customer by numeric id. Does not write.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def get_customer(customer_id: str) -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.get_customer(customer_id))
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected")}

    @server.tool(name="list_service_locations", description="List service locations for one required customer id at GET /customers/{customer_id}/service_locations. Documented filters are page, per_page, filter[phone], and filter[updated_after]. query, active, and branch are rejected. A full page sets truncated and next_page. Does not write.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def list_service_locations(customer_id: str, page: int = 1, per_page: int = 100, phone: str = "", updated_after: str = "") -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.list_service_locations(customer_id, page=page, per_page=per_page, phone=phone, updated_after=updated_after))
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected"), "fields": getattr(exc, "detail", {}).get("fields")}

    @server.tool(name="get_service_location", description="Read one service location for a customer id and location id. Does not write.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def get_service_location(customer_id: str, location_id: str) -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.get_location(customer_id, location_id))
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected")}

    @server.tool(name="list_work_order_statuses", description="Read GET /v3.1/statuses. value is the status write string, name is the label, and id is metadata. The i18n map is not this catalog. Transitions are not included. Does not write.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def list_work_order_statuses() -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            items = service.client.list_work_order_statuses()
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected")}
        return redact({
            "ok": True,
            "source": "GET /v3.1/statuses",
            "shape": "bare_array",
            "write_field": "value",
            "label_field": "name",
            "id_is_not_the_write_value": True,
            "transitions": "not_in_spec",
            "entity_type": "not_in_custom_array",
            "items": items,
        })

    @server.tool(name="search_services", description="Search the current GET /v3.1/services list by description, acronym, or id. Exposes catalog fields and states when active, taxable, and production defaults are absent. Does not invent a GET-by-id. Does not write.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def search_services(text: str = "") -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.search_services(text))
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected")}

    @server.tool(name="get_service", description="Return one service from the already fetched GET /v3.1/services list. There is no GET /services/{id}. Does not write.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def get_service(service_id: str) -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.get_service(service_id))
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected"), "reason": getattr(exc, "detail", {}).get("reason")}

    @server.tool(name="get_work_order", description="Read one work order. The occurrence id and service_appointment_id stay distinct. Recurrence is verified only when this occurrence payload contains repeat_type. Does not write.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def get_work_order(work_order_id: str) -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(work_order_view(service.client.get_work_order(work_order_id)))
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected")}

    @server.tool(name="list_work_orders", description="Read work orders for start_date and end_date, with optional status, route, current_technician, sort_direction, and work_pool. Route and status are checked locally because the API ignores the route filter. A full page sets truncated and next_page. Does not write.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def list_work_orders(start_date: str = "", end_date: str = "", current_technician: bool = False, sort_direction: str = "asc", work_pool: bool = False, status: str = "", service_route_ids: list[str] | None = None, customer_id: str = "", service_location_id: str = "", page: int = 1) -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.list_work_orders(start_date=start_date, end_date=end_date, current_technician=current_technician, sort_direction=sort_direction, work_pool=work_pool, status=status, service_route_ids=service_route_ids or [], customer_id=customer_id, service_location_id=service_location_id, page=page))
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected"), "fields": getattr(exc, "detail", {}).get("fields")}

    @server.tool(name="list_schedule", description="Read the schedule for ISO dates in America/New_York, optionally by technician name or route ids. Includes customer, address, times, arrival window, and distinct occurrence and appointment ids. A configured route directory is labeled as a snapshot. null technician_id is not unassigned. Follow next_page when truncated. Does not write.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def list_schedule(start_date: str, end_date: str, current_technician: bool = False, sort_direction: str = "asc", work_pool: bool = False, status: str = "", service_route_ids: list[str] | None = None, customer_id: str = "", service_location_id: str = "", technician: str = "", page: int = 1) -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.list_work_orders(start_date=start_date, end_date=end_date, current_technician=current_technician, sort_direction=sort_direction, work_pool=work_pool, status=status, service_route_ids=service_route_ids or [], customer_id=customer_id, service_location_id=service_location_id, technician=technician, page=page))
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected"), "fields": getattr(exc, "detail", {}).get("fields")}

    @server.tool(name="list_users", description="Read staff from GET /users. Returns name, contact, route, and branch id/name/company/address/time zone. Keeps staff assigned to a route even when is_technician is false. Does not return stripe_pk or internal account fields. Does not write.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def list_users() -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.list_users())
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected")}

    @server.tool(name="list_service_routes", description="Read GET /service_routes. An empty array is valid and is not proof of no staff. When GET /users succeeds, route relationships come from that live directory and a shared route lists every staff member with no single assignee. A configured snapshot is used only when live users are unavailable, and it is labeled with that reason. Does not write.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def list_service_routes() -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.list_service_routes())
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected")}

def report_gates_body(service: WriteService, settings: Settings) -> dict[str, Any]:
    body = service.readiness(settings)
    nested = body["gates"]
    body["live_ready"] = nested["live_ready"]
    body["credential_ready"] = nested["credential_ready"]
    body["oauth_ready"] = nested["oauth_ready"]
    body["fieldwork_api_auth_verified"] = nested["fieldwork_api_auth_verified"]
    body["writes_enabled"] = nested["writes_enabled"]
    body["approval_mode"] = nested["approval_mode"]
    body["forbidden"] = sorted(FORBIDDEN_OPS)
    return body


def build_server(settings: Settings | None = None, service: WriteService | None = None) -> MCPServer:
    from .fieldwork import HttpTransport, TypedFieldworkClient
    from .store import WriteStore

    settings = settings or Settings.from_env()
    if service is None:
        store = WriteStore(settings.store_path)
        transport = HttpTransport(load_api_key(), api_base=settings.api_base)
        from .fieldwork import load_route_directory

        client = TypedFieldworkClient(transport, mapping_verified=settings.mapping_verified, route_directory=load_route_directory(settings.route_directory_path))
        service = WriteService(settings, store, client)
    verifier = JwtTokenVerifier(settings)
    if not settings.oauth_ready():
        raise RuntimeError("oauth_required")
    return build_mcp(service, settings, verifier)


def closed_startup_gates(settings: Settings) -> dict[str, Any]:
    return {
        "oauth_authorization_server_configured": settings.oauth_ready(),
        "writes_enabled": settings.writes_enabled,
        "live_ready": False,
        **current_gates(
            writes_enabled=settings.writes_enabled,
            mapping_verified=settings.mapping_verified,
            api_role=settings.api_role,
            credential_ready=False,
            oauth_ready=settings.oauth_ready(),
        ),
    }
