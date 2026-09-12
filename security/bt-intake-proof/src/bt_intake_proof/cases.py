"""Durable case layer on the proven SQLite receipt store. Does not replace receipts."""

from __future__ import annotations

import json
import re
from typing import Any

from .constants import CLASS_REPLY, MAILBOX
from .store import ReceiptStore, utc_now

STAGE_NEW = "new"
STAGE_NEEDS_DRAFT = "needs_draft"
STAGE_DRAFT_READY = "draft_ready"
STAGE_AWAITING_REVIEW = "awaiting_review"
STAGE_APPROVED = "approved"
STAGE_CHANGES_REQUESTED = "changes_requested"
STAGE_NO_RESPONSE = "no_response_needed"
STAGE_REOPENED = "reopened"

APPROVAL_NONE = "none"
APPROVAL_PENDING = "pending_review"
APPROVAL_APPROVED = "approved"
APPROVAL_CHANGES = "changes_requested"
APPROVAL_NONE_NEEDED = "no_response_needed"
APPROVAL_SUPERSEDED = "superseded"

DECISION_APPROVE = "approve"
DECISION_CHANGES = "request_changes"
DECISION_NONE = "no_response"

MARKER_CASEMGR = "BT-INTAKE-PROOF-CASEMGR-"
MARKER_APPROVE = "BT-INTAKE-PROOF-CASE-APPROVE-E9A8"
MARKER_CHANGES = "BT-INTAKE-PROOF-CASE-CHANGES-E9A8"
MARKER_NONE = "BT-INTAKE-PROOF-CASE-NONE-E9A8"
MARKER_REVIEW = "BT-INTAKE-PROOF-CASE-REVIEW-E9A8"

_CASE_REF = re.compile(r"CASE=([A-Za-z0-9._-]+)")
_DRAFT_REF = re.compile(r"DRAFT=(\d+)")


DRAFT_NOT_SENT = "DRAFT - NOT SENT"
_DRAFT_PREFIXES = (DRAFT_NOT_SENT, "DRAFT — NOT SENT", "DRAFT -- NOT SENT")


