#!/usr/bin/env python3
"""Intake-proof CLI. Stops at the first failed or blocked Google gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .gates import diagnose_google
from .cloud_auth import cloud_authorization_url
from .oauth_consent import OAuthClientError, authorization_url, blocked_oauth_url, exchange_code
from .scorecard import apply_local_contract_results, empty_scorecard, markdown_table, write_scorecard
from .setup_google import blocked_setup

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
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
