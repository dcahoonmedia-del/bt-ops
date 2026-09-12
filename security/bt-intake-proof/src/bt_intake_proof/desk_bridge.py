"""Gmail control bridge: ChatGPT sends structured mail; the backend authorizes.

Daniel speaks to ChatGPT. ChatGPT chooses one existing desk intent and sends a
private control message from daniel@ to contactus@. This module parses that
mail, validates the packet binding, and calls submit_desk_action.

It does not interpret natural language.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from typing import Any

from .cases import (
    APPROVAL_APPROVED,
    DECISION_APPROVE,
    DECISION_NONE,
    CaseLayer,
)
from .constants import (
    ALLOWED_SENDER,
    CLASS_DESK_CONTROL,
    DESK_PACKET_MARKERS,
    DESK_SEND_BODY,
    MAILBOX,
    MARKER_DESK_BIND,
    MARKER_DESK_CTRL,
    MARKER_DESK_RESULT,
    MARKER_DESK_SEND,
)
from .desk_control import (
    INTENT_APPROVE_SEND,
    INTENT_HOLD,
    INTENT_NO_RESPONSE,
    INTENT_OFFICE,
    INTENT_REVISE,
    OFFICE_STAFF,
    SOURCE_CHATGPT,
    submit_desk_action,
)
from .desk_origin import authenticate_control_origin, unquoted_control_text
from .eligibility import normalize_email
from .phasee_constants import PHASEE_TO
from .send_bind import (
    desk_binding_from_case,
    ensure_send_tables,
    is_desk_roundtrip_body,
    is_phasee_body,
    queue_desk_send,
)
from .store import ReceiptStore, utc_now

MARKER_CTRL = MARKER_DESK_CTRL
MARKER_BIND = MARKER_DESK_BIND
MARKER_RESULT = MARKER_DESK_RESULT

BRIDGE_INTENTS = (
    INTENT_APPROVE_SEND,
    INTENT_REVISE,
    INTENT_HOLD,
    INTENT_OFFICE,
    INTENT_NO_RESPONSE,
)

_FIELD = re.compile(r"^(INTENT|OWNER|NOTE|CASE_ID|DRAFT_VERSION|NONCE|PACKET_HASH)=(.*)$", re.M)
_BIND_FIELD = re.compile(
    r"^(CASE_ID|DRAFT_VERSION|NONCE|PACKET_HASH|LATEST_INBOUND|TO_ADDR|BODY_HASH)=(.*)$",
    re.M,
)


def looks_like_control_mail(subject: str | None, body: str | None) -> bool:
    blob = f"{subject or ''}\n{body or ''}"
    return MARKER_CTRL in blob


def parse_control_mail(subject: str | None, body: str | None) -> dict[str, Any]:
    """Parse a ChatGPT control message. No speech interpretation."""
    blob = f"{subject or ''}\n{body or ''}"
    if MARKER_CTRL not in blob:
        return {"ok": False, "reason": "not_control_mail"}
    fields = {key: (value or "").strip() for key, value in _FIELD.findall(blob)}
    intent = fields.get("INTENT") or ""
    version_raw = fields.get("DRAFT_VERSION") or ""
    try:
        draft_version = int(version_raw) if version_raw else None
    except ValueError:
        draft_version = None
    owner = (fields.get("OWNER") or "").strip().lower() or None
    return {
        "ok": True,
        "intent": intent,
        "owner": owner,
        "note": fields.get("NOTE") or None,
        "case_id": fields.get("CASE_ID") or None,
        "draft_version": draft_version,
        "nonce": fields.get("NONCE") or None,
        "packet_hash": fields.get("PACKET_HASH") or None,
        "source": SOURCE_CHATGPT,
        "requires_case_id_from_daniel": False,
        "requires_magic_phrase": False,
    }


def format_control_mail(
    intent: str,
    binding: dict[str, Any],
    *,
    owner: str | None = None,
    note: str | None = None,
) -> dict[str, str]:
    """ChatGPT-compatible control mail. Daniel should never see this."""
    lines = [
        MARKER_CTRL,
        f"INTENT={intent}",
        f"OWNER={owner or ''}",
        f"NOTE={note or ''}",
        f"CASE_ID={binding.get('case_id') or ''}",
        f"DRAFT_VERSION={binding.get('draft_version') or ''}",
        f"NONCE={binding.get('nonce') or ''}",
        f"PACKET_HASH={binding.get('packet_hash') or ''}",
    ]
    return {
        "from": ALLOWED_SENDER,
        "to": MAILBOX,
        "cc": "",
        "subject": MARKER_CTRL,
        "body": "\n".join(lines) + "\n",
        "kind": "control",
        "marker": MARKER_CTRL,
    }


def parse_packet_binding(text: str | None) -> dict[str, Any] | None:
    blob = str(text or "")
    if MARKER_BIND not in blob:
        return None
    fields = {key: (value or "").strip() for key, value in _BIND_FIELD.findall(blob)}
    if not fields.get("CASE_ID") or not fields.get("PACKET_HASH"):
        return None
    try:
        version = int(fields["DRAFT_VERSION"]) if fields.get("DRAFT_VERSION") else None
    except ValueError:
        version = None
    return {
        "case_id": fields.get("CASE_ID"),
        "draft_version": version,
        "nonce": fields.get("NONCE") or None,
        "packet_hash": fields.get("PACKET_HASH"),
        "latest_inbound_message_id": fields.get("LATEST_INBOUND") or "",
        "to_addr": fields.get("TO_ADDR") or "",
        "body_hash": fields.get("BODY_HASH") or "",
    }


def exact_desk_send_draft() -> dict[str, Any]:
    return {
        "classification": "internal_desk_roundtrip_send_test",
        "known_facts": [
            "Internal B&T Lead Desk round-trip test only",
            "From contactus@ to daniel@ only",
            "No CC, BCC, attachments, or links",
        ],
        "missing_info": [],
        "recommended_next_step": "Daniel approves this exact version to authorize one bounded send",
        "proposed_response": DESK_SEND_BODY,
        "channel": "email",
        "judgment_needed": "Approve only if the exact body below is what should be sent once",
        "reasoning_summary": "Desk round-trip exact-approval send test. Not a customer promise.",
    }


def install_desk_send_draft(layer: CaseLayer, case_id: str, nonce: str) -> dict[str, Any]:
    return layer.save_draft(case_id, exact_desk_send_draft(), nonce, label_not_sent=False)


def body_sha256(text: str | None) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def compute_packet_binding(case: dict[str, Any], draft: dict[str, Any] | None) -> dict[str, Any]:
    """Exact current binding ChatGPT must copy from the newest packet."""
    draft = draft or {}
    body = str(draft.get("proposed_response") or "")
    to_addr = ""
    if is_phasee_body(body) or is_desk_roundtrip_body(body):
        to_addr = PHASEE_TO
    payload = {
        "case_id": case.get("case_id"),
        "draft_version": int(draft.get("version") or case.get("draft_version") or 0),
        "nonce": str(draft.get("nonce") or ""),
        "latest_inbound_message_id": str(case.get("latest_inbound_message_id") or ""),
        "to_addr": to_addr,
        "body_hash": body_sha256(body),
        "mailbox": case.get("mailbox") or MAILBOX,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    payload["packet_hash"] = digest
    return payload


def format_binding_block(binding: dict[str, Any]) -> str:
    return "\n".join(
        [
            "--- Machine binding (ChatGPT only; do not read this to Daniel) ---",
            MARKER_BIND,
            f"CASE_ID={binding.get('case_id') or ''}",
            f"DRAFT_VERSION={binding.get('draft_version') or ''}",
            f"NONCE={binding.get('nonce') or ''}",
            f"PACKET_HASH={binding.get('packet_hash') or ''}",
            f"LATEST_INBOUND={binding.get('latest_inbound_message_id') or ''}",
            f"TO_ADDR={binding.get('to_addr') or ''}",
            f"BODY_HASH={binding.get('body_hash') or ''}",
        ]
    )


def format_result_email(result: dict[str, Any]) -> dict[str, str]:
    human = str(result.get("human") or result.get("reason") or "The desk action finished.")
    lines = [
        "B&T Lead Desk result (internal). Tell Daniel this in plain language.",
        "Do not read machine fields to him.",
        "The ChatGPT iPhone app may show its own sent-mail confirmation; that is the app, not a hidden transport.",
        "",
        MARKER_RESULT,
        human,
        "",
        f"STATUS={'ok' if result.get('ok') else 'failed'}",
        f"INTENT={result.get('intent') or ''}",
        f"CASE={result.get('case_id') or ''}",
        f"DRAFT={result.get('draft_version') or ''}",
        f"REASON={result.get('reason') or ''}",
        f"CONTROL_ID={result.get('control_gmail_id') or ''}",
        f"NONCE={result.get('nonce') or ''}",
        f"EXECUTE_SEND={'yes' if result.get('execute_send') else 'no'}",
        f"SEND_QUEUED={'yes' if result.get('send_queued') else 'no'}",
        f"SEND_STATUS={result.get('send_status') or ''}",
        f"PROVIDER_ID={result.get('provider_message_id') or ''}",
    ]
    return {
        "from": MAILBOX,
        "to": ALLOWED_SENDER,
        "cc": "",
        "subject": f"{MARKER_RESULT} {result.get('intent') or 'action'} {result.get('case_id') or ''}".strip(),
        "body": "\n".join(lines) + "\n",
        "kind": "result",
        "marker": MARKER_RESULT,
    }


def looks_like_desk_transport(subject: str | None, body: str | None) -> bool:
    blob = f"{subject or ''}\n{body or ''}"
    return any(marker in blob for marker in DESK_PACKET_MARKERS) or MARKER_DESK_SEND in blob


def inspect_inbound(
    sender: str | None,
    subject: str | None,
    body: str | None,
    *,
    provider_evidence: dict[str, Any] | None = None,
    headers: Any = None,
) -> dict[str, Any]:
    """Classify an inbound before ordinary intake. Origin is fail-closed."""
    if not looks_like_control_mail(subject, body):
        return {"shaped": False, "kind": "not_control"}
    sender_n = normalize_email(sender)
    unquoted = unquoted_control_text(body)
    parsed = parse_control_mail(subject, unquoted)
    origin = authenticate_control_origin(headers, sender_n, provider_evidence)
    quoted_only = bool(
        MARKER_CTRL in str(body or "")
        and MARKER_CTRL not in unquoted
        and not re.search(r"^INTENT=", unquoted, re.M)
    )
    sender_ok = bool(origin.get("accepted"))
    reason = None
    if not sender_ok:
        reason = str(origin.get("reason") or "sender_not_verified_daniel")
    elif quoted_only or not parsed.get("ok") or not parsed.get("intent"):
        reason = "control_not_in_unquoted_text" if quoted_only or not parsed.get("intent") else None
        if quoted_only:
            sender_ok = False
    return {
        "shaped": True,
        "kind": CLASS_DESK_CONTROL,
        "sender_ok": sender_ok,
        "sender": sender_n,
        "origin": origin,
        "parsed": parsed if parsed.get("ok") and parsed.get("intent") else None,
        "reason": reason,
        "quoted_only": quoted_only,
        "eligible_for_intake": False,
        "eligible_for_codex": False,
        "becomes_case": False,
    }


def _table_names(layer: CaseLayer) -> set[str]:
    return {row[0] for row in layer.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def ensure_bridge_tables(layer: CaseLayer) -> None:
    names = _table_names(layer)
    if "desk_control_inbox" not in names or "desk_control_consumed" not in names or "desk_result_outbox" not in names:
        layer.conn.executescript(
            """
        CREATE TABLE IF NOT EXISTS desk_control_inbox (
            id INTEGER PRIMARY KEY,
            gmail_message_id TEXT UNIQUE,
            sender TEXT,
            parsed_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            processed INTEGER NOT NULL DEFAULT 0,
            result_json TEXT
        );

        CREATE TABLE IF NOT EXISTS desk_control_consumed (
            nonce TEXT NOT NULL,
            draft_version INTEGER NOT NULL,
            packet_hash TEXT NOT NULL,
            consumed_at TEXT NOT NULL,
            gmail_message_id TEXT,
            PRIMARY KEY (nonce, draft_version)
        );

        CREATE TABLE IF NOT EXISTS desk_result_outbox (
            id INTEGER PRIMARY KEY,
            control_gmail_id TEXT NOT NULL,
            nonce TEXT,
            kind TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT NOT NULL,
            provider_id TEXT,
            created_at TEXT NOT NULL,
            sent_at TEXT,
            UNIQUE (control_gmail_id, kind)
        );
        """
    )
    cols = {row[1] for row in layer.conn.execute("PRAGMA table_info(cases)")}
    if "owner" not in cols:
        layer.conn.execute("ALTER TABLE cases ADD COLUMN owner TEXT")
    if "hold" not in cols:
        layer.conn.execute("ALTER TABLE cases ADD COLUMN hold INTEGER NOT NULL DEFAULT 0")
    inbox_cols = {row[1] for row in layer.conn.execute("PRAGMA table_info(desk_control_inbox)")}
    if "origin_authenticated" not in inbox_cols:
        layer.conn.execute(
            "ALTER TABLE desk_control_inbox ADD COLUMN origin_authenticated INTEGER NOT NULL DEFAULT 0"
        )


def record_control_inbox(
    layer: CaseLayer,
    *,
    gmail_message_id: str,
    sender: str,
    parsed: dict[str, Any],
    origin_authenticated: bool = False,
) -> None:
    ensure_bridge_tables(layer)
    layer.conn.execute(
        """
        INSERT OR IGNORE INTO desk_control_inbox (
            gmail_message_id, sender, parsed_json, created_at, processed, origin_authenticated
        )
        VALUES (?, ?, ?, ?, 0, ?)
        """,
        (
            gmail_message_id,
            sender,
            json.dumps(parsed, sort_keys=True, default=str),
            utc_now(),
            1 if origin_authenticated else 0,
        ),
    )


def _mark_inbox(layer: CaseLayer, gmail_message_id: str | None, result: dict[str, Any]) -> None:
    if not gmail_message_id:
        return
    layer.conn.execute(
        "UPDATE desk_control_inbox SET processed = 1, result_json = ? WHERE gmail_message_id = ?",
        (json.dumps(result, sort_keys=True, default=str), gmail_message_id),
    )


def _fail(reason: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "ok": False,
        "execute_send": False,
        "send_queued": False,
        "reason": reason,
        "source": SOURCE_CHATGPT,
        "human": extra.pop("human", "I could not apply that desk action."),
    }
    payload.update(extra)
    return payload


def _human_success(intent: str, *, owner: str | None = None, version: int | None = None) -> str:
    if intent == INTENT_HOLD:
        return "I put this lead on hold. Nothing will send."
    if intent == INTENT_OFFICE:
        who = "Brenda" if owner == "brenda" else "Ally" if owner == "ally" else "the office"
        return f"This stays with {who}. I will not send a duplicate AI reply."
    if intent == INTENT_NO_RESPONSE:
        return "No customer reply is needed on this one."
    if intent == INTENT_REVISE:
        return f"I saved a new draft version{f' (v{version})' if version else ''}."
    if intent == INTENT_APPROVE_SEND:
        return (
            "That version is approved and queued for the bounded sender. "
            "Delivery is not proven until independent verify."
        )
    return "The desk action was recorded."


def validate_control_binding(
    parsed: dict[str, Any],
    *,
    case: dict[str, Any] | None,
    draft: dict[str, Any] | None,
    layer: CaseLayer,
) -> list[str]:
    ensure_bridge_tables(layer)
    blocks: list[str] = []
    if not case:
        return ["unknown_case"]
    if not draft:
        return ["draft_missing"]
    current = compute_packet_binding(case, draft)
    if not parsed.get("nonce") or parsed.get("nonce") != current.get("nonce"):
        blocks.append("nonce_invalid")
    if not parsed.get("packet_hash") or parsed.get("packet_hash") != current.get("packet_hash"):
        blocks.append("packet_hash_invalid")
    if parsed.get("case_id") != case.get("case_id"):
        blocks.append("case_mismatch")
    if int(parsed.get("draft_version") or 0) != int(current.get("draft_version") or 0):
        blocks.append("stale_draft_version")
    if (case.get("latest_inbound_message_id") or "") != (current.get("latest_inbound_message_id") or ""):
        blocks.append("inbound_changed")
    if body_sha256(str(draft.get("proposed_response") or "")) != current.get("body_hash"):
        blocks.append("draft_body_changed")
    consumed = layer.conn.execute(
        "SELECT 1 FROM desk_control_consumed WHERE nonce = ? AND draft_version = ?",
        (parsed.get("nonce") or "", int(parsed.get("draft_version") or 0)),
    ).fetchone()
    if consumed:
        blocks.append("nonce_consumed")
    return blocks


def consume_binding(layer: CaseLayer, parsed: dict[str, Any], *, gmail_message_id: str | None) -> None:
    """Insert the nonce. Raises IntegrityError if another worker already consumed it."""
    ensure_bridge_tables(layer)
    layer.conn.execute(
        """
        INSERT INTO desk_control_consumed (nonce, draft_version, packet_hash, consumed_at, gmail_message_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            parsed.get("nonce") or "",
            int(parsed.get("draft_version") or 0),
            parsed.get("packet_hash") or "",
            utc_now(),
            gmail_message_id,
        ),
    )


