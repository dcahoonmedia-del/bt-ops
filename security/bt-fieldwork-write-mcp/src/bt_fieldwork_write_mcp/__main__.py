"""Process entry. Does not deploy or contact GCP."""

from __future__ import annotations

import os

from .config import Settings
from .server import build_server, closed_startup_gates


def main() -> None:
    settings = Settings.from_env()
    print(closed_startup_gates(settings), flush=True)
    server = build_server(settings)
    transport = os.environ.get("FW_WRITE_TRANSPORT", "stdio").strip().lower()
    if transport == "http":
        server.run(transport="streamable-http")
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
