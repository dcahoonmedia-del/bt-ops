#!/usr/bin/env python3
"""Write isolated office-accept review artifacts. Does not touch production SQLite."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.office_accept_pack import run_office_accept_pack


def main() -> int:
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results" / "office-accept"
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        result = run_office_accept_pack(Path(tmp) / "office-accept.sqlite")
    (dest / "SCENARIO_RESULTS.json").write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    lines = [
        "# Isolated proof-console review (synthetic)",
        "",
        "Generated from `LeadDesk` over a throwaway SQLite file. Not live mail.",
        "Interpretation of spoken requests is simulated in OPERATOR_WALKTHROUGH.md.",
        "",
        f"Pack ok: {result['ok']}",
        "",
    ]
    for item in result["scenarios"]:
        lines.append(f"- {item['name']}: **{item['status']}** — {item.get('notes') or ''}")
    lines.extend(["", "## Cases", ""])
    for item in result["console"]["cases"]:
        lines.append(
            f"- `{item['case_id']}` owner={item['owner']} stage={item['stage']} "
            f"draft={item['draft_exists']} attention={item['attention_reason']}"
        )
        hold = item.get("office_hold")
        if hold:
            lines.append(f"  hold/office: {hold}")
    lines.extend(["", "## Scenario table", ""])
    lines.append("| Scenario | Result |")
    lines.append("| --- | --- |")
    for item in result["scenarios"]:
        lines.append(f"| {item['name']} | {item['status']} |")
    lines.extend(["", "## Unsupported / blocked", ""])
    for item in result["unsupported"]:
        lines.append(f"- `{item['id']}` **{item['status']}**: {item['detail']}")
    (dest / "REVIEW_ARTIFACT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "dest": str(dest)}, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
