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
            "no messaging, no generic HTTP. Writes disabled by default. "
            "Work-order ID mapping and create schema are unverified. "
            "GET /check_connection is not auth proof. "
            "Operator HMAC approval is required; approved=true is ignored."
        ),
        token_verifier=verifier if auth is not None else None,
        auth=auth,
    )

    @server.tool(name="report_gates", description="Report closed write gates. Not live readiness.")
    async def report_gates() -> dict[str, Any]:
        return report_gates_body(service, settings)

    @server.tool(name="propose_write", description="Build an immutable exact-before/after proposal. Does not write.")
    async def propose_write(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        identity = request_identity()
        if identity is None:
            return {"ok": False, "gate": GATE_AUTH, "gates": service.gates()}
        return redact(service.propose(operation, payload, identity))

    @server.tool(
        name="execute_approved_write",
        description="Execute one independently approved proposal. Ignores approved=true.",
    )
    async def execute_approved_write(
        proposal_id: str,
        operator_approval: str = "",
        approved: bool | None = None,
    ) -> dict[str, Any]:
        identity = request_identity()
        if identity is None:
            return {"ok": False, "gate": GATE_AUTH, "gates": service.gates()}
        return redact(
            service.execute(
                proposal_id,
                identity,
                operator_approval=operator_approval,
                approved=approved,
            )
        )

    @server.tool(name="inspect_proposal", description="Inspect a stored proposal. No secrets.")
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
    mcp = FastMCP(name="bt-fieldwork-write-mcp", auth=provider)

    def _identity() -> dict[str, str] | None:
        from fastmcp.server.dependencies import get_access_token

        return bridge_identity_from_token(get_access_token(), settings)

    @mcp.tool(name="report_gates", description="Report closed write gates. Not live readiness.")
    async def report_gates() -> dict[str, Any]:
        if _identity() is None:
            return {"ok": False, "gate": GATE_AUTH}
        return report_gates_body(service, settings)

    @mcp.tool(name="propose_write", description="Build an immutable exact-before/after proposal. Does not write.")
    async def propose_write(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        identity = _identity()
        if identity is None:
            return {"ok": False, "gate": GATE_AUTH, "gates": service.gates()}
        return redact(service.propose(operation, payload, identity))

    @mcp.tool(name="execute_approved_write", description="Execute one independently approved proposal. Ignores approved=true.")
    async def execute_approved_write(proposal_id: str, operator_approval: str = "", approved: bool | None = None) -> dict[str, Any]:
        identity = _identity()
        if identity is None:
            return {"ok": False, "gate": GATE_AUTH, "gates": service.gates()}
        return redact(service.execute(proposal_id, identity, operator_approval=operator_approval, approved=approved))

    @mcp.tool(name="inspect_proposal", description="Inspect a stored proposal. No secrets.")
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

    @server.tool(name="search_customers", description="Search customers by the documented query parameter. Pages until a short page or reports truncation.")
    async def search_customers(query: str) -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.search_customers(query))
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected")}

    @server.tool(name="get_customer", description="GET one customer by id. Flat id-bearing body only.")
    async def get_customer(customer_id: str) -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.get_customer(customer_id))
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected")}

    @server.tool(name="get_service_location", description="GET one service location wrapper for a customer.")
    async def get_service_location(customer_id: str, location_id: str) -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.get_location(customer_id, location_id))
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected")}

    @server.tool(name="get_work_order", description="GET one work order. Occurrence id and service-appointment id stay distinct.")
    async def get_work_order(work_order_id: str) -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(work_order_view(service.client.get_work_order(work_order_id)))
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected")}

    @server.tool(name="list_work_orders", description="GET /work_orders with documented date, route, technician, and pool filters. Pages until short or reports truncation.")
    async def list_work_orders(start_date: str = "", end_date: str = "", current_technician: bool = False, sort_direction: str = "asc", work_pool: bool = False, status: str = "", service_route_ids: list[str] | None = None) -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.list_work_orders(start_date=start_date, end_date=end_date, current_technician=current_technician, sort_direction=sort_direction, work_pool=work_pool, status=status, service_route_ids=service_route_ids or []))
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected")}

    @server.tool(name="list_schedule", description="Same documented GET /work_orders filters as list_work_orders. Date bounds are sent, not dropped.")
    async def list_schedule(start_date: str, end_date: str, current_technician: bool = False, sort_direction: str = "asc", work_pool: bool = False, status: str = "", service_route_ids: list[str] | None = None, technician: str = "") -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.list_work_orders(start_date=start_date, end_date=end_date, current_technician=current_technician, sort_direction=sort_direction, work_pool=work_pool, status=status, service_route_ids=service_route_ids or [], technician=technician))
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected")}

    @server.tool(name="list_service_routes", description="GET /service_routes with page and per_page only.")
    async def list_service_routes() -> dict[str, Any]:
        denied = _guard()
        if denied:
            return denied
        try:
            return redact(service.client.list_service_routes())
        except Exception as exc:
            return {"ok": False, "gate": getattr(exc, "gate", "read_rejected")}

def report_gates_body(service: WriteService, settings: Settings) -> dict[str, Any]:
    return {
        "ok": True,
        "live_ready": False,
        "fieldwork_api_auth_verified": False,
        "credential_ready": service.gates().get("credential_ready"),
        "direct_jwt_configured": settings.oauth_ready(),
        "auth0_bridge_configured": settings.auth_mode == "auth0_bridge" and not bridge_blockers(settings),
        "active_auth_configured": (settings.auth_mode == "auth0_bridge" and not bridge_blockers(settings)) or (settings.auth_mode != "auth0_bridge" and settings.oauth_ready()),
        "live_auth0_login_observed_by_this_process": False,
        "offline_access_requested": settings.auth0_offline_access,
        "offline_access_required_on_access_token": False,
        "offline_access_allow_saved_by_operator": True,
        "offline_access_observed_by_this_process": False,
        "existing_downstream_sessions_remain_usable": True,
        "refresh_token_needs_one_new_authorization": True,
        "reuse_storage_path_configured": bool(settings.auth0_storage_path),
        "reuse_storage_key_configured": bool(settings.auth0_storage_key),
        "reuse_signing_key_configured": bool(settings.auth0_jwt_signing_key),
        "live_patch_tested": False,
        "check_connection_is_not_auth_proof": True,
        "gates": service.gates(),
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
