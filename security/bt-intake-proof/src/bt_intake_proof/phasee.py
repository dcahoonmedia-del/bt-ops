"""Phase E exact internal send helpers. No Fieldwork. No customer mail."""

from __future__ import annotations

from typing import Any

from .cases import CaseLayer
from .phasee_constants import PHASEE_BODY, PHASEE_CASE_MARKER, PHASEE_SEND_MARKER
from .send_bind import is_phasee_body


def is_phasee_receipt(receipt: dict[str, Any] | None) -> bool:
    blob = f"{(receipt or {}).get('test_marker') or ''} {(receipt or {}).get('subject') or ''} {(receipt or {}).get('body_text') or ''}"
    return PHASEE_CASE_MARKER in blob or PHASEE_SEND_MARKER in blob


def exact_phasee_draft() -> dict[str, Any]:
    return {
        "classification": "internal_phase_e_send_test",
        "known_facts": [
            "Internal B&T test only",
            "From contactus@ to daniel@ only",
            "No CC, BCC, attachments, or links",
        ],
        "missing_info": [],
        "recommended_next_step": "Daniel approves this exact version to authorize one bounded send",
        "proposed_response": PHASEE_BODY,
        "channel": "email",
        "judgment_needed": "Approve only if the exact body below is what should be sent once",
        "reasoning_summary": "Phase E exact-approval send test. Not a customer promise.",
    }


def install_phasee_draft(layer: CaseLayer, case_id: str, nonce: str) -> dict[str, Any]:
    return layer.save_draft(case_id, exact_phasee_draft(), nonce, label_not_sent=False)


def review_footer(is_phasee: bool) -> str:
    if is_phasee:
        return (
            f"This Phase E packet authorizes one bounded send of the exact body above "
            f"from contactus@ to daniel@ only. Marker {PHASEE_SEND_MARKER}. "
            "A generic or stale approval will not send."
        )
    return "Approval is recorded only. It will not send a customer message."
