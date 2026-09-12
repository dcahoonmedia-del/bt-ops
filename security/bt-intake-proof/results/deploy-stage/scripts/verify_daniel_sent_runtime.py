#!/usr/bin/env python3
"""Probe ExistingDanielSentLookup as the service identity. Prints no secrets."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bt_intake_proof.desk_deploy_env import load_env_file
from bt_intake_proof.desk_sent_proof import (
    ExistingDanielSentLookup,
    REASON_ACCESS_BLOCKED,
    diagnose_daniel_sent_access,
)
from bt_intake_proof.gates import daniel_sent_token_path


def _apply_host_env() -> None:
    env_path = Path(os.environ.get("BT_INTAKE_ENV", "/etc/bt-intake-proof/env"))
    for key, value in load_env_file(env_path).items():
        os.environ.setdefault(key, value)


def main() -> int:
    _apply_host_env()
    path = daniel_sent_token_path()
    access = diagnose_daniel_sent_access()
    payload = {
        "diagnose_status": access.get("status"),
        "available": bool(access.get("available")),
        "token_present": bool(access.get("token_present")),
        "token_path": str(path),
        "token_email": access.get("token_email"),
        "readonly_only": access.get("status") == "READY",
        "reason": access.get("reason"),
        "live_lookup": None,
        "boolean_bypass": False,
    }
    if access.get("available"):
        found = ExistingDanielSentLookup().find_by_rfc_message_id(
            "desk-rt-probe-not-a-real-message@btpestcontrol.com"
        )
        payload["live_lookup"] = {
            "status": found.status,
            "reason": found.reason,
            "record_count": len(found.records),
            "blocked": found.status == "blocked" or found.reason == REASON_ACCESS_BLOCKED,
        }
        payload["ok"] = found.status != "blocked" and found.reason != REASON_ACCESS_BLOCKED
    else:
        payload["ok"] = False
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
