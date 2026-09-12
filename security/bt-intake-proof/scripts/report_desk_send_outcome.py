#!/usr/bin/env python3
"""Inspect action 2 send stages or enqueue one accurate result. Does not resend."""

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

from bt_intake_proof.cases import CaseLayer
from bt_intake_proof.desk_deploy_env import load_env_file
from bt_intake_proof.desk_recover_send import RECOVERY_ACTION_ID, RECOVERY_CASE_ID, configured_contactus_sent_verify
from bt_intake_proof.desk_report import report_desk_send_outcome
from bt_intake_proof.gates import store_path
from bt_intake_proof.send_verify import configured_daniel_inbox_verify
from bt_intake_proof.store import ReceiptStore


def _apply_host_env() -> None:
    env_path = Path(os.environ.get("BT_INTAKE_ENV", "/etc/bt-intake-proof/env"))
    for key, value in load_env_file(env_path).items():
        os.environ.setdefault(key, value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--action-id", type=int, default=RECOVERY_ACTION_ID)
    parser.add_argument("--case-id", default=RECOVERY_CASE_ID)
    parser.add_argument("--store", default="")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--verify-sent", action="store_true", help="Run contactus Sent verify. Does not send.")
    parser.add_argument(
        "--verify-recipient",
        action="store_true",
        help="Run existing recipient verifier via daniel@ readonly. Does not send or change labels.",
    )
    parser.add_argument(
        "--enqueue-result",
        action="store_true",
        help="Enqueue one accurate current-stage result. Does not resend the proof.",
    )
    args = parser.parse_args(argv)
    if args.live or not args.store:
        _apply_host_env()
    path = Path(args.store) if args.store else store_path()
    store = ReceiptStore(path)
    try:
        layer = CaseLayer(store)
        sent = configured_contactus_sent_verify()
        inbox = configured_daniel_inbox_verify()
        payload = report_desk_send_outcome(
            layer,
            action_id=args.action_id,
            case_id=args.case_id,
            verify_sent_live=args.verify_sent,
            verify_recipient_live=args.verify_recipient,
            enqueue_result=args.enqueue_result,
            sent_transport=sent,
            inbox_transport=inbox,
        )
    finally:
        store.close()
    print(json.dumps(payload, indent=2, default=str))
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
