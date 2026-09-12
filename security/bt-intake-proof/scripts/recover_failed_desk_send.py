#!/usr/bin/env python3
"""Inspect or authorize one recovery of failed desk action 2. Default is dry-run."""

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

from bt_intake_proof.bounded_send import MissingContactusSendTransport
from bt_intake_proof.cases import CaseLayer
from bt_intake_proof.contactus_send import configured_send_transport
from bt_intake_proof.desk_deploy_env import load_env_file
from bt_intake_proof.desk_recover_send import (
    RECOVERY_ACTION_ID,
    RECOVERY_CASE_ID,
    configured_contactus_sent_verify,
    recover_failed_desk_send,
)
from bt_intake_proof.gates import store_path
from bt_intake_proof.store import ReceiptStore


def _apply_host_env() -> None:
    env_path = Path(os.environ.get("BT_INTAKE_ENV", "/etc/bt-intake-proof/env"))
    for key, value in load_env_file(env_path).items():
        os.environ.setdefault(key, value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--action-id", type=int, default=RECOVERY_ACTION_ID)
    parser.add_argument("--case-id", default=RECOVERY_CASE_ID)
    parser.add_argument("--store", default="", help="SQLite path override")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Authorize at most one execute_action call. Never re-queues. Default is dry-run.",
    )
    parser.add_argument("--live", action="store_true", help="read host env and BT_INTAKE_STORE")
    args = parser.parse_args(argv)
    if args.live or not args.store:
        _apply_host_env()
    path = Path(args.store) if args.store else store_path()
    store = ReceiptStore(path)
    try:
        layer = CaseLayer(store)
        verify = configured_contactus_sent_verify()
        send = None
        if args.execute:
            send = configured_send_transport()
            if isinstance(send, MissingContactusSendTransport):
                payload = recover_failed_desk_send(
                    layer,
                    action_id=args.action_id,
                    case_id=args.case_id,
                    execute=False,
                    verify_transport=verify,
                )
                payload["ok"] = False
                payload["mode"] = "execute_blocked"
                payload["blockers"] = list(payload.get("blockers") or []) + ["send_transport_missing"]
                print(json.dumps(payload, indent=2, default=str))
                return 2
        payload = recover_failed_desk_send(
            layer,
            action_id=args.action_id,
            case_id=args.case_id,
            execute=args.execute,
            send_transport=send,
            verify_transport=verify,
        )
    finally:
        store.close()
    print(json.dumps(payload, indent=2, default=str))
    if args.execute:
        return 0 if payload.get("ok") and payload.get("executed") else 2
    return 0 if payload.get("recovery_authorized") else 2


if __name__ == "__main__":
    raise SystemExit(main())
