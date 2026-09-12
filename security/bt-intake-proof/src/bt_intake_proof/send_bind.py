"""Version-bound Phase E send actions. Approval is not a send."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .cases import APPROVAL_APPROVED, CaseLayer, _json, _loads
from .constants import (
    DESK_SEND_SUBJECT,
    MAILBOX,
    MARKER_DESK_SEND,
    OFFICE_OWNER_KEYS,
)
from .phasee_constants import (
    PHASEE_FROM,
    PHASEE_SEND_MARKER,
    PHASEE_SUBJECT,
    PHASEE_TIMING,
    PHASEE_TO,
    STATUS_QUEUED,
    STATUS_REJECTED,
)

from .store import utc_now

QUEUED_BY_PHASEE = "phasee"
QUEUED_BY_DESK = "desk_control"

LINK_RE = re.compile(r"https?://|www\.", re.I)
# Gmail thread ids are hex. Local synthetic case keys are not provider identity.
GMAIL_THREAD_ID_RE = re.compile(r"^[0-9a-fA-F]{10,32}$")


def provider_gmail_thread_id(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if GMAIL_THREAD_ID_RE.fullmatch(raw):
        return raw
    return None


def _table_names(layer: CaseLayer) -> set[str]:
    return {row[0] for row in layer.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def ensure_send_tables(layer: CaseLayer) -> None:
    names = _table_names(layer)
    if "case_send_actions" not in names:
        layer.conn.executescript(
            """
        CREATE TABLE IF NOT EXISTS case_send_actions (
            id INTEGER PRIMARY KEY,
            case_id TEXT NOT NULL,
            draft_version INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            mailbox TEXT NOT NULL,
            from_addr TEXT NOT NULL,
            to_addr TEXT NOT NULL,
            cc_json TEXT NOT NULL,
            bcc_json TEXT NOT NULL,
            thread_id TEXT,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            attachments_json TEXT NOT NULL,
            latest_inbound_message_id TEXT,
            payload_sha256 TEXT NOT NULL,
            send_timing TEXT NOT NULL,
            status TEXT NOT NULL,
            consumed INTEGER NOT NULL DEFAULT 0,
            locked_at TEXT,
            lock_owner TEXT,
            UNIQUE (case_id, draft_version)
        );
            """
        )
    cols = {row[1] for row in layer.conn.execute("PRAGMA table_info(case_send_actions)")}
    if "queued_by" not in cols:
        layer.conn.execute("ALTER TABLE case_send_actions ADD COLUMN queued_by TEXT")
    if "control_gmail_id" not in cols:
        layer.conn.execute("ALTER TABLE case_send_actions ADD COLUMN control_gmail_id TEXT")
    names = _table_names(layer)
    if "case_send_attempts" not in names:
        layer.conn.executescript(
            """
        CREATE TABLE IF NOT EXISTS case_send_attempts (
            id INTEGER PRIMARY KEY,
            action_id INTEGER NOT NULL,
            at TEXT NOT NULL,
            result TEXT NOT NULL,
            provider_message_id TEXT,
            detail TEXT
        );
            """
        )
    if "case_send_verifications" not in _table_names(layer):
        layer.conn.executescript(
            """
        CREATE TABLE IF NOT EXISTS case_send_verifications (
            id INTEGER PRIMARY KEY,
            action_id INTEGER NOT NULL,
            at TEXT NOT NULL,
            kind TEXT NOT NULL,
            result TEXT NOT NULL,
            provider_message_id TEXT,
            detail_json TEXT
        );
        """
    )


def canonical_payload(binding: dict[str, Any]) -> str:
    return json.dumps(
        {
            "case_id": binding["case_id"],
            "draft_version": int(binding["draft_version"]),
            "mailbox": binding["mailbox"],
            "from": binding["from_addr"],
            "to": binding["to_addr"],
            "cc": binding.get("cc") or [],
            "bcc": binding.get("bcc") or [],
            "thread_id": binding.get("thread_id") or "",
            "subject": binding["subject"],
            "body": binding["body"],
            "attachments": binding.get("attachments") or [],
            "latest_inbound_message_id": binding.get("latest_inbound_message_id") or "",
            "send_timing": binding.get("send_timing") or PHASEE_TIMING,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def payload_sha256(binding: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_payload(binding).encode("utf-8")).hexdigest()


def is_phasee_body(text: str | None) -> bool:
    return PHASEE_SEND_MARKER in str(text or "")


def is_desk_roundtrip_body(text: str | None) -> bool:
    return MARKER_DESK_SEND in str(text or "")


def is_authorized_internal_send_body(text: str | None) -> bool:
    return is_phasee_body(text) or is_desk_roundtrip_body(text)


def outbound_marker(text: str | None) -> str:
    if is_desk_roundtrip_body(text):
        return MARKER_DESK_SEND
    return PHASEE_SEND_MARKER


def phasee_binding_from_case(layer: CaseLayer, case_id: str) -> dict[str, Any] | None:
    case = layer.get_case(case_id)
    draft = layer.latest_draft(case_id)
    if not case or not draft:
        return None
    body = str(draft.get("proposed_response") or "")
    if not is_phasee_body(body):
        return None
    return {
        "case_id": case_id,
        "draft_version": int(draft["version"]),
        "mailbox": case.get("mailbox") or MAILBOX,
        "from_addr": PHASEE_FROM,
        "to_addr": PHASEE_TO,
        "cc": [],
        "bcc": [],
        "thread_id": case.get("thread_id") or "",
        "subject": PHASEE_SUBJECT,
        "body": body,
        "attachments": [],
        "latest_inbound_message_id": case.get("latest_inbound_message_id") or "",
        "send_timing": PHASEE_TIMING,
    }


def reject_reasons(binding: dict[str, Any], *, case: dict[str, Any] | None = None, draft: dict[str, Any] | None = None) -> list[str]:
    reasons = []
    if binding.get("from_addr") != PHASEE_FROM:
        reasons.append("from_not_contactus")
    if binding.get("to_addr") != PHASEE_TO:
        reasons.append("to_not_daniel")
    if binding.get("cc") or binding.get("bcc"):
        reasons.append("cc_or_bcc_present")
    if binding.get("attachments"):
        reasons.append("attachments_present")
    if LINK_RE.search(str(binding.get("body") or "")):
        reasons.append("links_present")
    desk = is_desk_roundtrip_body(binding.get("body"))
    phasee = is_phasee_body(binding.get("body"))
    if desk and not phasee:
        if binding.get("subject") != DESK_SEND_SUBJECT:
            reasons.append("subject_mismatch")
    elif not phasee:
        reasons.append("missing_phasee_marker")
        if binding.get("subject") != PHASEE_SUBJECT:
            reasons.append("subject_mismatch")
    elif binding.get("subject") != PHASEE_SUBJECT:
        reasons.append("subject_mismatch")
    if binding.get("mailbox") != MAILBOX:
        reasons.append("mailbox_mismatch")
    if case is not None:
        if case.get("approval_state") != APPROVAL_APPROVED:
            reasons.append("not_approved")
        if int(case.get("draft_version") or 0) != int(binding["draft_version"]):
            reasons.append("stale_draft_version")
        if (case.get("latest_inbound_message_id") or "") != (binding.get("latest_inbound_message_id") or ""):
            reasons.append("inbound_changed")
        if (case.get("thread_id") or "") != (binding.get("thread_id") or ""):
            reasons.append("thread_changed")
        if int(case.get("hold") or 0):
            reasons.append("hold")
        who = str(case.get("owner") or "").lower()
        if who in OFFICE_OWNER_KEYS:
            reasons.append("office_owned")
    if draft is not None and str(draft.get("proposed_response") or "") != str(binding.get("body") or ""):
        reasons.append("body_changed")
    return reasons


def queue_phasee_send(layer: CaseLayer, case_id: str) -> dict[str, Any]:
    ensure_send_tables(layer)
    case = layer.get_case(case_id)
    draft = layer.latest_draft(case_id)
    binding = phasee_binding_from_case(layer, case_id)
    if not binding:
        return {"ok": False, "reason": "not_phasee_draft"}
    reasons = reject_reasons(binding, case=case, draft=draft)
    if reasons:
        return {"ok": False, "reason": "rejected", "reasons": reasons}
    digest = payload_sha256(binding)
    existing = layer.conn.execute(
        "SELECT * FROM case_send_actions WHERE case_id = ? AND draft_version = ?",
        (case_id, binding["draft_version"]),
    ).fetchone()
    if existing:
        return {"ok": True, "skipped": True, "reason": "already_queued", "action": dict(existing)}
    now = utc_now()
    layer.conn.execute(
        """
        INSERT INTO case_send_actions (
            case_id, draft_version, created_at, mailbox, from_addr, to_addr, cc_json, bcc_json,
            thread_id, subject, body, attachments_json, latest_inbound_message_id,
            payload_sha256, send_timing, status, consumed, queued_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        """,
        (
            binding["case_id"],
            binding["draft_version"],
            now,
            binding["mailbox"],
            binding["from_addr"],
            binding["to_addr"],
            _json(binding["cc"]),
            _json(binding["bcc"]),
            binding["thread_id"],
            binding["subject"],
            binding["body"],
            _json(binding["attachments"]),
            binding["latest_inbound_message_id"],
            digest,
            binding["send_timing"],
            STATUS_QUEUED,
            QUEUED_BY_PHASEE,
        ),
    )
    layer.add_event(case_id, "phasee_send_queued", draft_version=binding["draft_version"], payload_sha256=digest)
    row = layer.conn.execute(
        "SELECT * FROM case_send_actions WHERE case_id = ? AND draft_version = ?",
        (case_id, binding["draft_version"]),
    ).fetchone()
    return {"ok": True, "action": dict(row), "queued_by": QUEUED_BY_PHASEE}


def desk_binding_from_case(layer: CaseLayer, case_id: str) -> dict[str, Any] | None:
    case = layer.get_case(case_id)
    draft = layer.latest_draft(case_id)
    if not case or not draft:
        return None
    body = str(draft.get("proposed_response") or "")
    if not is_desk_roundtrip_body(body):
        return None
    return {
        "case_id": case_id,
        "draft_version": int(draft["version"]),
        "mailbox": case.get("mailbox") or MAILBOX,
        "from_addr": PHASEE_FROM,
        "to_addr": PHASEE_TO,
        "cc": [],
        "bcc": [],
        "thread_id": case.get("thread_id") or "",
        "subject": DESK_SEND_SUBJECT,
        "body": body,
        "attachments": [],
        "latest_inbound_message_id": case.get("latest_inbound_message_id") or "",
        "send_timing": PHASEE_TIMING,
    }


def queue_desk_send(layer: CaseLayer, case_id: str, *, control_gmail_id: str | None = None) -> dict[str, Any]:
    """Queue only a desk-roundtrip send. Phase E leftovers are not executable here."""
    ensure_send_tables(layer)
    case = layer.get_case(case_id)
    draft = layer.latest_draft(case_id)
    binding = desk_binding_from_case(layer, case_id)
    if not binding:
        return {"ok": False, "reason": "not_desk_send_draft"}
    reasons = reject_reasons(binding, case=case, draft=draft)
    if reasons:
        return {"ok": False, "reason": "rejected", "reasons": reasons}
    digest = payload_sha256(binding)
    existing = layer.conn.execute(
        "SELECT * FROM case_send_actions WHERE case_id = ? AND draft_version = ?",
        (case_id, binding["draft_version"]),
    ).fetchone()
    if existing:
        row = dict(existing)
        if str(row.get("queued_by") or "") != QUEUED_BY_DESK:
            return {"ok": False, "reason": "phasee_leftover_not_executable", "action": row}
        return {"ok": True, "skipped": True, "reason": "already_queued", "action": row}
    now = utc_now()
    layer.conn.execute(
        """
        INSERT INTO case_send_actions (
            case_id, draft_version, created_at, mailbox, from_addr, to_addr, cc_json, bcc_json,
            thread_id, subject, body, attachments_json, latest_inbound_message_id,
            payload_sha256, send_timing, status, consumed, queued_by, control_gmail_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            binding["case_id"],
            binding["draft_version"],
            now,
            binding["mailbox"],
            binding["from_addr"],
            binding["to_addr"],
            _json(binding["cc"]),
            _json(binding["bcc"]),
            binding["thread_id"],
            binding["subject"],
            binding["body"],
            _json(binding["attachments"]),
            binding["latest_inbound_message_id"],
            digest,
            binding["send_timing"],
            STATUS_QUEUED,
            QUEUED_BY_DESK,
            control_gmail_id,
        ),
    )
    layer.add_event(
        case_id,
        "desk_send_queued",
        draft_version=binding["draft_version"],
        payload_sha256=digest,
        control_gmail_id=control_gmail_id,
    )
    row = layer.conn.execute(
        "SELECT * FROM case_send_actions WHERE case_id = ? AND draft_version = ?",
        (case_id, binding["draft_version"]),
    ).fetchone()
    return {"ok": True, "action": dict(row), "queued_by": QUEUED_BY_DESK}


