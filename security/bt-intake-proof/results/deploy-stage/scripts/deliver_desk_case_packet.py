#!/usr/bin/env python3
"""Deliver CASE (optionally QUEUE/HEALTH) contactus→daniel. Never the proof reply."""

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
from bt_intake_proof.desk_fresh_case import deliver_case_packets, fresh_case_id
from bt_intake_proof.gates import store_path
from bt_intake_proof.store import ReceiptStore


def _apply_host_env() -> None:
    env_path = Path(os.environ.get("BT_INTAKE_ENV", "/etc/bt-intake-proof/env"))
    for key, value in load_env_file(env_path).items():
        os.environ.setdefault(key, value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", default="")
    parser.add_argument("--also-queue-health", action="store_true")
    args = parser.parse_args(argv)
    _apply_host_env()
    path = Path(args.store) if args.store else store_path()
    kinds = ("case", "queue", "health") if args.also_queue_health else ("case",)
    store = ReceiptStore(path)
    try:
        result = deliver_case_packets(store, kinds=kinds)
    finally:
        store.close()
    result["case_id"] = fresh_case_id()
    result["note"] = (
        "This is an internal desk packet only. It is not the approved proof reply "
        "and does not record approve_send."
    )
    print(json.dumps(result, indent=2, default=str))
    if result.get("proof_reply_sent"):
        return 2
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
