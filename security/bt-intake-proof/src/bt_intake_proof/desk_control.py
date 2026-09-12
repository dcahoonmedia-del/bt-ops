"""Lead Desk control: ChatGPT sends a structured action; the backend authorizes.

Production path: Daniel speaks to ChatGPT → ChatGPT chooses one intent →
submit_desk_action → Phase E / ownership / freshness checks.

normalize_desk_intent is a temporary Python fallback only. Do not grow its
phrase lists or model Daniel's speech here.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from .send_bind import reject_reasons

INTENT_APPROVE_SEND = "approve_and_send_current"
INTENT_APPROVE_DRAFT = "approve_draft_only"
INTENT_REVISE = "revise_draft"
INTENT_HOLD = "hold"
INTENT_OFFICE = "office_owned"
INTENT_NO_RESPONSE = "no_response_needed"
INTENT_REQUEST_INFO = "request_information"
INTENT_CONDITIONAL = "conditional_instruction"
INTENT_AMBIGUOUS = "ambiguous_needs_confirmation"

SOURCE_CHATGPT = "chatgpt_structured"
SOURCE_FALLBACK = "python_utterance_fallback"

INTENTS = (
    INTENT_APPROVE_SEND,
    INTENT_APPROVE_DRAFT,
    INTENT_REVISE,
    INTENT_HOLD,
    INTENT_OFFICE,
    INTENT_NO_RESPONSE,
    INTENT_REQUEST_INFO,
    INTENT_CONDITIONAL,
    INTENT_AMBIGUOUS,
)

QUESTION_OFFER_SEND = "offer_send"
QUESTION_REVIEW_WORDING = "review_wording"
QUESTION_ASK_OWNER = "ask_owner"

OFFICE_STAFF = {
    "brenda": {"name": "Brenda", "role": "office", "email": "brenda@btpestcontrol.com"},
    "ally": {"name": "Ally", "role": "office", "email": "ally@btpestcontrol.com"},
}

_SPLIT = re.compile(
    r"\s*(?:[-—,]?\s*)?(?:\bactually\s+wait\b|\bactually\b|\bwait[,.]?\b|\bbut\b|\bhowever\b|\bhold on\b)\s*",
    re.I,
)
_CONDITIONAL = re.compile(
    r"\b(?:if|unless|when she|when they|once she|once they|after she|after they)\b",
    re.I,
)
_NEGATE_ACTION = re.compile(
    r"\b(?:don'?t|do not|never|not)\s+(?:send|do it|go ahead|approve)?\b|\bdon'?t send\b|\bdo not send\b",
    re.I,
)
_REVISE = re.compile(
    r"\b(?:make it shorter|make it longer|rewrite|rephrase|change (?:it|the|that)|fix (?:it|the)|edit|revise|word it|shorter first)\b",
    re.I,
)
_SENDISH = re.compile(r"\b(?:send|do it|go ahead)\b", re.I)
_AFFIRM = re.compile(
    r"\b(?:yeah|yep|yes|ok|okay|looks good|that works|that'?s fine|fine|good|approved?)\b",
    re.I,
)
_NO_REPLY = re.compile(r"\b(?:no response|don'?t (?:reply|respond)|no reply needed|leave it)\b", re.I)
_HOLD = re.compile(r"\b(?:hold(?: this)?|park it|pause(?: this)?|wait on this)\b", re.I)
_REQUEST = re.compile(r"\b(?:ask (?:her|him|them)|find out|get the|need (?:the )?address|request)\b", re.I)
_OFFICE_GENERIC = re.compile(
    r"\b(?:the office (?:has|owns) this|office has this|leave this with the office|office[- ]owned)\b",
    re.I,
)
_REASSIGN_TO_DANIEL = re.compile(
    r"\b(?:i(?:'ll| will) (?:take|handle) (?:this|it)|give it back to me|i(?:'m| am) taking this)\b",
    re.I,
)


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("—", "-").replace("–", "-")).strip()


def _clauses(utterance: str) -> list[str]:
    parts = [part.strip(" -,.") for part in _SPLIT.split(utterance) if part and part.strip(" -,.")]
    return parts or [utterance.strip()]


def _office_mentions(text: str) -> list[str]:
    found = []
    lower = text.lower()
    for key in OFFICE_STAFF:
        if re.search(rf"\b{key}\b", lower):
            found.append(key)
    return found


def _signals(text: str) -> dict[str, bool]:
    return {
        "conditional": bool(_CONDITIONAL.search(text)),
        "negate": bool(_NEGATE_ACTION.search(text)),
        "revise": bool(_REVISE.search(text)),
        "sendish": bool(_SENDISH.search(text)),
        "affirm": bool(_AFFIRM.search(text)),
        "no_reply": bool(_NO_REPLY.search(text)),
        "hold": bool(_HOLD.search(text)) and not _REVISE.search(text),
        "request": bool(_REQUEST.search(text)),
        "office_generic": bool(_OFFICE_GENERIC.search(text)),
        "office_people": _office_mentions(text),
        "reassign_daniel": bool(_REASSIGN_TO_DANIEL.search(text)),
        "or_choice": bool(re.search(r"\bbrenda\b.*\bor\b.*\bally\b|\bally\b.*\bor\b.*\bbrenda\b", text, re.I)),
    }


def _clarification(intent: str, *, office_people: list[str] | None = None) -> str | None:
    if intent == INTENT_AMBIGUOUS:
        return "Want me to send this version, or just keep the draft?"
    if intent == INTENT_OFFICE and office_people and len(office_people) > 1:
        return "Brenda or Ally?"
    return None


def structured_action(
    intent: str | Mapping[str, Any] | None = None,
    *,
    owner: str | None = None,
    note: str | None = None,
    reassign_to_daniel: bool = False,
) -> dict[str, Any]:
    """Validate a small ChatGPT action. This is not speech interpretation."""
    if isinstance(intent, Mapping):
        owner = intent.get("owner") if owner is None else owner
        note = intent.get("note") if note is None else note
        reassign_to_daniel = bool(intent.get("reassign_to_daniel", reassign_to_daniel))
        intent = intent.get("intent")
    if not intent:
        return {
            "ok": False,
            "source": SOURCE_CHATGPT,
            "intent": intent,
            "execute_send": False,
            "reason": "missing_structured_intent",
        }
    if intent not in INTENTS:
        return {
            "ok": False,
            "source": SOURCE_CHATGPT,
            "intent": intent,
            "execute_send": False,
            "reason": "unknown_intent",
        }
    who = (owner or "").lower() or None
    return {
        "ok": True,
        "source": SOURCE_CHATGPT,
        "intent": intent,
        "execute_send": intent == INTENT_APPROVE_SEND,
        "owner": who,
        "note": note,
        "reassign_to_daniel": reassign_to_daniel,
        "preserve_existing_office_owner": who in OFFICE_STAFF or who == "office",
        "requires_case_id_from_daniel": False,
        "requires_magic_phrase": False,
    }


def submit_desk_action(
    action: Mapping[str, Any] | str,
    **authorize_kwargs: Any,
) -> dict[str, Any]:
    """Primary ChatGPT path: accept a structured action and authorize it.

    Never sends. A later execute_action call still needs a stored Phase E
    action id and the same case/version/payload/freshness checks.
    """
    parsed = structured_action(action if isinstance(action, Mapping) else {"intent": action})
    if not parsed.get("ok"):
        return parsed
    result = authorize_desk_intent(parsed, **authorize_kwargs)
    result["source"] = SOURCE_CHATGPT
    result["action"] = parsed
    return result


def normalize_desk_intent(utterance: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Temporary fallback if ChatGPT cannot submit a structured action. Do not expand."""
    ctx = context or {}
    text = _norm(utterance)
    question = str(ctx.get("last_question_kind") or "")
    displayed = bool(ctx.get("displayed_case") or ctx.get("displayed_draft"))
    current_owner = str(ctx.get("owner") or ctx.get("current_owner") or "daniel").lower()
    clauses = _clauses(text)
    last = _signals(clauses[-1])
    whole = _signals(text)
    later_overrides = last

    intent = INTENT_AMBIGUOUS
    owner = None
    office_people = later_overrides["office_people"] or whole["office_people"]

    if later_overrides["negate"] and (later_overrides["sendish"] or whole["sendish"] or later_overrides["affirm"]):
        intent = INTENT_HOLD if later_overrides["hold"] else INTENT_NO_RESPONSE
        if "don't send" in text.lower() or "do not send" in text.lower() or later_overrides["sendish"]:
            intent = INTENT_NO_RESPONSE
    elif later_overrides["conditional"] and (later_overrides["sendish"] or whole["sendish"]):
        intent = INTENT_CONDITIONAL
    elif later_overrides["revise"]:
        intent = INTENT_REVISE
    elif later_overrides["or_choice"] or (len(office_people) > 1):
        intent = INTENT_OFFICE
        owner = None
    elif office_people and (
        re.search(r"\b(?:leave|give|handling|has this|owns|with)\b", text, re.I) or later_overrides["office_generic"]
    ):
        intent = INTENT_OFFICE
        owner = office_people[0] if len(office_people) == 1 else None
    elif later_overrides["office_generic"] or whole["office_generic"]:
        intent = INTENT_OFFICE
        owner = "office"
    elif later_overrides["request"]:
        intent = INTENT_REQUEST_INFO
    elif later_overrides["hold"] and not later_overrides["sendish"]:
        intent = INTENT_HOLD
    elif later_overrides["no_reply"]:
        intent = INTENT_NO_RESPONSE
    elif later_overrides["sendish"] and not later_overrides["negate"] and not later_overrides["conditional"]:
        intent = INTENT_APPROVE_SEND if displayed or question == QUESTION_OFFER_SEND else INTENT_AMBIGUOUS
    elif later_overrides["affirm"]:
        if question == QUESTION_OFFER_SEND and displayed:
            intent = INTENT_APPROVE_SEND
        elif question == QUESTION_REVIEW_WORDING:
            intent = INTENT_AMBIGUOUS
        else:
            intent = INTENT_AMBIGUOUS
    else:
        intent = INTENT_AMBIGUOUS

    if current_owner in OFFICE_STAFF and intent == INTENT_APPROVE_SEND and not later_overrides["reassign_daniel"]:
        # Surface activity later; do not silently take the case or send as AI.
        intent = INTENT_OFFICE
        owner = current_owner

    execute_send = intent == INTENT_APPROVE_SEND
    return {
        "source": SOURCE_FALLBACK,
        "intent": intent,
        "execute_send": execute_send,
        "owner": owner,
        "office_staff_recognized": list(OFFICE_STAFF),
        "preserve_existing_office_owner": current_owner in OFFICE_STAFF and not later_overrides["reassign_daniel"],
        "requires_case_id_from_daniel": False,
        "requires_magic_phrase": False,
        "utterance": text,
        "last_question_kind": question or None,
        "clarification": _clarification(intent, office_people=office_people),
        "notes": {
            "later_clause_overrides_earlier": len(clauses) > 1,
            "clauses": clauses,
        },
    }


