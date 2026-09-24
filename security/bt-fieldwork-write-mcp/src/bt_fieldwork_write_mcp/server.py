"""Official MCP SDK resource server. OAuth validation is required for HTTP."""

from __future__ import annotations

from typing import Any, Callable

from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer

from .allowlist import FORBIDDEN_OPS, GATE_AUTH, current_gates
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


def build_mcp(
    service: WriteService,
    settings: Settings,
    verifier: JwtTokenVerifier,
    *,
    identity_provider: Callable[[], dict[str, str] | None] | None = None,
) -> MCPServer:
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

    def _identity() -> dict[str, str] | None:
        if identity_provider is not None:
            return identity_provider()
        return None

    @server.tool(name="report_gates", description="Report closed write gates. Not live readiness.")
    def report_gates() -> dict[str, Any]:
        return {
            "ok": True,
            "live_ready": False,
            "fieldwork_api_auth_verified": False,
            "check_connection_is_not_auth_proof": True,
            "gates": service.gates(),
            "forbidden": sorted(FORBIDDEN_OPS),
        }

    @server.tool(name="propose_write", description="Build an immutable exact-before/after proposal. Does not write.")
    def propose_write(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        identity = _identity()
        if identity is None:
            return {"ok": False, "gate": GATE_AUTH, "gates": service.gates()}
        return redact(service.propose(operation, payload, identity))

    @server.tool(
        name="execute_approved_write",
        description="Execute one independently approved proposal. Ignores approved=true.",
    )
    def execute_approved_write(
        proposal_id: str,
        operator_approval: str = "",
        approved: bool | None = None,
    ) -> dict[str, Any]:
        identity = _identity()
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
    def inspect_proposal(proposal_id: str) -> dict[str, Any]:
        return redact(service.inspect(proposal_id))

    return server


def build_server(
    settings: Settings | None = None,
    service: WriteService | None = None,
    *,
    identity_provider: Callable[[], dict[str, str] | None] | None = None,
) -> MCPServer:
    from .fieldwork import HttpTransport, TypedFieldworkClient
    from .store import WriteStore

    settings = settings or Settings.from_env()
    if service is None:
        store = WriteStore(settings.store_path)
        transport = HttpTransport(load_api_key(), api_base=settings.api_base)
        client = TypedFieldworkClient(transport, mapping_verified=settings.mapping_verified)
        service = WriteService(settings, store, client)
    verifier = JwtTokenVerifier(settings)
    return build_mcp(service, settings, verifier, identity_provider=identity_provider)


def closed_startup_gates(settings: Settings) -> dict[str, Any]:
    return {
        "oauth_authorization_server_configured": settings.oauth_ready(),
        "writes_enabled": settings.writes_enabled,
        "live_ready": False,
        **current_gates(writes_enabled=settings.writes_enabled, mapping_verified=settings.mapping_verified),
    }