def queue_approved_phasee_sends(layer: CaseLayer) -> list[dict[str, Any]]:
    ensure_send_tables(layer)
    rows = layer.conn.execute(
        "SELECT case_id FROM cases WHERE approval_state = ? AND stage = ?",
        (APPROVAL_APPROVED, "approved"),
    ).fetchall()
    return [queue_phasee_send(layer, row["case_id"]) for row in rows]


def action_row(layer: CaseLayer, action_id: int) -> dict[str, Any] | None:
    ensure_send_tables(layer)
    row = layer.conn.execute("SELECT * FROM case_send_actions WHERE id = ?", (action_id,)).fetchone()
    return dict(row) if row else None


def latest_action(layer: CaseLayer, case_id: str) -> dict[str, Any] | None:
    ensure_send_tables(layer)
    row = layer.conn.execute(
        "SELECT * FROM case_send_actions WHERE case_id = ? ORDER BY id DESC LIMIT 1",
        (case_id,),
    ).fetchone()
    return dict(row) if row else None


def binding_from_action(action: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": action["case_id"],
        "draft_version": int(action["draft_version"]),
        "mailbox": action["mailbox"],
        "from_addr": action["from_addr"],
        "to_addr": action["to_addr"],
        "cc": _loads(action.get("cc_json") or []),
        "bcc": _loads(action.get("bcc_json") or []),
        "thread_id": action.get("thread_id") or "",
        "subject": action["subject"],
        "body": action["body"],
        "attachments": _loads(action.get("attachments_json") or []),
        "latest_inbound_message_id": action.get("latest_inbound_message_id") or "",
        "send_timing": action.get("send_timing") or PHASEE_TIMING,
    }


