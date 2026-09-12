"""Always-on host loop around the proven intake path. No intake-logic redesign."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .constants import (
    CODEX_NAMESPACE,
    CODEX_TOOL_NAME,
    DISPATCH_FAILED,
    DISPATCH_PENDING,
    MAILBOX,
    MARKER_PREFIX,
)
from .case_manager import process_cases
from .dispatch import build_constructor
from .gce_identity import receiver_identity
from .gates import store_path
from .live_google import contactus_gmail, register_watch_on_existing_topic, renew_watch_preserving_cursor
from .live_receive import receive_once, receiver_access_token
from .receiver import recover_from_cursor
from .store import ReceiptStore, utc_now

ROOT = Path(__file__).resolve().parents[2]
ISOLATION_DISPATCH = ROOT.parent / "codex-external-isolation" / "scripts" / "host_intake_dispatch.sh"


def safe_log(event: str, **fields: Any) -> None:
    """Structured logs without message bodies."""
    blocked = {"body", "body_text", "raw_message", "raw", "content", "payload"}
    record = {"event": event, "at": utc_now()}
    for key, value in fields.items():
        if key in blocked:
            continue
        record[key] = value
    print(json.dumps(record, default=str), flush=True)


def dispatch_pending(store: ReceiptStore) -> list[dict[str, Any]]:
    """Send durable eligible receipts through the existing isolated ExternalMessage path."""
    results = []
    for receipt in store.eligible_receipts(MAILBOX):
        if str(receipt.get("codex_dispatch_state") or "") != DISPATCH_PENDING:
            continue
        marker = str(receipt.get("test_marker") or "")
        if not marker.startswith(MARKER_PREFIX):
            continue
        nonce = f"bt-cloud-{receipt['gmail_message_id']}"
        constructor = build_constructor(receipt, nonce)
        payload_path = store.path.parent / f"dispatch-{receipt['gmail_message_id']}.json"
        payload_path.write_text(json.dumps({"constructor": constructor}, indent=2) + "\n", encoding="utf-8")
        # Isolation container runs as uid 1000; btintake is 999. 0600 is unreadable inside Docker.
        payload_path.chmod(0o644)
        if not ISOLATION_DISPATCH.exists():
            results.append({"gmail_message_id": receipt["gmail_message_id"], "status": "BLOCKED", "reason": "dispatch_script_missing"})
            continue
        completed = subprocess.run(
            ["bash", str(ISOLATION_DISPATCH), str(payload_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        ok = completed.returncode == 0
        if ok:
            store.mark_dispatched(MAILBOX, receipt["gmail_message_id"], nonce)
        else:
            store.conn.execute(
                "UPDATE receipts SET codex_dispatch_state = ? WHERE mailbox = ? AND gmail_message_id = ?",
                (DISPATCH_FAILED, MAILBOX, receipt["gmail_message_id"]),
            )
        err = (completed.stderr or completed.stdout or "")[-400:].replace("\n", " ")
        results.append(
            {
                "gmail_message_id": receipt["gmail_message_id"],
                "test_marker": marker,
                "status": "PASS" if ok else "FAIL",
                "tool_name": CODEX_TOOL_NAME,
                "namespace": CODEX_NAMESPACE,
                "returncode": completed.returncode,
            }
        )
        safe_log(
            "codex_dispatch",
            gmail_message_id=receipt["gmail_message_id"],
            test_marker=marker,
            status="PASS" if ok else "FAIL",
            returncode=completed.returncode,
            error_tail=err if not ok else None,
        )
    return results


def run_once(store: ReceiptStore) -> dict[str, Any]:
    identity = receiver_identity()
    gmail = contactus_gmail()
    token = receiver_access_token()
    recover = recover_from_cursor(store, gmail)
    watch = renew_watch_preserving_cursor(store)
    received = receive_once(store, gmail, token)
    dispatched = dispatch_pending(store)
    cases = process_cases(store)
    return {
        "identity": identity,
        "recover": {
            "ok": recover.get("ok"),
            "receipt_count": recover.get("receipt_count"),
            "start_history_id": recover.get("start_history_id"),
            "end_history_id": recover.get("end_history_id"),
            "detection_path": recover.get("detection_path"),
        },
        "watch": {
            "status": watch.get("status"),
            "history_id": (watch.get("watch") or watch).get("history_id") if isinstance(watch.get("watch") or watch, dict) else None,
            "reason": watch.get("reason"),
        },
        "receive": received,
        "dispatch": dispatched,
        "cases": {
            "synced": [
                {k: item.get(k) for k in ("case_id", "created", "reopened", "approval_superseded", "ok", "decision", "reason", "skipped")}
                for item in cases.get("synced") or []
            ],
            "drafted": [
                {k: item.get(k) for k in ("case_id", "status", "version", "reason")}
                for item in cases.get("drafted") or []
            ],
            "phasee_queued": [
                {
                    "ok": item.get("ok"),
                    "reason": item.get("reason"),
                    "skipped": item.get("skipped"),
                    "action_id": (item.get("action") or {}).get("id"),
                    "status": (item.get("action") or {}).get("status"),
                }
                for item in cases.get("phasee_queued") or []
            ],
        },
    }


def serve(interval: float = 2.0) -> int:
    store = ReceiptStore(store_path())
    identity = receiver_identity()
    safe_log("cloud_host_start", **identity, store=str(store.path), mailbox=MAILBOX)
    try:
        if not store.get_watch(MAILBOX):
            watch0 = register_watch_on_existing_topic(store)
            safe_log(
                "initial_watch",
                status=watch0.get("status"),
                history_id=(watch0.get("watch") or {}).get("history_id"),
            )
        gmail = contactus_gmail()
        token = receiver_access_token()
        recover = recover_from_cursor(store, gmail)
        safe_log(
            "startup_recover",
            ok=recover.get("ok"),
            receipt_count=recover.get("receipt_count"),
            start_history_id=recover.get("start_history_id"),
            end_history_id=recover.get("end_history_id"),
        )
        last_refresh = time.time()
        while True:
            if time.time() - last_refresh > 45 * 60:
                gmail = contactus_gmail()
                token = receiver_access_token()
                last_refresh = time.time()
            watch = renew_watch_preserving_cursor(store)
            if watch.get("status") not in {"SKIPPED", None}:
                safe_log("watch_renew", status=watch.get("status"), history_id=(watch.get("watch") or {}).get("history_id"))
            received = receive_once(store, gmail, token)
            if received.get("pulled"):
                safe_log(
                    "pubsub_pull",
                    pulled=received.get("pulled"),
                    acked_count=received.get("acked_count"),
                    processed=received.get("processed"),
                )
            dispatch_pending(store)
            cases = process_cases(store)
            if cases.get("synced") or cases.get("drafted") or cases.get("phasee_queued"):
                safe_log(
                    "case_manager",
                    synced=[
                        {k: item.get(k) for k in ("case_id", "created", "reopened", "approval_superseded", "ok", "decision", "reason", "skipped")}
                        for item in cases.get("synced") or []
                    ],
                    drafted=[
                        {k: item.get(k) for k in ("case_id", "status", "version", "reason")}
                        for item in cases.get("drafted") or []
                    ],
                    phasee_queued=[
                        {
                            "ok": item.get("ok"),
                            "reason": item.get("reason"),
                            "action_id": (item.get("action") or {}).get("id"),
                            "status": (item.get("action") or {}).get("status"),
                        }
                        for item in cases.get("phasee_queued") or []
                    ],
                )
            time.sleep(interval)
    except KeyboardInterrupt:
        safe_log("cloud_host_stop")
        return 0
    finally:
        store.close()


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    interval = float(os.environ.get("BT_INTAKE_INTERVAL", "2"))
    if args and args[0] == "once":
        store = ReceiptStore(store_path())
        try:
            print(json.dumps(run_once(store), indent=2, default=str), flush=True)
        finally:
            store.close()
        return 0
    return serve(interval)


if __name__ == "__main__":
    raise SystemExit(main())