def _label_draft_not_sent(proposed: str) -> str:
    text = (proposed or "").strip()
    for prefix in _DRAFT_PREFIXES:
        if text.startswith(prefix):
            return DRAFT_NOT_SENT + text[len(prefix) :]
    return f"{DRAFT_NOT_SENT}\n\n{text}" if text else DRAFT_NOT_SENT


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _loads(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def case_id_for(mailbox: str, thread_id: str) -> str:
    thread = (thread_id or "unknown").replace("/", "")
    box = (mailbox or MAILBOX).split("@", 1)[0]
    return f"BTC-{box}-{thread}"


def marker_kind(marker: str | None) -> str:
    text = str(marker or "")
    if MARKER_REVIEW in text:
        return "review_packet"
    if MARKER_APPROVE in text:
        return "decision_approve"
    if MARKER_CHANGES in text:
        return "decision_changes"
    if MARKER_NONE in text:
        return "decision_none"
    if text.startswith(MARKER_CASEMGR):
        return "lead"
    return "other"


def parse_decision(subject: str | None, body: str | None) -> dict[str, Any] | None:
    blob = f"{subject or ''}\n{body or ''}"
    kind = marker_kind(blob)
    decision = {
        "decision_approve": DECISION_APPROVE,
        "decision_changes": DECISION_CHANGES,
        "decision_none": DECISION_NONE,
    }.get(kind)
    if not decision:
        return None
    case_match = _CASE_REF.search(blob)
    draft_match = _DRAFT_REF.search(blob)
    return {
        "decision": decision,
        "case_id": case_match.group(1) if case_match else None,
        "draft_version": int(draft_match.group(1)) if draft_match else None,
        "note": None,
    }


class CaseLayer:
    """Cases, drafts, decisions, and audit events in the same SQLite file as receipts."""

    def __init__(self, store: ReceiptStore) -> None:
        self.store = store
        self.conn = store.conn
        self._create()

    def _create(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS cases (
                case_id TEXT PRIMARY KEY,
                mailbox TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                sender TEXT,
                contact_json TEXT,
                opened_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                stage TEXT NOT NULL,
                inbound_class TEXT,
                latest_inbound_message_id TEXT,
                latest_inbound_at TEXT,
                latest_receipt_pk INTEGER,
                draft_version INTEGER NOT NULL DEFAULT 0,
                approval_state TEXT NOT NULL DEFAULT 'none',
                approved_draft_version INTEGER,
                next_action TEXT,
                UNIQUE (mailbox, thread_id)
            );

            CREATE TABLE IF NOT EXISTS case_events (
                id INTEGER PRIMARY KEY,
                case_id TEXT NOT NULL,
                at TEXT NOT NULL,
                actor TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT
            );

            CREATE TABLE IF NOT EXISTS case_drafts (
                case_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                classification TEXT,
                known_facts_json TEXT,
                missing_info_json TEXT,
                recommended_next_step TEXT,
                proposed_response TEXT,
                channel TEXT,
                judgment_needed TEXT,
                reasoning_summary TEXT,
                labeled_not_sent INTEGER NOT NULL,
                nonce TEXT,
                PRIMARY KEY (case_id, version)
            );

            CREATE TABLE IF NOT EXISTS case_decisions (
                id INTEGER PRIMARY KEY,
                case_id TEXT NOT NULL,
                draft_version INTEGER NOT NULL,
                decision TEXT NOT NULL,
                actor TEXT NOT NULL,
                at TEXT NOT NULL,
                note TEXT,
                gmail_message_id TEXT,
                send_triggered INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS case_fieldwork (
                id INTEGER PRIMARY KEY,
                case_id TEXT NOT NULL,
                inbound_message_id TEXT,
                retrieved_at TEXT NOT NULL,
                match_status TEXT NOT NULL,
                confidence TEXT,
                customer_id TEXT,
                location_id TEXT,
                identifiers_json TEXT,
                active_agreement_json TEXT,
                upcoming_work_orders_json TEXT,
                last_service_json TEXT,
                evidence_json TEXT NOT NULL,
                write_attempted INTEGER NOT NULL DEFAULT 0
            );
            """
        )

    def add_event(self, case_id: str, event_type: str, actor: str = "system", **payload: Any) -> None:
        self.conn.execute(
            "INSERT INTO case_events (case_id, at, actor, event_type, payload_json) VALUES (?, ?, ?, ?, ?)",
            (case_id, utc_now(), actor, event_type, _json(payload)),
        )

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        return dict(row) if row else None

    def get_case_by_thread(self, mailbox: str, thread_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM cases WHERE mailbox = ? AND thread_id = ?",
            (mailbox, thread_id),
        ).fetchone()
        return dict(row) if row else None

    def list_events(self, case_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM case_events WHERE case_id = ? ORDER BY id",
            (case_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_draft(self, case_id: str, version: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM case_drafts WHERE case_id = ? AND version = ?",
            (case_id, version),
        ).fetchone()
        return dict(row) if row else None

    def latest_draft(self, case_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM case_drafts WHERE case_id = ? ORDER BY version DESC LIMIT 1",
            (case_id,),
        ).fetchone()
        return dict(row) if row else None

    def decisions(self, case_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM case_decisions WHERE case_id = ? ORDER BY id",
            (case_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _inbound_already_applied(self, case_id: str, message_id: str) -> bool:
        if not message_id:
            return False
        rows = self.conn.execute(
            """
            SELECT payload_json FROM case_events
            WHERE case_id = ? AND event_type IN ('case_opened', 'inbound_reopened')
            """,
            (case_id,),
        ).fetchall()
        for row in rows:
            payload = _loads(row["payload_json"] if "payload_json" in row.keys() else row[0])
            if isinstance(payload, dict) and payload.get("gmail_message_id") == message_id:
                return True
        return False

    def upsert_from_receipt(self, receipt: dict[str, Any]) -> dict[str, Any]:
        """Create or reopen one case per mailbox+thread. Never a silent finished duplicate."""
        mailbox = receipt.get("mailbox") or MAILBOX
        thread_id = str(receipt.get("thread_id") or "")
        message_id = str(receipt.get("gmail_message_id") or "")
        marker = str(receipt.get("test_marker") or "")
        kind = marker_kind(marker)
        if kind != "lead" or not receipt.get("eligible"):
            return {"skipped": True, "reason": kind}
        case_id = case_id_for(mailbox, thread_id)
        existing = self.get_case(case_id)
        if existing and self._inbound_already_applied(case_id, message_id):
            return {"skipped": True, "reason": "already_applied", "case_id": case_id}
        now = utc_now()
        inbound_class = "reply" if receipt.get("classification") == CLASS_REPLY or existing else "new_lead"
        contact = {
            "sender": receipt.get("sender"),
            "recipients": _loads(receipt.get("recipients_json") or receipt.get("recipients") or []),
            "subject": receipt.get("subject"),
        }
        if existing:
            if existing.get("latest_inbound_message_id") == message_id:
                return {"skipped": True, "reason": "already_applied", "case_id": case_id}
            superseded = existing.get("approval_state") in {
                APPROVAL_APPROVED,
                APPROVAL_PENDING,
                APPROVAL_CHANGES,
                APPROVAL_NONE_NEEDED,
            }
            self.conn.execute(
                """
                UPDATE cases SET
                    sender = ?, contact_json = ?, updated_at = ?, stage = ?, inbound_class = ?,
                    latest_inbound_message_id = ?, latest_inbound_at = ?, latest_receipt_pk = ?,
                    approval_state = ?, approved_draft_version = NULL, next_action = ?
                WHERE case_id = ?
                """,
                (
                    receipt.get("sender"),
                    _json(contact),
                    now,
                    STAGE_REOPENED if existing else STAGE_NEEDS_DRAFT,
                    inbound_class,
                    message_id,
                    receipt.get("gmail_received_at") or now,
                    receipt.get("id"),
                    APPROVAL_SUPERSEDED if superseded else APPROVAL_NONE,
                    "draft_new_version",
                    case_id,
                ),
            )
            if existing.get("draft_version"):
                self.conn.execute(
                    "UPDATE case_drafts SET status = ? WHERE case_id = ? AND status != ?",
                    ("superseded", case_id, "superseded"),
                )
            self.add_event(
                case_id,
                "inbound_reopened",
                gmail_message_id=message_id,
                previous_approval=existing.get("approval_state"),
                previous_draft_version=existing.get("draft_version"),
                approval_superseded=superseded,
            )
            return {"case_id": case_id, "created": False, "reopened": True, "approval_superseded": superseded}

        self.conn.execute(
            """
            INSERT INTO cases (
                case_id, mailbox, thread_id, sender, contact_json, opened_at, updated_at,
                stage, inbound_class, latest_inbound_message_id, latest_inbound_at,
                latest_receipt_pk, draft_version, approval_state, approved_draft_version, next_action
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, NULL, ?)
            """,
            (
                case_id,
                mailbox,
                thread_id,
                receipt.get("sender"),
                _json(contact),
                now,
                now,
                STAGE_NEEDS_DRAFT,
                inbound_class,
                message_id,
                receipt.get("gmail_received_at") or now,
                receipt.get("id"),
                APPROVAL_NONE,
                "draft_initial",
            ),
        )
        self.add_event(case_id, "case_opened", gmail_message_id=message_id, inbound_class=inbound_class)
        return {"case_id": case_id, "created": True, "reopened": False, "approval_superseded": False}

    def save_draft(
        self,
        case_id: str,
        draft: dict[str, Any],
        nonce: str,
        *,
        label_not_sent: bool = True,
    ) -> dict[str, Any]:
        case = self.get_case(case_id)
        if not case:
            raise ValueError(f"unknown case {case_id}")
        version = int(case.get("draft_version") or 0) + 1
        raw_proposed = str(draft.get("proposed_response") or "").strip()
        # Phase C customer drafts stay labeled. Phase E stores the exact send body.
        proposed = _label_draft_not_sent(raw_proposed) if label_not_sent else raw_proposed
        labeled = 1 if label_not_sent else 0
        now = utc_now()
        self.conn.execute(
            "UPDATE case_drafts SET status = ? WHERE case_id = ? AND status = ?",
            ("superseded", case_id, "active"),
        )
        self.conn.execute(
            """
            INSERT INTO case_drafts (
                case_id, version, created_at, status, classification, known_facts_json,
                missing_info_json, recommended_next_step, proposed_response, channel,
                judgment_needed, reasoning_summary, labeled_not_sent, nonce
            ) VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                version,
                now,
                draft.get("classification"),
                _json(draft.get("known_facts") or []),
                _json(draft.get("missing_info") or []),
                draft.get("recommended_next_step"),
                proposed,
                draft.get("channel") or "email",
                draft.get("judgment_needed"),
                draft.get("reasoning_summary"),
                labeled,
                nonce,
            ),
        )
        self.conn.execute(
            """
            UPDATE cases SET draft_version = ?, stage = ?, approval_state = ?,
                approved_draft_version = NULL, next_action = ?, updated_at = ?
            WHERE case_id = ?
            """,
            (version, STAGE_AWAITING_REVIEW, APPROVAL_PENDING, "daniel_review", now, case_id),
        )
        self.add_event(case_id, "draft_created", version=version, nonce=nonce)
        return {"case_id": case_id, "version": version, "proposed_response": proposed}

    def apply_decision(
        self,
        case_id: str,
        decision: str,
        *,
        draft_version: int | None,
        actor: str,
        gmail_message_id: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        case = self.get_case(case_id)
        if not case:
            return {"ok": False, "reason": "unknown_case"}
        if gmail_message_id:
            already = self.conn.execute(
                "SELECT id FROM case_decisions WHERE gmail_message_id = ?",
                (gmail_message_id,),
            ).fetchone()
            if already:
                return {
                    "ok": True,
                    "skipped": True,
                    "reason": "already_recorded",
                    "case_id": case_id,
                    "decision": decision,
                    "send_triggered": False,
                }
        version = int(draft_version or case.get("draft_version") or 0)
        if version != int(case.get("draft_version") or 0):
            return {
                "ok": False,
                "reason": "stale_draft_version",
                "requested": version,
                "current": case.get("draft_version"),
            }
        if case.get("approval_state") == APPROVAL_SUPERSEDED:
            return {"ok": False, "reason": "approval_superseded"}
        if decision == DECISION_APPROVE and int(case.get("draft_version") or 0) != version:
            return {"ok": False, "reason": "cannot_approve_old_draft"}
        now = utc_now()
        stage = {
            DECISION_APPROVE: STAGE_APPROVED,
            DECISION_CHANGES: STAGE_CHANGES_REQUESTED,
            DECISION_NONE: STAGE_NO_RESPONSE,
        }[decision]
        approval = {
            DECISION_APPROVE: APPROVAL_APPROVED,
            DECISION_CHANGES: APPROVAL_CHANGES,
            DECISION_NONE: APPROVAL_NONE_NEEDED,
        }[decision]
        draft_status = {
            DECISION_APPROVE: "approved",
            DECISION_CHANGES: "changes_requested",
            DECISION_NONE: "no_response",
        }[decision]
        self.conn.execute(
            """
            INSERT INTO case_decisions (
                case_id, draft_version, decision, actor, at, note, gmail_message_id, send_triggered
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (case_id, version, decision, actor, now, note, gmail_message_id),
        )
        self.conn.execute(
            "UPDATE case_drafts SET status = ? WHERE case_id = ? AND version = ?",
            (draft_status, case_id, version),
        )
        self.conn.execute(
            """
            UPDATE cases SET stage = ?, approval_state = ?, approved_draft_version = ?,
                next_action = ?, updated_at = ?
            WHERE case_id = ?
            """,
            (
                stage,
                approval,
                version if decision == DECISION_APPROVE else None,
                "none_do_not_send",
                now,
                case_id,
            ),
        )
        self.add_event(
            case_id,
            "decision_recorded",
            actor=actor,
            decision=decision,
            draft_version=version,
            send_triggered=False,
        )
        return {"ok": True, "case_id": case_id, "decision": decision, "draft_version": version, "send_triggered": False}

    def sync_eligible_receipts(self, mailbox: str = MAILBOX) -> list[dict[str, Any]]:
        results = []
        for receipt in self.store.eligible_receipts(mailbox):
            marker = str(receipt.get("test_marker") or "")
            kind = marker_kind(marker)
            if kind.startswith("decision_"):
                parsed = parse_decision(receipt.get("subject"), receipt.get("body_text"))
                if not parsed or not parsed.get("case_id"):
                    results.append({"skipped": True, "reason": "decision_missing_case_ref", "gmail_message_id": receipt.get("gmail_message_id")})
                    continue
                applied = self.apply_decision(
                    parsed["case_id"],
                    parsed["decision"],
                    draft_version=parsed.get("draft_version"),
                    actor=receipt.get("sender") or "daniel@btpestcontrol.com",
                    gmail_message_id=receipt.get("gmail_message_id"),
                    note=parsed.get("note"),
                )
                results.append(applied)
                continue
            if kind == "review_packet":
                results.append({"skipped": True, "reason": "review_packet"})
                continue
            results.append(self.upsert_from_receipt(receipt))
        return results

    def cases_needing_draft(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM cases
            WHERE stage IN (?, ?) AND approval_state IN (?, ?)
            ORDER BY opened_at
            """,
            (STAGE_NEEDS_DRAFT, STAGE_REOPENED, APPROVAL_NONE, APPROVAL_SUPERSEDED),
        ).fetchall()
        return [dict(row) for row in rows]

    def save_fieldwork(self, case_id: str, evidence: dict[str, Any], inbound_message_id: str | None) -> dict[str, Any]:
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO case_fieldwork (
                case_id, inbound_message_id, retrieved_at, match_status, confidence,
                customer_id, location_id, identifiers_json, active_agreement_json,
                upcoming_work_orders_json, last_service_json, evidence_json, write_attempted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                case_id,
                inbound_message_id,
                evidence.get("retrieved_at") or now,
                evidence.get("status"),
                evidence.get("confidence"),
                evidence.get("customer_id"),
                evidence.get("location_id"),
                _json(evidence.get("identifiers") or {}),
                _json(evidence.get("active_agreement")),
                _json(evidence.get("upcoming_work_orders") or []),
                _json(evidence.get("last_service")),
                _json(evidence),
            ),
        )
        self.add_event(
            case_id,
            "fieldwork_matched",
            status=evidence.get("status"),
            customer_id=evidence.get("customer_id"),
            location_id=evidence.get("location_id"),
            write_attempted=False,
        )
        return {"ok": True, "write_attempted": False}

    def latest_fieldwork(self, case_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM case_fieldwork WHERE case_id = ? ORDER BY id DESC LIMIT 1",
            (case_id,),
        ).fetchone()
        return dict(row) if row else None

    def review_packet(self, case_id: str) -> dict[str, Any]:
        case = self.get_case(case_id)
        if not case:
            raise ValueError(f"unknown case {case_id}")
        draft = self.latest_draft(case_id)
        receipt = None
        if case.get("latest_inbound_message_id"):
            receipt = self.store.get_receipt(case["mailbox"], case["latest_inbound_message_id"])
        return {
            "case": case,
            "draft": draft,
            "inbound": {
                "gmail_message_id": (receipt or {}).get("gmail_message_id"),
                "thread_id": (receipt or {}).get("thread_id"),
                "sender": (receipt or {}).get("sender"),
                "subject": (receipt or {}).get("subject"),
                "gmail_received_at": (receipt or {}).get("gmail_received_at"),
                "body_text": (receipt or {}).get("body_text"),
                "classification": (receipt or {}).get("classification"),
            },
            "events": self.list_events(case_id),
            "decisions": self.decisions(case_id),
            "fieldwork": self.latest_fieldwork(case_id),
            "send_triggered": False,
        }
