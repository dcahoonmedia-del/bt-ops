"""Official MCP SDK resource server. OAuth validation is required for HTTP."""

from __future__ import annotations

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
        instructions=(
            "Narrow Fieldwork writes only. No customer create, no Lead-status accounts, "
            "no messaging, no generic HTTP. Writes stay off unless FIELDWORK_WRITES_ENABLED is set "
            "and the live API role is writer. Work-order writes also require FIELDWORK_MAPPING_VERIFIED. "
            "create_work_order is unsupported. GET /check_connection is not auth proof. "
            + (
                "ChatGPT execution requires approved=true and the exact proposal digest. "
                "A separate approval string is not accepted."
                if settings.approval_mode == "chatgpt_confirmation"
                else "Model-supplied approved=true is not proof. Operator HMAC is internal and is not a tool parameter."
            )
        ),
        token_verifier=verifier if auth is not None else None,
        auth=auth,
    )

    @server.tool(name="report_gates", description="Report auth configuration, the live Fieldwork API role, write and mapping flags, and which operations can propose or execute. Does not change Fieldwork.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def report_gates() -> dict[str, Any]:
        return report_gates_body(service, settings)

    @server.tool(name="propose_write", description="Prepare one exact before/after proposal and do not change Fieldwork. Supported: update_service_location_notes(customer_id, location_id, notes); update_work_order_notes(work_order_id, service_appointment_id, instructions and/or private_notes); update_work_order_schedule(work_order_id, service_appointment_id, starts_at with a numeric offset, duration minutes, service_route_ids). create_work_order, customer create, messages, series edits, and arrival-window edits are rejected.")
    async def propose_write(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        identity = request_identity()
        if identity is None:
            return {"ok": False, "gate": GATE_AUTH, "gates": service.gates()}
        return redact(service.propose(operation, payload, identity))

    @server.tool(
        name="execute_approved_write",
        description="Execute one stored proposal on the fake or live client only when approved is true and expected_digest equals that proposal digest. The digest binds proposal_id, payload, before, after, identity, and target. Do not send an approval string. Rejects a missing, stale, tampered, or cross-proposal digest. create_work_order cannot execute.",
        annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
    )
    async def execute_approved_write(
        proposal_id: str,
        approved: bool | None = None,
        expected_digest: str = "",
    ) -> dict[str, Any]:
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
    mcp = FastMCP(name="bt-fieldwork-write-mcp", auth=provider, instructions="Read schedules, customers, locations, and work orders. Propose an exact before/after change, then execute only with approved=true and that proposal's digest. No approval string. Never create customers or work orders, send messages, change a recurring series, or use generic HTTP. Arrival-window edits are unsupported. Writes require the writes flag, a live writer role, and mapping verification for work orders.")

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

    @mcp.tool(name="propose_write", description="Prepare one exact before/after proposal and do not change Fieldwork. Supported: update_service_location_notes(customer_id, location_id, notes); update_work_order_notes(work_order_id, service_appointment_id, instructions and/or private_notes); update_work_order_schedule(work_order_id, service_appointment_id, starts_at with a numeric offset, duration minutes, service_route_ids). create_work_order, customer create, messages, series edits, and arrival-window edits are rejected.")
    async def propose_write(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        identity = _identity()
        if identity is None:
            return {"ok": False, "gate": GATE_AUTH, "gates": service.gates()}
        return redact(service.propose(operation, payload, identity))

    @mcp.tool(name="execute_approved_write", description="Execute one stored proposal only when approved is true and expected_digest equals that proposal digest. The digest binds proposal_id, payload, before, after, identity, and target. Do not send an approval string. Rejects a missing, stale, tampered, or cross-proposal digest. create_work_order cannot execute.", annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True})
    async def execute_approved_write(proposal_id: str, approved: bool | None = None, expected_digest: str = "") -> dict[str, Any]:
        identity = _identity()
        if identity is None:
            return {"ok": False, "gate": GATE_AUTH, "gates": service.gates()}
        return redact(service.execute(proposal_id, identity, approved=approved, expected_digest=expected_digest))

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

    @server.tool(name="search_customers", description="Search customers with the documented query parameter. Reads pages until a short page, or returns truncation and next_page. Does not write.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def search_customers(query: str) -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.search_customers(query))
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected")}

    @server.tool(name="get_customer", description="Read one customer by numeric id. Does not write.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def get_customer(customer_id: str) -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.get_customer(customer_id))
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected")}

    @server.tool(name="get_service_location", description="Read one service location for a customer id and location id. Does not write.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def get_service_location(customer_id: str, location_id: str) -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.get_location(customer_id, location_id))
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected")}

    @server.tool(name="get_work_order", description="Read one work order. The occurrence id and service_appointment_id stay distinct. Does not write.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def get_work_order(work_order_id: str) -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(work_order_view(service.client.get_work_order(work_order_id)))
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected")}

    @server.tool(name="list_work_orders", description="Read work orders for start_date and end_date, with optional status, route, current_technician, sort_direction, and work_pool. Route and status are checked locally because the API ignores the route filter. A full page sets truncated and next_page. Does not write.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def list_work_orders(start_date: str = "", end_date: str = "", current_technician: bool = False, sort_direction: str = "asc", work_pool: bool = False, status: str = "", service_route_ids: list[str] | None = None, page: int = 1) -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.list_work_orders(start_date=start_date, end_date=end_date, current_technician=current_technician, sort_direction=sort_direction, work_pool=work_pool, status=status, service_route_ids=service_route_ids or [], page=page))
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected")}

    @server.tool(name="list_schedule", description="Read the schedule for ISO dates in America/New_York, optionally by technician name or route ids. Includes customer, address, times, arrival window, and distinct occurrence and appointment ids. A configured route directory is labeled as a snapshot. null technician_id is not unassigned. Follow next_page when truncated. Does not write.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def list_schedule(start_date: str, end_date: str, current_technician: bool = False, sort_direction: str = "asc", work_pool: bool = False, status: str = "", service_route_ids: list[str] | None = None, technician: str = "", page: int = 1) -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.list_work_orders(start_date=start_date, end_date=end_date, current_technician=current_technician, sort_direction=sort_direction, work_pool=work_pool, status=status, service_route_ids=service_route_ids or [], technician=technician, page=page))
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected")}

    @server.tool(name="list_service_routes", description="Read service routes. An empty array is a valid directory, not proof of no staff. Route names on work orders remain usable. Does not write. list_users is not available.", annotations={"readOnlyHint": True, "destructiveHint": False})
    async def list_service_routes() -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.list_service_routes())
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected")}

def report_gates_body(service: WriteService, settings: Settings) -> dict[str, Any]:
    role_error = None
    try:
        role = service.client.get_api_role()
    except Exception as exc:
        role, role_error = "unknown", getattr(exc, "gate", "read_rejected")
    normalized = str(role or "unknown").strip().lower().replace("-", "_").replace(" ", "_")
    writer = role_error is None and normalized == "writer"
    writes_on = bool(settings.writes_enabled) and writer
    if settings.auth_mode == "auth0_bridge":
        oauth_ready = not bridge_blockers(settings)
    else:
        oauth_ready = settings.oauth_ready()
    gates = service.gates()
    gates.update(
        api_role=normalized,
        fieldwork_api_auth_verified=role_error is None,
        fieldwork_get_auth_verified=role_error is None,
        writes_enabled=writes_on,
        work_order_id_mapping_verified=bool(settings.mapping_verified),
        live_ready=writes_on,
        rollout_safeguard="FIELDWORK_WRITES_ENABLED and live writer role; work orders also need FIELDWORK_MAPPING_VERIFIED",
        oauth_ready=oauth_ready,
    )
    return {
        "ok": True,
        "reads_ready": role_error is None,
        "live_ready": writes_on,
        "fieldwork_api_auth_verified": role_error is None,
        "role_check_error": role_error,
        "credential_ready": service.client.api_key_present(),
        "direct_jwt_configured": settings.oauth_ready(),
        "auth0_bridge_configured": settings.auth_mode == "auth0_bridge" and not bridge_blockers(settings),
        "live_auth0_login_observed_by_this_process": bool(getattr(service, "authenticated_call_observed", False)),
        "offline_access_requested": settings.auth0_offline_access,
        "offline_access_required_on_access_token": False,
        "offline_access_observed_by_this_process": bool(getattr(service, "offline_access_observed", False)),
        "existing_downstream_sessions_remain_usable": True,
        "refresh_token_needs_one_new_authorization": not bool(getattr(service, "offline_access_observed", False)),
        "approval_mode": settings.approval_mode,
        "live_patch_tested": False,
        "live_patch_tested_is_a_status_not_a_write_block": True,
        "gates": gates,
        "forbidden": sorted(FORBIDDEN_OPS),
    }


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
