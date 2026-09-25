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

PUBLIC_INSTRUCTIONS = (
    "Read the Fieldwork record, propose one change, inspect it, and show the user the exact before and after. "
    "Obtain explicit user approval of that before and after. Then execute only with approved=true and the exact digest "
    "from that proposal, and show the live readback. Do not execute a draft, a stale proposal, a different proposal, "
    "or a change the user did not approve. No customer create, no work-order create, no Lead-status accounts, "
    "no messaging, no generic HTTP, no recurring-series edits, and no arrival-window edits. "
    "Writes stay off unless FIELDWORK_WRITES_ENABLED is set and the live API role is writer. "
    "Work-order writes also require FIELDWORK_MAPPING_VERIFIED. GET /check_connection is not auth proof. "
    "MCP execution requires FW_WRITE_APPROVAL_MODE=chatgpt_confirmation. A separate approval string is not accepted."
)

EXECUTE_DESCRIPTION = (
    "After the user has explicitly approved the exact before and after shown by inspect_proposal, "
    "execute that one proposal with approved=true and the exact digest. The result includes live readback. "
    "Rejects missing approval, a missing or wrong digest, a stale before, an expired proposal, a tampered stored proposal, "
    "another proposal id, or another user's proposal. create_work_order cannot execute. "
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

    @server.tool(name="propose_write", description="Prepare one exact before/after proposal and do not change Fieldwork. Supported: update_service_location_notes(customer_id, location_id, notes); update_work_order_notes(work_order_id, service_appointment_id, instructions and/or private_notes); update_work_order_schedule(work_order_id, service_appointment_id, starts_at with a numeric offset, duration minutes, service_route_ids). create_work_order, customer create, messages, series edits, and arrival-window edits are rejected.")
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

    @mcp.tool(name="propose_write", description="Prepare one exact before/after proposal and do not change Fieldwork. Supported: update_service_location_notes(customer_id, location_id, notes); update_work_order_notes(work_order_id, service_appointment_id, instructions and/or private_notes); update_work_order_schedule(work_order_id, service_appointment_id, starts_at with a numeric offset, duration minutes, service_route_ids). create_work_order, customer create, messages, series edits, and arrival-window edits are rejected.")
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