def revalidate_action(layer: CaseLayer, action: dict[str, Any]) -> list[str]:
    case = layer.get_case(action["case_id"])
    draft = layer.get_draft(action["case_id"], int(action["draft_version"]))
    binding = binding_from_action(action)
    reasons = reject_reasons(binding, case=case, draft=draft)
    if payload_sha256(binding) != action.get("payload_sha256"):
        reasons.append("payload_hash_mismatch")
    if int(action.get("consumed") or 0):
        reasons.append("already_consumed")
    current = layer.latest_draft(action["case_id"])
    if current and int(current["version"]) != int(action["draft_version"]):
        reasons.append("superseded_draft")
    return reasons


def mark_action(layer: CaseLayer, action_id: int, **fields: Any) -> None:
    if not fields:
        return
    assignments = ", ".join(f"{key} = ?" for key in fields)
    layer.conn.execute(f"UPDATE case_send_actions SET {assignments} WHERE id = ?", (*fields.values(), action_id))


def record_attempt(layer: CaseLayer, action_id: int, result: str, provider_message_id: str | None = None, detail: str | None = None) -> None:
    layer.conn.execute(
        "INSERT INTO case_send_attempts (action_id, at, result, provider_message_id, detail) VALUES (?, ?, ?, ?, ?)",
        (action_id, utc_now(), result, provider_message_id, detail),
    )


def record_verification(layer: CaseLayer, action_id: int, kind: str, result: str, provider_message_id: str | None = None, detail: dict[str, Any] | None = None) -> None:
    layer.conn.execute(
        "INSERT INTO case_send_verifications (action_id, at, kind, result, provider_message_id, detail_json) VALUES (?, ?, ?, ?, ?, ?)",
        (action_id, utc_now(), kind, result, provider_message_id, _json(detail or {})),
    )
