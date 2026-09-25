"""Operator CLI. Mints an HMAC approval. Not an MCP tool and not model-callable."""

from __future__ import annotations

import argparse
import json
import sys

from .config import Settings
from .fieldwork import FakeTransport, TypedFieldworkClient
from .service import WriteService
from .store import WriteStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mint an independent operator approval for one proposal.")
    parser.add_argument("proposal_id")
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    store = WriteStore(settings.store_path)
    # Minting does not talk to Fieldwork; a dummy client is enough.
    service = WriteService(settings, store, TypedFieldworkClient(FakeTransport(), mapping_verified=False))
    result = service.mint_approval(args.proposal_id)
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