def authorize_desk_intent(
    inferred: dict[str, Any],
    *,
    binding: dict[str, Any] | None = None,
    case: dict[str, Any] | None = None,
    draft: dict[str, Any] | None = None,
    hold: bool = False,
    owner: str | None = None,
    latest_inbound_message_id: str | None = None,
    displayed_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Backend authorization. The model's intent is not execution."""
    intent = inferred.get("intent")
    source = inferred.get("source") or SOURCE_FALLBACK
    if intent not in INTENTS:
        return {"ok": False, "source": source, "execute_send": False, "reason": "unknown_intent"}
    if intent != INTENT_APPROVE_SEND:
        return {
            "ok": True,
            "source": source,
            "execute_send": False,
            "intent": intent,
            "reason": "non_send_intent",
            "owner": inferred.get("owner") or owner,
        }

    blocks = []
    who = str(owner or inferred.get("owner") or (case or {}).get("owner") or "").lower()
    if hold or (case or {}).get("hold"):
        blocks.append("hold")
    if who in OFFICE_STAFF or who == "office" or inferred.get("preserve_existing_office_owner"):
        if not inferred.get("reassign_to_daniel"):
            blocks.append("office_owned")
    if not binding or not case or not draft:
        blocks.append("missing_current_packet")
    if displayed_binding and binding:
        for key in ("case_id", "draft_version", "to_addr", "body", "latest_inbound_message_id"):
            if displayed_binding.get(key) != binding.get(key):
                blocks.append("stale_displayed_context")
                break
    if latest_inbound_message_id and binding and latest_inbound_message_id != binding.get("latest_inbound_message_id"):
        blocks.append("inbound_changed")
    if binding and case and draft:
        blocks.extend(reject_reasons(binding, case=case, draft=draft))
    if blocks:
        return {
            "ok": False,
            "source": source,
            "execute_send": False,
            "intent": intent,
            "reason": "blocked_by_backend",
            "blocks": blocks,
        }
    return {
        "ok": True,
        "source": source,
        "execute_send": True,
        "intent": intent,
        "reason": "bound_current_packet",
        "bound": {
            "case_id": binding.get("case_id"),
            "draft_version": binding.get("draft_version"),
            "to_addr": binding.get("to_addr"),
            "mailbox": binding.get("mailbox"),
            "latest_inbound_message_id": binding.get("latest_inbound_message_id"),
        },
    }
