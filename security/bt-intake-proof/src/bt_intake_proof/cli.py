#!/usr/bin/env python3
"""Intake-proof CLI. Stops at the first failed or blocked Google gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .constants import MAILBOX
from .dispatch import build_constructor
from .cloud_auth import cloud_authorization_url
from .gates import diagnose_google, store_path
from .live_google import contactus_gmail
from .live_receive import receiver_access_token, receive_once
from .receiver import recover_from_cursor
from .oauth_consent import OAuthClientError, authorization_url, blocked_oauth_url, exchange_code
from .scorecard import apply_local_contract_results, empty_scorecard, markdown_table, write_scorecard
from .setup_google import blocked_setup
from .store import ReceiptStore

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"


def _print(payload: dict) -> None:
    print(json.dumps(payload, indent=2, default=str), flush=True)


def cmd_gate(_args: argparse.Namespace) -> int:
    diagnosis = diagnose_google()
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "phase1-google-gate.json").write_text(
        json.dumps(diagnosis, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    scorecard = empty_scorecard(
        "contactus@ Gmail read-only consent passed. Pub/Sub create is blocked on Cloud admin credentials or console-created topic."
    )
    write_scorecard(RESULTS / "scorecard.json", scorecard)
    _print({"google": diagnosis, "setup": blocked_setup(diagnosis), "scorecard_overall": scorecard["overall"]})
    return 0 if diagnosis["status"] == "READY" else 2


def cmd_setup(_args: argparse.Namespace) -> int:
    diagnosis = diagnose_google()
    setup = blocked_setup(diagnosis)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "phase1-setup.json").write_text(json.dumps(setup, indent=2, default=str) + "\n", encoding="utf-8")
    _print(setup)
    if setup["status"] != "READY":
        return 2
    return 0


def cmd_scorecard(_args: argparse.Namespace) -> int:
    path = RESULTS / "scorecard.json"
    if not path.exists():
        scorecard = empty_scorecard("Scorecard has not been generated yet.")
    else:
        scorecard = json.loads(path.read_text(encoding="utf-8"))
    print(markdown_table(scorecard), flush=True)
    _print({"overall": scorecard.get("overall"), "stopped_at": scorecard.get("stopped_at")})
    return 0


def cmd_oauth_url(_args: argparse.Namespace) -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    try:
        payload = authorization_url()
    except OAuthClientError:
        payload = blocked_oauth_url()
    (RESULTS / "oauth-url.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if payload.get("authorization_url"):
        (RESULTS / "AUTH_URL.txt").write_text(payload["authorization_url"] + "\n", encoding="utf-8")
    _print(payload)
    return 0 if payload.get("authorization_url") else 2


def cmd_cloud_oauth_url(_args: argparse.Namespace) -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    try:
        payload = cloud_authorization_url()
    except OAuthClientError as exc:
        payload = {"status": "BLOCKED", "authorization_url": None, "error": str(exc)}
        _print(payload)
        return 2
    safe = dict(payload)
    (RESULTS / "cloud-oauth-url.json").write_text(json.dumps(safe, indent=2) + "\n", encoding="utf-8")
    _print(safe)
    return 0


def cmd_oauth_exchange(args: argparse.Namespace) -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    try:
        payload = exchange_code(args.redirect)
    except OAuthClientError as exc:
        payload = {"status": "FAIL", "error": str(exc)}
        _print(payload)
        return 1
    safe = {k: v for k, v in payload.items() if k != "token_path"}
    (RESULTS / "gmail-consent.json").write_text(json.dumps(safe, indent=2) + "\n", encoding="utf-8")
    _print(safe)
    return 0


def _live_store() -> ReceiptStore:
    return ReceiptStore(store_path())


def cmd_receive_once(_args: argparse.Namespace) -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    store = _live_store()
    try:
        payload = receive_once(store, contactus_gmail(), receiver_access_token())
    except OAuthClientError as exc:
        payload = {"status": "FAIL", "error": str(exc)}
        _print(payload)
        return 1
    finally:
        store.close()
    (RESULTS / "live" / "last-receive.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _print(payload)
    return 0


def cmd_receive_loop(args: argparse.Namespace) -> int:
    import time

    RESULTS.mkdir(parents=True, exist_ok=True)
    store = _live_store()
    try:
        gmail = contactus_gmail()
        sa_token = receiver_access_token()
        started = time.time()
        while True:
            if time.time() - started > 50 * 60:
                gmail = contactus_gmail()
                sa_token = receiver_access_token()
                started = time.time()
            payload = receive_once(store, gmail, sa_token)
            (RESULTS / "live" / "last-receive.json").write_text(
                json.dumps(payload, indent=2) + "\n", encoding="utf-8"
            )
            if payload.get("pulled"):
                _print(payload)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0
    finally:
        store.close()


def cmd_recover(_args: argparse.Namespace) -> int:
    store = _live_store()
    try:
        result = recover_from_cursor(store, contactus_gmail())
    except OAuthClientError as exc:
        payload = {"status": "FAIL", "error": str(exc)}
        _print(payload)
        return 1
    finally:
        store.close()
    safe = {
        "ok": result.get("ok"),
        "acked": result.get("acked"),
        "receipt_count": result.get("receipt_count"),
        "eligible": [
            {
                "gmail_message_id": item.get("gmail_message_id"),
                "thread_id": item.get("thread_id"),
                "classification": item.get("classification"),
                "test_marker": item.get("test_marker"),
                "detection_path": item.get("detection_path"),
            }
            for item in (result.get("eligible") or [])
        ],
        "ineligible_count": len(result.get("ineligible") or []),
        "start_history_id": result.get("start_history_id"),
        "end_history_id": result.get("end_history_id"),
        "detection_path": result.get("detection_path"),
        "commit": {
            k: (result.get("commit") or {}).get(k)
            for k in ("ok", "inserted", "duplicates", "skipped_ineligible", "history_id")
        },
    }
    (RESULTS / "live" / "last-recover.json").write_text(json.dumps(safe, indent=2) + "\n", encoding="utf-8")
    _print(safe)
    return 0 if result.get("ok") else 1


def cmd_write_dispatch_payload(args: argparse.Namespace) -> int:
    store = _live_store()
    try:
        receipts = [item for item in store.eligible_receipts(MAILBOX) if item.get("gmail_message_id") == args.message_id] if args.message_id else store.eligible_receipts(MAILBOX)
    finally:
        store.close()
    if not receipts:
        payload = {"status": "FAIL", "error": "no eligible durable receipt"}
        _print(payload)
        return 1
    receipt = receipts[0]
    nonce = args.nonce or f"bt-intake-{receipt['gmail_message_id']}"
    constructor = build_constructor(receipt, nonce)
    dest = RESULTS / "live" / "codex-payload.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"constructor": constructor}, indent=2) + "\n", encoding="utf-8")
    dest.chmod(0o600)
    _print(
        {
            "status": "READY",
            "payload_path": str(dest),
            "gmail_message_id": receipt.get("gmail_message_id"),
            "test_marker": receipt.get("test_marker"),
            "nonce": nonce,
            "tool_name": constructor["tool_name"],
            "namespace": constructor["namespace"],
            "authorization": constructor["authorization"],
        }
    )
    return 0


def cmd_phasee_send_oauth_url(_args: argparse.Namespace) -> int:
    from .contactus_send import send_authorization_url

    RESULTS.mkdir(parents=True, exist_ok=True)
    try:
        payload = send_authorization_url()
    except OAuthClientError as exc:
        payload = {"status": "BLOCKED", "authorization_url": None, "error": str(exc)}
        _print(payload)
        return 2
    (RESULTS / "phasee-send-oauth-url.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "SEND_AUTH_URL.txt").write_text(str(payload.get("authorization_url") or "") + "\n", encoding="utf-8")
    _print(payload)
    return 0


def cmd_phasee_send_oauth_exchange(args: argparse.Namespace) -> int:
    from .contactus_send import exchange_send_code

    RESULTS.mkdir(parents=True, exist_ok=True)
    try:
        payload = exchange_send_code(args.redirect)
    except (OAuthClientError, Exception) as exc:
        payload = {"status": "FAIL", "error": str(exc)}
        _print(payload)
        return 1
    safe = {k: v for k, v in payload.items() if k != "token_path"}
    (RESULTS / "phasee-send-consent.json").write_text(json.dumps(safe, indent=2) + "\n", encoding="utf-8")
    _print(safe)
    return 0


def cmd_phasee_execute(args: argparse.Namespace) -> int:
    from .bounded_send import execute_action
    from .cases import CaseLayer
    from .contactus_send import configured_send_transport
    from .send_bind import ensure_send_tables

    RESULTS.mkdir(parents=True, exist_ok=True)
    store = _live_store()
    try:
        layer = CaseLayer(store)
        ensure_send_tables(layer)
        result = execute_action(layer, int(args.action_id), configured_send_transport())
    finally:
        store.close()
    dest = RESULTS / "live" / "phasee-execute.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    _print(result)
    return 0 if result.get("ok") else 2


def cmd_phasee_verify(args: argparse.Namespace) -> int:
    from .cases import CaseLayer
    from .send_bind import ensure_send_tables
    from .send_verify import ContactusReadonlySentVerify, verify_sent

    RESULTS.mkdir(parents=True, exist_ok=True)
    store = _live_store()
    try:
        layer = CaseLayer(store)
        ensure_send_tables(layer)
        result = verify_sent(layer, int(args.action_id), ContactusReadonlySentVerify(contactus_gmail()))
    finally:
        store.close()
    dest = RESULTS / "live" / "phasee-verify-sent.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    _print(result)
    return 0 if result.get("ok") else 2


def cmd_lead_desk_packets(args: argparse.Namespace) -> int:
    from .desk_packets import build_desk_packets, write_desk_packets

    store = Path(args.store) if args.store else store_path()
    dest = Path(args.out) if args.out else RESULTS / "live" / "desk-packets"
    payload = build_desk_packets(store, case_id=args.case_id or None)
    write_desk_packets(payload, dest)
    safe = {
        "status": "PASS",
        "generated_at": payload.get("generated_at"),
        "store_fingerprint": payload.get("store_fingerprint"),
        "store_unchanged": payload.get("store_unchanged"),
        "case_id": payload.get("case_id"),
        "health_overall": payload.get("health_overall"),
        "queue_count": payload.get("queue_count"),
        "subjects": [item.get("subject") for item in payload.get("emails") or []],
        "out": str(dest),
        "public_ingress": False,
        "chatgpt_mcp_mobile": "not_used",
    }
    (RESULTS / "phasef1-packets.json").write_text(json.dumps(safe, indent=2) + "\n", encoding="utf-8")
    _print(safe)
    return 0


def cmd_record_local_tests(args: argparse.Namespace) -> int:
    scorecard = empty_scorecard(
        "contactus@ Gmail read-only consent passed. Pub/Sub create is blocked on Cloud admin credentials or console-created topic."
    )
    apply_local_contract_results(scorecard, bool(args.passed), args.output or "")
    write_scorecard(RESULTS / "scorecard.json", scorecard)
    _print({"overall": scorecard["overall"], "gates": {k: v["result"] for k, v in scorecard["gates"].items()}})
    return 0 if args.passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="B&T contactus intake proof")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("gate").set_defaults(func=cmd_gate)
    sub.add_parser("setup").set_defaults(func=cmd_setup)
    sub.add_parser("scorecard").set_defaults(func=cmd_scorecard)
    rec = sub.add_parser("record-local-tests")
    rec.add_argument("--passed", action="store_true")
    rec.add_argument("--output", default="")
    rec.set_defaults(func=cmd_record_local_tests)
    sub.add_parser("oauth-url").set_defaults(func=cmd_oauth_url)
    sub.add_parser("cloud-oauth-url").set_defaults(func=cmd_cloud_oauth_url)
    ex = sub.add_parser("oauth-exchange")
    ex.add_argument("redirect", help="localhost redirect URL or code from contactus consent")
    ex.set_defaults(func=cmd_oauth_exchange)
    sub.add_parser("receive-once").set_defaults(func=cmd_receive_once)
    loop = sub.add_parser("receive-loop")
    loop.add_argument("--interval", type=float, default=2.0)
    loop.set_defaults(func=cmd_receive_loop)
    disp = sub.add_parser("write-dispatch-payload")
    disp.add_argument("--message-id", default="")
    disp.add_argument("--nonce", default="")
    disp.set_defaults(func=cmd_write_dispatch_payload)
    sub.add_parser("recover").set_defaults(func=cmd_recover)
    sub.add_parser("phasee-send-oauth-url").set_defaults(func=cmd_phasee_send_oauth_url)
    pex = sub.add_parser("phasee-send-oauth-exchange")
    pex.add_argument("redirect", help="localhost redirect URL or code from contactus send-only consent")
    pex.set_defaults(func=cmd_phasee_send_oauth_exchange)
    pe = sub.add_parser("phasee-execute")
    pe.add_argument("action_id", type=int, help="stored case_send_actions.id; does not auto-select")
    pe.set_defaults(func=cmd_phasee_execute)
    pv = sub.add_parser("phasee-verify")
    pv.add_argument("action_id", type=int, help="stored case_send_actions.id")
    pv.set_defaults(func=cmd_phasee_verify)
    desk = sub.add_parser("lead-desk-packets")
    desk.add_argument("--store", default="", help="readonly SQLite path; defaults to BT_INTAKE_STORE")
    desk.add_argument("--out", default="", help="directory for desk-queue/case/health files")
    desk.add_argument("--case-id", default="", help="optional case to detail; default is newest inbound")
    desk.set_defaults(func=cmd_lead_desk_packets)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
