#!/usr/bin/env python3
"""Intake-proof CLI. Stops at the first failed or blocked Google gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .gates import diagnose_google
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
        "Waiting for a real Google Cloud project ID and Desktop OAuth client JSON. Placeholder IDs are rejected."
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


def cmd_record_local_tests(args: argparse.Namespace) -> int:
    scorecard = empty_scorecard(
        "Waiting for a real Google Cloud project ID and Desktop OAuth client JSON. Placeholder IDs are rejected."
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
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
