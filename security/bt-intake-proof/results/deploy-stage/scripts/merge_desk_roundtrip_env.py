#!/usr/bin/env python3
"""Merge /etc/bt-intake-proof/env for isolated desk-roundtrip. Does not write tokens."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bt_intake_proof.desk_deploy_env import load_env_file, merge_desk_roundtrip_env, render_env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="/etc/bt-intake-proof/env")
    parser.add_argument("--prefix", default="/opt/bt-intake-proof")
    parser.add_argument("--state", default="/var/lib/bt-intake-proof")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    path = Path(args.env)
    existing = load_env_file(path)
    merged = merge_desk_roundtrip_env(existing, prefix=args.prefix, state=args.state)
    text = render_env(merged)
    if args.write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        path.chmod(0o640)
    print(
        json.dumps(
            {
                "ok": True,
                "wrote": bool(args.write),
                "path": str(path),
                "mode": "isolated_test",
                "daniel_token": merged.get("BT_DANIEL_GMAIL_TOKEN"),
                "store": merged.get("BT_INTAKE_STORE"),
                "preserved_contactus_token": existing.get("BT_GMAIL_TOKEN") == merged.get("BT_GMAIL_TOKEN")
                if existing.get("BT_GMAIL_TOKEN")
                else True,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
