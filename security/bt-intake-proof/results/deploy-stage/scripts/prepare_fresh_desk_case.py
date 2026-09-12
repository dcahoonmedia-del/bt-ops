#!/usr/bin/env python3
"""Create the fresh isolated desk case and decision packet. Does not approve or send."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bt_intake_proof.desk_deploy_env import load_env_file
from bt_intake_proof.desk_fresh_case import format_decision_markdown, prepare_fresh_desk_case
from bt_intake_proof.gates import store_path
from bt_intake_proof.store import ReceiptStore


def _apply_host_env() -> None:
    env_path = Path(os.environ.get("BT_INTAKE_ENV", "/etc/bt-intake-proof/env"))
    for key, value in load_env_file(env_path).items():
        os.environ.setdefault(key, value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="write the unused case into BT_INTAKE_STORE")
    parser.add_argument("--store", default="", help="SQLite path override")
    parser.add_argument(
        "--out",
        default="",
        help="directory for DECISION_PACKET.json/md",
    )
    args = parser.parse_args(argv)
    if args.live:
        _apply_host_env()
    dest = Path(args.out) if args.out else ROOT / "results" / "desk-roundtrip-release"
    dest.mkdir(parents=True, exist_ok=True)
    if args.store:
        path = Path(args.store)
    elif args.live:
        path = store_path()
    else:
        path = dest / ".fresh-case-local.sqlite"
    store = ReceiptStore(path)
    try:
        result = prepare_fresh_desk_case(store, dest=dest)
    finally:
        store.close()
    print(json.dumps({k: result[k] for k in result if k != "decision"}, indent=2, default=str))
    print(format_decision_markdown(result["decision"]))
    if result.get("approve_send_recorded") or result.get("send_queued") or result.get("proof_reply_sent"):
        return 2
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
