"""Process entry. Does not deploy or contact GCP."""

from __future__ import annotations

import os
import sys

from .config import Settings
from .server import build_server, closed_startup_gates
from .service import WriteService


def main() -> None:
    settings = Settings.from_env()
    print(closed_startup_gates(settings), file=sys.stderr, flush=True)
    if str(settings.store_path).startswith("/tmp"):
        print({"store": "ephemeral", "path_class": "tmp"}, file=sys.stderr, flush=True)
    transport = os.environ.get("FW_WRITE_TRANSPORT", "stdio").strip().lower()
    if settings.auth_mode == "auth0_bridge":
        from .auth0_bridge import bridge_blockers

        blocked = bridge_blockers(settings)
        if blocked:
            print({"ok": False, "gate": "auth0_bridge_blocked", "blocked": blocked}, file=sys.stderr, flush=True)
            raise SystemExit(2)
    elif not settings.oauth_ready():
        print({"ok": False, "gate": "oauth_required"}, file=sys.stderr, flush=True)
        raise SystemExit(2)
    if settings.auth_mode == "auth0_bridge":
        if transport != "http":
            print({"ok": False, "gate": "auth0_bridge_requires_http"}, file=sys.stderr, flush=True)
            raise SystemExit(2)
        from .fieldwork import HttpTransport, TypedFieldworkClient
        from .secrets import load_api_key
        from .server import build_bridge_server
        from .store import WriteStore

        fieldwork_key = load_api_key()
        store = WriteStore(settings.store_path)
        from .fieldwork import load_route_directory

        client = TypedFieldworkClient(HttpTransport(fieldwork_key, api_base=settings.api_base), route_directory=load_route_directory(settings.route_directory_path))
        try:
            server = build_bridge_server(settings, WriteService(settings, store, client), fieldwork_key=fieldwork_key.get())
        except ValueError as exc:
            print({"ok": False, "gate": "auth0_bridge_blocked", "reason": str(exc).split(":")[0]}, file=sys.stderr, flush=True)
            raise SystemExit(2) from None
        server.run(transport="http")
        return
    server = build_server(settings)
    if transport == "http":
        server.run(transport="streamable-http")
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
