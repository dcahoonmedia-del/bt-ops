"""PASS / FAIL / BLOCKED scorecard for the intake proof only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .gates import diagnose_google

GATES = (
    "gmail_watch_registration",
    "pubsub_delivery",
    "new_message_automatic_capture",
    "old_thread_reply_capture",
    "state_preservation",
    "durable_storage",
    "deduplication",
    "recovery_after_receiver_downtime",
    "codex_external_message_delivery",
)


def empty_scorecard(reason: str) -> dict[str, Any]:
    diagnosis = diagnose_google()
    gates = {name: {"result": "BLOCKED", "detail": reason} for name in GATES}
    return {
        "overall": "BLOCKED",
        "stopped_at": "phase_1_google_setup",
        "reason": reason,
        "gates": gates,
        "google": diagnosis,
        "local_contract_tests": None,
    }


def apply_local_contract_results(scorecard: dict[str, Any], tests_passed: bool, test_output: str) -> dict[str, Any]:
    scorecard["local_contract_tests"] = {
        "passed": tests_passed,
        "output": test_output[-4000:],
    }
    note = (
        "Local SQLite/eligibility/ack contract tests passed. Live mailbox write is blocked on Google setup."
        if tests_passed
        else "Local contract tests failed; stop before live Gmail work."
    )
    for name in ("durable_storage", "deduplication"):
        if tests_passed:
            scorecard["gates"][name] = {
                "result": "BLOCKED",
                "detail": note,
                "local_contract": "PASS",
            }
        else:
            scorecard["gates"][name] = {"result": "FAIL", "detail": note, "local_contract": "FAIL"}
    if not tests_passed:
        scorecard["overall"] = "FAIL"
        scorecard["stopped_at"] = "local_contract_tests"
    return scorecard


def write_scorecard(path: Path, scorecard: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scorecard, indent=2, default=str) + "\n", encoding="utf-8")


def markdown_table(scorecard: dict[str, Any]) -> str:
    lines = [
        "| Gate | Result | Detail |",
        "| --- | --- | --- |",
    ]
    for name in GATES:
        item = scorecard["gates"][name]
        detail = str(item.get("detail") or "").replace("\n", " ")
        lines.append(f"| {name} | {item['result']} | {detail} |")
    return "\n".join(lines)
