"""Process entry. Does not deploy or contact GCP."""

from __future__ import annotations

import os
import sys

from .config import Settings
from .server import build_server, closed_startup_gates


def main() -> None:
    settings = Settings.from_env()
    print(closed_startup_gates(settings), file=sys.stderr, flush=True)
    if str(settings.store_path).startswith("/tmp"):
        print({"store": "ephemeral", "path_class": "tmp"}, file=sys.stderr, flush=True)
    transport = os.environ.get("FW_WRITE_TRANSPORT", "stdio").strip().lower()
    if transport == "http" and not settings.oauth_ready():
        print({"ok": False, "gate": "oauth_required"}, file=sys.stderr, flush=True)
        raise SystemExit(2)
    if not settings.oauth_ready():
        print({"ok": False, "gate": "oauth_required"}, file=sys.stderr, flush=True)
        raise SystemExit(2)
    server = build_server(settings)
    if transport == "http":
        server.run(transport="streamable-http")
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