def _send_kwargs(layer: CaseLayer, case: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    binding = desk_binding_from_case(layer, case["case_id"])
    return {
        "binding": binding,
        "case": case,
        "draft": {"proposed_response": draft.get("proposed_response")},
        "hold": bool(case.get("hold")),
        "owner": case.get("owner"),
        "latest_inbound_message_id": case.get("latest_inbound_message_id"),
        "displayed_binding": binding,
    }


def apply_authorized_action(
    layer: CaseLayer,
    parsed: dict[str, Any],
    *,
    case: dict[str, Any],
    draft: dict[str, Any],
) -> dict[str, Any]:
    intent = parsed["intent"]
    owner = parsed.get("owner")
    note = parsed.get("note")
    case_id = case["case_id"]
    version = int(draft.get("version") or case.get("draft_version") or 0)

    if intent == INTENT_HOLD:
        layer.conn.execute(
            "UPDATE cases SET hold = 1, next_action = ?, updated_at = ? WHERE case_id = ?",
            ("hold", utc_now(), case_id),
        )
        layer.add_event(case_id, "desk_hold", actor=ALLOWED_SENDER, draft_version=version, note=note)
        return {"ok": True, "intent": intent, "case_id": case_id, "draft_version": version, "applied": "hold"}

    if intent == INTENT_OFFICE:
        if owner not in OFFICE_STAFF:
            return _fail("office_owner_required", intent=intent, case_id=case_id, human="Say whether this stays with Brenda or Ally.")
        layer.conn.execute(
            "UPDATE cases SET owner = ?, hold = 0, next_action = ?, updated_at = ? WHERE case_id = ?",
            (owner, "office_owned", utc_now(), case_id),
        )
        layer.add_event(case_id, "desk_office_owned", actor=ALLOWED_SENDER, owner=owner, draft_version=version)
        return {"ok": True, "intent": intent, "case_id": case_id, "draft_version": version, "owner": owner, "applied": "office_owned"}

    if intent == INTENT_NO_RESPONSE:
        applied = layer.apply_decision(
            case_id,
            DECISION_NONE,
            draft_version=version,
            actor=ALLOWED_SENDER,
            note=note,
        )
        if not applied.get("ok"):
            return _fail(str(applied.get("reason") or "no_response_failed"), intent=intent, case_id=case_id)
        return {**applied, "intent": intent, "applied": "no_response_needed"}

    if intent == INTENT_REVISE:
        new_body = (note or "").strip() or str(draft.get("proposed_response") or "")
        saved = layer.save_draft(
            case_id,
            {
                "classification": draft.get("classification"),
                "known_facts": [],
                "missing_info": [],
                "recommended_next_step": draft.get("recommended_next_step"),
                "proposed_response": new_body,
                "channel": draft.get("channel") or "email",
                "judgment_needed": note,
                "reasoning_summary": "ChatGPT revise_draft via Gmail control bridge",
            },
            nonce=f"desk-revise-{case_id}-v{version}",
            label_not_sent=not is_phasee_body(new_body),
        )
        layer.add_event(case_id, "desk_revise", actor=ALLOWED_SENDER, from_version=version, to_version=saved["version"])
        return {
            "ok": True,
            "intent": intent,
            "case_id": case_id,
            "draft_version": saved["version"],
            "previous_draft_version": version,
            "applied": "revise_draft",
        }

    if intent == INTENT_APPROVE_SEND:
        if is_phasee_body(draft.get("proposed_response")) and not is_desk_roundtrip_body(draft.get("proposed_response")):
            return _fail(
                "phasee_leftover_not_reusable",
                intent=intent,
                case_id=case_id,
                human="That Phase E packet is not this round-trip send. A new exact approval is required.",
            )
        if not is_desk_roundtrip_body(draft.get("proposed_response")):
            return _fail(
                "not_desk_send_draft",
                intent=intent,
                case_id=case_id,
                human="Send still requires the exact isolated internal round-trip packet.",
            )
        if case.get("approval_state") != APPROVAL_APPROVED:
            decided = layer.apply_decision(
                case_id,
                DECISION_APPROVE,
                draft_version=version,
                actor=ALLOWED_SENDER,
                note=note,
            )
            if not decided.get("ok"):
                return _fail(str(decided.get("reason") or "approve_failed"), intent=intent, case_id=case_id)
            case = layer.get_case(case_id) or case
        authorized = submit_desk_action(
            {"intent": intent, "owner": owner, "note": note, "source": SOURCE_CHATGPT},
            **_send_kwargs(layer, case, draft),
        )
        if not authorized.get("ok") or not authorized.get("execute_send"):
            return {
                **authorized,
                "ok": False,
                "execute_send": False,
                "send_queued": False,
                "human": "That send is blocked. The exact packet no longer matches.",
            }
        queued = queue_desk_send(layer, case_id, control_gmail_id=parsed.get("control_gmail_id"))
        return {
            **authorized,
            "ok": bool(queued.get("ok")),
            "send_queued": bool(queued.get("ok")),
            "queued": queued,
            "action_id": (queued.get("action") or {}).get("id"),
            "applied": "approve_and_send_current",
            "human": _human_success(intent),
        }

    return _fail("unknown_intent", intent=intent, case_id=case_id)


def _finish_control_result(
    layer: CaseLayer,
    result: dict[str, Any],
    *,
    gmail_message_id: str | None,
    nonce: str | None = None,
    enqueue: bool = True,
) -> dict[str, Any]:
    result["control_gmail_id"] = gmail_message_id
    result["nonce"] = nonce or result.get("nonce")
    result["result_email"] = format_result_email(result)
    if enqueue and gmail_message_id:
        enqueue_control_deliveries(layer, result)
    _mark_inbox(layer, gmail_message_id, {k: v for k, v in result.items() if k != "result_email"})
    return result


def process_control_mail(
    layer: CaseLayer,
    *,
    sender: str | None,
    subject: str | None,
    body: str | None,
    gmail_message_id: str | None = None,
    provider_evidence: dict[str, Any] | None = None,
    headers: Any = None,
    origin_already_authenticated: bool = False,
) -> dict[str, Any]:
    """Authorize one control message. Never interprets speech. Does not execute a send."""
    ensure_bridge_tables(layer)
    ensure_send_tables(layer)
    inspection = inspect_inbound(
        sender,
        subject,
        body,
        provider_evidence=provider_evidence,
        headers=headers,
    )
    if origin_already_authenticated and inspection.get("shaped"):
        inspection = {**inspection, "sender_ok": True, "reason": None}
    if not inspection.get("shaped"):
        result = _fail("not_control_mail")
        return _finish_control_result(layer, result, gmail_message_id=gmail_message_id, enqueue=False)
    if not inspection.get("sender_ok"):
        result = _fail(
            str(inspection.get("reason") or "sender_not_verified_daniel"),
            human="Only verified Daniel mail can control the desk.",
        )
        record_control_inbox(
            layer,
            gmail_message_id=gmail_message_id or f"imitation-{utc_now()}",
            sender=normalize_email(sender),
            parsed={"imitation": True, "reason": result["reason"]},
            origin_authenticated=False,
        )
        return _finish_control_result(layer, result, gmail_message_id=gmail_message_id)

    parsed = inspection.get("parsed") or parse_control_mail(subject, unquoted_control_text(body))
    if not parsed.get("ok") or not parsed.get("intent"):
        result = _fail(str(inspection.get("reason") or "unparsed_control_mail"))
        return _finish_control_result(layer, result, gmail_message_id=gmail_message_id)
    if parsed.get("intent") not in BRIDGE_INTENTS:
        result = _fail("unsupported_bridge_intent", intent=parsed.get("intent"))
        return _finish_control_result(layer, result, gmail_message_id=gmail_message_id, nonce=parsed.get("nonce"))

    if gmail_message_id:
        already = layer.conn.execute(
            "SELECT result_json, processed FROM desk_control_inbox WHERE gmail_message_id = ? AND processed = 1",
            (gmail_message_id,),
        ).fetchone()
        if already and already["result_json"]:
            cached = json.loads(already["result_json"])
            cached["result_email"] = format_result_email(cached)
            cached["replayed"] = True
            return cached
        record_control_inbox(
            layer,
            gmail_message_id=gmail_message_id,
            sender=ALLOWED_SENDER,
            parsed=parsed,
            origin_authenticated=True,
        )

    parsed = {**parsed, "control_gmail_id": gmail_message_id}

    def _binding_blocks(case_row: dict[str, Any] | None, draft_row: dict[str, Any] | None) -> list[str]:
        found = validate_control_binding(parsed, case=case_row, draft=draft_row, layer=layer)
        if case_row and parsed["intent"] == INTENT_APPROVE_SEND:
            if case_row.get("hold"):
                found.append("hold")
            if (case_row.get("owner") or "").lower() in OFFICE_STAFF:
                found.append("office_owned")
        return found

    case = layer.get_case(str(parsed.get("case_id") or ""))
    draft = layer.latest_draft(str(parsed.get("case_id") or "")) if case else None
    blocks = _binding_blocks(case, draft)
    if blocks:
        result = _fail(
            "blocked_by_backend",
            blocks=blocks,
            intent=parsed.get("intent"),
            case_id=parsed.get("case_id"),
            human="That action is stale or blocked. I did not change the case.",
        )
        return _finish_control_result(layer, result, gmail_message_id=gmail_message_id, nonce=parsed.get("nonce"))

    assert case is not None and draft is not None
    try:
        layer.conn.execute("BEGIN IMMEDIATE")
        case = layer.get_case(str(parsed.get("case_id") or ""))
        draft = layer.latest_draft(str(parsed.get("case_id") or "")) if case else None
        blocks = _binding_blocks(case, draft)
        if blocks or case is None or draft is None:
            layer.conn.execute("ROLLBACK")
            result = _fail(
                "blocked_by_backend",
                blocks=blocks or ["unknown_case"],
                intent=parsed.get("intent"),
                case_id=parsed.get("case_id"),
                human="That action is stale or blocked. I did not change the case.",
            )
            return _finish_control_result(layer, result, gmail_message_id=gmail_message_id, nonce=parsed.get("nonce"))
        try:
            consume_binding(layer, parsed, gmail_message_id=gmail_message_id)
        except sqlite3.IntegrityError:
            layer.conn.execute("ROLLBACK")
            result = _fail(
                "blocked_by_backend",
                blocks=["nonce_consumed"],
                intent=parsed.get("intent"),
                case_id=parsed.get("case_id"),
                human="That action is stale or blocked. I did not change the case.",
            )
            return _finish_control_result(layer, result, gmail_message_id=gmail_message_id, nonce=parsed.get("nonce"))
        applied = apply_authorized_action(layer, parsed, case=case, draft=draft)
        if not applied.get("ok"):
            layer.conn.execute("ROLLBACK")
            applied.setdefault("intent", parsed["intent"])
            applied.setdefault("case_id", parsed.get("case_id"))
            return _finish_control_result(layer, applied, gmail_message_id=gmail_message_id, nonce=parsed.get("nonce"))
        if layer.conn.in_transaction:
            layer.conn.execute("COMMIT")
    except sqlite3.OperationalError:
        try:
            if layer.conn.in_transaction:
                layer.conn.execute("ROLLBACK")
        except sqlite3.OperationalError:
            pass
        raise
    applied.setdefault("intent", parsed["intent"])
    applied.setdefault("case_id", case["case_id"])
    applied.setdefault("source", SOURCE_CHATGPT)
    applied.setdefault("execute_send", False)
    applied.setdefault("send_queued", False)
    applied["draft_version"] = applied.get("draft_version") or draft.get("version")
    applied.setdefault(
        "human",
        _human_success(
            parsed["intent"],
            owner=applied.get("owner") or parsed.get("owner"),
            version=applied.get("draft_version"),
        ),
    )
    return _finish_control_result(layer, applied, gmail_message_id=gmail_message_id, nonce=parsed.get("nonce"))


def process_control_receipt(store: ReceiptStore, receipt: dict[str, Any]) -> dict[str, Any]:
    layer = CaseLayer(store)
    return process_control_mail(
        layer,
        sender=receipt.get("sender"),
        subject=receipt.get("subject"),
        body=receipt.get("body_text"),
        gmail_message_id=receipt.get("gmail_message_id"),
        provider_evidence=receipt.get("_provider_evidence") or receipt.get("provider_evidence"),
        headers=receipt.get("_headers") or receipt.get("headers"),
    )


def process_pending_controls(store: ReceiptStore) -> list[dict[str, Any]]:
    layer = CaseLayer(store)
    ensure_bridge_tables(layer)
    rows = layer.conn.execute(
        "SELECT * FROM desk_control_inbox WHERE processed = 0 ORDER BY id"
    ).fetchall()
    results = []
    for row in rows:
        parsed = json.loads(row["parsed_json"])
        if parsed.get("imitation") or not int(row["origin_authenticated"] if "origin_authenticated" in row.keys() else 0):
            result = _fail(str(parsed.get("reason") or "sender_not_verified_daniel"))
            _finish_control_result(layer, result, gmail_message_id=row["gmail_message_id"])
            results.append(result)
            continue
        fake_body = format_control_mail(
            str(parsed.get("intent") or ""),
            {
                "case_id": parsed.get("case_id"),
                "draft_version": parsed.get("draft_version"),
                "nonce": parsed.get("nonce"),
                "packet_hash": parsed.get("packet_hash"),
            },
            owner=parsed.get("owner"),
            note=parsed.get("note"),
        )["body"]
        results.append(
            process_control_mail(
                layer,
                sender=row["sender"],
                subject=MARKER_CTRL,
                body=fake_body,
                gmail_message_id=row["gmail_message_id"],
                origin_already_authenticated=True,
            )
        )
    return results


def _fresh_case_email(layer: CaseLayer, case_id: str | None) -> dict[str, str] | None:
    if not case_id:
        return None
    from .desk_packets import format_case_email
    from .lead_desk import LeadDesk, db_fingerprint

    path = layer.store.path
    before = db_fingerprint(path)
    desk = LeadDesk(path)
    try:
        detail = desk.get_case(case_id, debug=True)
    except Exception:
        return None
    finally:
        desk.close()
    after = db_fingerprint(path)
    if before["sha256"] != after["sha256"]:
        return None
    return format_case_email(detail, generated_at=utc_now(), fingerprint=before["sha256"])


def enqueue_control_deliveries(layer: CaseLayer, result: dict[str, Any], *, kind_suffix: str = "") -> None:
    """Durable, duplicate-safe result + fresh case packet for success and reject."""
    ensure_bridge_tables(layer)
    control_id = str(result.get("control_gmail_id") or "")
    if not control_id:
        return
    nonce = result.get("nonce")
    now = utc_now()
    result_mail = result.get("result_email") or format_result_email(result)
    kind_result = f"result{kind_suffix}"
    kind_case = f"case{kind_suffix}"
    layer.conn.execute(
        """
        INSERT OR IGNORE INTO desk_result_outbox
            (control_gmail_id, nonce, kind, subject, body, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?)
        """,
        (control_id, nonce, kind_result, result_mail["subject"], result_mail["body"], now),
    )
    case_mail = _fresh_case_email(layer, result.get("case_id"))
    if case_mail:
        layer.conn.execute(
            """
            INSERT OR IGNORE INTO desk_result_outbox
                (control_gmail_id, nonce, kind, subject, body, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """,
            (control_id, nonce, kind_case, case_mail["subject"], case_mail["body"], now),
        )


def deliver_pending_desk_mail(layer: CaseLayer, transport: Any) -> list[dict[str, Any]]:
    """Send pending desk packets contactus → daniel. Duplicate-safe; unknown does not retry."""
    ensure_bridge_tables(layer)
    rows = layer.conn.execute(
        "SELECT * FROM desk_result_outbox WHERE status = 'pending' ORDER BY id"
    ).fetchall()
    out = []
    sender = getattr(transport, "send_internal_desk", None)
    if sender is None:
        return [{"ok": False, "reason": "desk_sender_missing"}]
    for row in rows:
        claimed = layer.conn.execute(
            "UPDATE desk_result_outbox SET status = 'sending' WHERE id = ? AND status = 'pending'",
            (row["id"],),
        )
        if claimed.rowcount != 1:
            continue
        result = sender(
            {
                "from_addr": MAILBOX,
                "to": ALLOWED_SENDER,
                "subject": row["subject"],
                "body": row["body"],
            }
        )
        if result.get("unknown"):
            layer.conn.execute(
                "UPDATE desk_result_outbox SET status = 'unknown', provider_id = ? WHERE id = ?",
                (result.get("provider_message_id"), row["id"]),
            )
            out.append({"ok": False, "unknown": True, "id": row["id"], "reason": result.get("reason")})
            continue
        if not result.get("ok"):
            layer.conn.execute(
                "UPDATE desk_result_outbox SET status = 'pending' WHERE id = ? AND status = 'sending'",
                (row["id"],),
            )
            if result.get("blocked"):
                layer.conn.execute(
                    "UPDATE desk_result_outbox SET status = 'blocked' WHERE id = ?",
                    (row["id"],),
                )
            out.append({"ok": False, "id": row["id"], "reason": result.get("reason"), "blocked": result.get("blocked")})
            continue
        layer.conn.execute(
            "UPDATE desk_result_outbox SET status = 'sent', provider_id = ?, sent_at = ? WHERE id = ?",
            (result.get("provider_message_id"), utc_now(), row["id"]),
        )
        out.append(
            {
                "ok": True,
                "id": row["id"],
                "kind": row["kind"],
                "control_gmail_id": row["control_gmail_id"],
                "provider_message_id": result.get("provider_message_id"),
            }
        )
    return out


def reconcile_sending_outbox(layer: CaseLayer, sent_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Unstick result delivery after crash between provider accept and local persist."""
    ensure_bridge_tables(layer)
    rows = layer.conn.execute("SELECT * FROM desk_result_outbox WHERE status = 'sending' ORDER BY id").fetchall()
    out = []
    for row in rows:
        matches = [
            item
            for item in sent_records
            if str(item.get("subject") or "") == row["subject"]
            and str(row["body"] or "")[:80] in str(item.get("body") or "")
        ]
        if len(matches) == 1:
            mid = matches[0].get("provider_message_id") or matches[0].get("id")
            layer.conn.execute(
                "UPDATE desk_result_outbox SET status = 'sent', provider_id = ?, sent_at = ? WHERE id = ?",
                (mid, utc_now(), row["id"]),
            )
            out.append({"ok": True, "recovered": True, "id": row["id"], "provider_message_id": mid})
        elif len(matches) > 1:
            layer.conn.execute(
                "UPDATE desk_result_outbox SET status = 'unknown' WHERE id = ?",
                (row["id"],),
            )
            out.append({"ok": False, "unknown": True, "retried": False, "id": row["id"]})
        else:
            layer.conn.execute(
                "UPDATE desk_result_outbox SET status = 'pending' WHERE id = ? AND status = 'sending'",
                (row["id"],),
            )
            out.append({"ok": True, "unlocked": True, "id": row["id"], "reason": "sending_reset_to_pending"})
    return out


def enqueue_send_followup(layer: CaseLayer, executed: dict[str, Any]) -> None:
    action_id = executed.get("action_id")
    if not action_id:
        return
    action = layer.conn.execute("SELECT * FROM case_send_actions WHERE id = ?", (action_id,)).fetchone()
    if not action:
        return
    control_id = action["control_gmail_id"]
    if not control_id:
        return
    payload = {
        "ok": bool(executed.get("ok")),
        "intent": INTENT_APPROVE_SEND,
        "case_id": action["case_id"],
        "draft_version": action["draft_version"],
        "control_gmail_id": control_id,
        "send_queued": True,
        "execute_send": True,
        "send_status": executed.get("status") or executed.get("reason"),
        "provider_message_id": executed.get("provider_message_id"),
        "reason": executed.get("reason"),
        "human": (
            "The bounded sender attempted that internal message. Independent verify is still required."
            if executed.get("ok")
            else "The bounded sender did not complete that send."
        ),
    }
    payload["result_email"] = format_result_email(payload)
    enqueue_control_deliveries(layer, payload, kind_suffix="_send")
