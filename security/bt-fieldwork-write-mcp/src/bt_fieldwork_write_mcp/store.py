"""Durable proposals, operator approvals, audit, and no-retry guards."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .allowlist import GATE_AMBIGUOUS, GATE_DUPLICATE
from .errors import GateError


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class WriteStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init()
        self.sweep_in_flight_to_ambiguous()

    def _init(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS proposals (
              proposal_id TEXT PRIMARY KEY,
              operation TEXT NOT NULL,
              identity_sub TEXT NOT NULL,
              identity_email TEXT NOT NULL,
              subject_key TEXT NOT NULL,
              before_json TEXT NOT NULL,
              after_json TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              digest TEXT NOT NULL,
              created_at TEXT NOT NULL,
              expires_at TEXT NOT NULL,
              status TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS approvals (
              fingerprint TEXT PRIMARY KEY,
              proposal_id TEXT NOT NULL,
              digest TEXT NOT NULL,
              created_at TEXT NOT NULL,
              expires_at TEXT NOT NULL,
              used_at TEXT
            );
            CREATE TABLE IF NOT EXISTS subject_guards (
              subject_key TEXT PRIMARY KEY,
              proposal_id TEXT NOT NULL,
              state TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS attempts (
              attempt_id TEXT PRIMARY KEY,
              proposal_id TEXT NOT NULL,
              subject_key TEXT NOT NULL,
              started_at TEXT NOT NULL,
              outcome TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              at TEXT NOT NULL,
              event TEXT NOT NULL,
              proposal_id TEXT,
              detail_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS creation_journal (
              step_id TEXT PRIMARY KEY,
              proposal_id TEXT NOT NULL,
              step TEXT NOT NULL,
              intent_json TEXT NOT NULL,
              result_json TEXT,
              customer_id TEXT,
              contact_id TEXT,
              location_id TEXT,
              outcome TEXT NOT NULL,
              at TEXT NOT NULL
            );
            """
        )

    def close(self) -> None:
        self._conn.close()

    def audit(self, event: str, proposal_id: str | None, detail: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO audit(at, event, proposal_id, detail_json) VALUES (?,?,?,?)",
                (_now(), event, proposal_id, _json(detail)),
            )

    def sweep_in_flight_to_ambiguous(self) -> int:
        """Restarts after a write was sent: leftover in_flight is not retryable."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                rows = list(
                    self._conn.execute(
                        "SELECT proposal_id, subject_key FROM attempts WHERE outcome = 'in_flight'"
                    )
                )
                for row in rows:
                    self._conn.execute(
                        "UPDATE attempts SET outcome = 'ambiguous' WHERE proposal_id = ? AND outcome = 'in_flight'",
                        (row["proposal_id"],),
                    )
                    self._conn.execute(
                        "UPDATE proposals SET status = 'ambiguous' WHERE proposal_id = ?",
                        (row["proposal_id"],),
                    )
                    self._conn.execute(
                        "UPDATE subject_guards SET state = 'ambiguous', updated_at = ? WHERE subject_key = ?",
                        (_now(), row["subject_key"]),
                    )
                    self._conn.execute(
                        "INSERT INTO audit(at, event, proposal_id, detail_json) VALUES (?,?,?,?)",
                        (_now(), "ambiguous_after_restart", row["proposal_id"], _json({"gate": GATE_AMBIGUOUS})),
                    )
                journal = list(self._conn.execute("SELECT proposal_id, step FROM creation_journal WHERE outcome = 'intended'"))
                for row in journal:
                    self._conn.execute(
                        "UPDATE creation_journal SET outcome = 'ambiguous', result_json = ? WHERE proposal_id = ? AND step = ? AND outcome = 'intended'",
                        (_json({"gate": GATE_AMBIGUOUS, "crash": True}), row["proposal_id"], row["step"]),
                    )
                    self._conn.execute("UPDATE proposals SET status = 'ambiguous' WHERE proposal_id = ?", (row["proposal_id"],))
                    self._conn.execute(
                        "INSERT INTO audit(at, event, proposal_id, detail_json) VALUES (?,?,?,?)",
                        (_now(), "creation_step_ambiguous_after_restart", row["proposal_id"], _json({"step": row["step"]})),
                    )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return len(rows) + len(journal)

    def create_proposal(self, record: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._expire_unlocked(record["created_at"])
                guard = self._conn.execute(
                    "SELECT proposal_id, state FROM subject_guards WHERE subject_key = ?",
                    (record["subject_key"],),
                ).fetchone()
                if guard is not None:
                    if guard["state"] == "ambiguous":
                        raise GateError(GATE_AMBIGUOUS, proposal_id=guard["proposal_id"])
                    raise GateError(GATE_DUPLICATE, proposal_id=guard["proposal_id"])
                self._conn.execute(
                    """INSERT INTO proposals(
                        proposal_id, operation, identity_sub, identity_email, subject_key,
                        before_json, after_json, payload_json, digest, created_at, expires_at, status
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        record["proposal_id"],
                        record["operation"],
                        record["identity_sub"],
                        record["identity_email"],
                        record["subject_key"],
                        _json(record["before"]),
                        _json(record["after"]),
                        _json(record["payload"]),
                        record["digest"],
                        record["created_at"],
                        record["expires_at"],
                        "proposed",
                    ),
                )
                self._conn.execute(
                    "INSERT INTO subject_guards(subject_key, proposal_id, state, updated_at) VALUES (?,?,?,?)",
                    (record["subject_key"], record["proposal_id"], "open", record["created_at"]),
                )
                self._conn.execute(
                    "INSERT INTO audit(at, event, proposal_id, detail_json) VALUES (?,?,?,?)",
                    (record["created_at"], "proposed", record["proposal_id"], _json({"digest": record["digest"]})),
                )
                self._conn.execute("COMMIT")
            except GateError:
                self._conn.execute("ROLLBACK")
                raise
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def _expire_unlocked(self, now: str) -> None:
        rows = list(
            self._conn.execute(
                """SELECT p.proposal_id, p.subject_key FROM proposals p
                   JOIN subject_guards g ON g.proposal_id = p.proposal_id
                   WHERE p.status IN ('proposed','approved') AND p.expires_at <= ? AND g.state = 'open'""",
                (now,),
            )
        )
        for row in rows:
            self._conn.execute("UPDATE proposals SET status = 'expired' WHERE proposal_id = ?", (row["proposal_id"],))
            self._conn.execute("DELETE FROM subject_guards WHERE proposal_id = ? AND state = 'open'", (row["proposal_id"],))

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()
        if row is None:
            return None
        return {
            "proposal_id": row["proposal_id"],
            "operation": row["operation"],
            "identity": {"sub": row["identity_sub"], "email": row["identity_email"]},
            "subject_key": row["subject_key"],
            "before": json.loads(row["before_json"]),
            "after": json.loads(row["after_json"]),
            "payload": json.loads(row["payload_json"]),
            "digest": row["digest"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "status": row["status"],
        }

    def append_audit(self, proposal_id: str, event: str, detail: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO audit(at, event, proposal_id, detail_json) VALUES (?,?,?,?)",
                (_now(), event, proposal_id, _json(detail)),
            )

    def release_ambiguous_guard(self, subject_key: str, proposal_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM subject_guards WHERE subject_key = ? AND proposal_id = ? AND state = 'ambiguous'",
                (subject_key, proposal_id),
            )

    def set_status(self, proposal_id: str, status: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE proposals SET status = ? WHERE proposal_id = ?", (status, proposal_id))

    def release_open_guard(self, subject_key: str, proposal_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM subject_guards WHERE subject_key = ? AND proposal_id = ? AND state = 'open'",
                (subject_key, proposal_id),
            )

    def record_approval(self, fingerprint: str, proposal_id: str, digest: str, created_at: str, expires_at: str) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO approvals(fingerprint, proposal_id, digest, created_at, expires_at, used_at)
                   VALUES (?,?,?,?,?,NULL)""",
                (fingerprint, proposal_id, digest, created_at, expires_at),
            )
            self._conn.execute("UPDATE proposals SET status = 'approved' WHERE proposal_id = ?", (proposal_id,))
            self._conn.execute(
                "INSERT INTO audit(at, event, proposal_id, detail_json) VALUES (?,?,?,?)",
                (created_at, "approved", proposal_id, _json({"fingerprint": fingerprint})),
            )

    def get_approval(self, fingerprint: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM approvals WHERE fingerprint = ?", (fingerprint,)).fetchone()
        if row is None:
            return None
        return dict(row)

    def mark_approval_used(self, fingerprint: str, used_at: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE approvals SET used_at = ? WHERE fingerprint = ? AND used_at IS NULL",
                (used_at, fingerprint),
            )
            return cur.rowcount == 1

    def begin_attempt(self, proposal_id: str, subject_key: str, started_at: str) -> str:
        attempt_id = str(uuid.uuid4())
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                guard = self._conn.execute(
                    "SELECT state, proposal_id FROM subject_guards WHERE subject_key = ?",
                    (subject_key,),
                ).fetchone()
                if guard is None or guard["proposal_id"] != proposal_id:
                    raise GateError(GATE_DUPLICATE)
                if guard["state"] == "ambiguous":
                    raise GateError(GATE_AMBIGUOUS, proposal_id=proposal_id)
                if guard["state"] == "in_flight":
                    raise GateError(GATE_AMBIGUOUS, proposal_id=proposal_id)
                prior = self._conn.execute(
                    "SELECT outcome FROM attempts WHERE proposal_id = ? AND outcome IN ('in_flight','ambiguous')",
                    (proposal_id,),
                ).fetchone()
                if prior is not None:
                    raise GateError(GATE_AMBIGUOUS, proposal_id=proposal_id)
                self._conn.execute(
                    "INSERT INTO attempts(attempt_id, proposal_id, subject_key, started_at, outcome) VALUES (?,?,?,?,?)",
                    (attempt_id, proposal_id, subject_key, started_at, "in_flight"),
                )
                self._conn.execute(
                    "UPDATE subject_guards SET state = 'in_flight', updated_at = ? WHERE subject_key = ?",
                    (started_at, subject_key),
                )
                self._conn.execute("COMMIT")
            except GateError:
                self._conn.execute("ROLLBACK")
                raise
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return attempt_id

    def finish_attempt(self, attempt_id: str, proposal_id: str, subject_key: str, outcome: str) -> None:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute("UPDATE attempts SET outcome = ? WHERE attempt_id = ?", (outcome, attempt_id))
                if outcome == "success":
                    self._conn.execute("UPDATE proposals SET status = 'executed' WHERE proposal_id = ?", (proposal_id,))
                    self._conn.execute("DELETE FROM subject_guards WHERE subject_key = ?", (subject_key,))
                elif outcome == "ambiguous":
                    self._conn.execute("UPDATE proposals SET status = 'ambiguous' WHERE proposal_id = ?", (proposal_id,))
                    self._conn.execute(
                        "UPDATE subject_guards SET state = 'ambiguous', updated_at = ? WHERE subject_key = ?",
                        (_now(), subject_key),
                    )
                elif outcome == "failed_no_write":
                    self._conn.execute("UPDATE proposals SET status = 'rejected' WHERE proposal_id = ?", (proposal_id,))
                    self._conn.execute(
                        "DELETE FROM subject_guards WHERE subject_key = ? AND proposal_id = ? AND state IN ('open','in_flight')",
                        (subject_key, proposal_id),
                    )
                self._conn.execute(
                    "INSERT INTO audit(at, event, proposal_id, detail_json) VALUES (?,?,?,?)",
                    (_now(), f"attempt_{outcome}", proposal_id, _json({"attempt_id": attempt_id})),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def has_ambiguous(self, subject_key: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM subject_guards WHERE subject_key = ? AND state = 'ambiguous'",
            (subject_key,),
        ).fetchone()
        return row is not None

    def begin_creation_step(self, proposal_id: str, step: str, intent: dict[str, Any], *, customer_id: str | None = None, contact_id: str | None = None, location_id: str | None = None) -> str:
        step_id = str(uuid.uuid4())
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                prior = self._conn.execute(
                    "SELECT step, outcome FROM creation_journal WHERE proposal_id = ? AND outcome IN ('intended','ambiguous')",
                    (proposal_id,),
                ).fetchone()
                if prior is not None:
                    raise GateError(GATE_AMBIGUOUS, proposal_id=proposal_id, failed_step=prior["step"])
                self._conn.execute(
                    """INSERT INTO creation_journal(
                        step_id, proposal_id, step, intent_json, customer_id, contact_id, location_id, outcome, at
                    ) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (step_id, proposal_id, step, _json(intent), customer_id, contact_id, location_id, "intended", _now()),
                )
                self._conn.execute("COMMIT")
            except GateError:
                self._conn.execute("ROLLBACK")
                raise
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return step_id

    def finish_creation_step(self, step_id: str, outcome: str, result: dict[str, Any] | None = None, *, customer_id: str | None = None, contact_id: str | None = None, location_id: str | None = None) -> None:
        with self._lock:
            self._conn.execute(
                """UPDATE creation_journal
                   SET outcome = ?, result_json = ?,
                       customer_id = COALESCE(?, customer_id),
                       contact_id = COALESCE(?, contact_id),
                       location_id = COALESCE(?, location_id)
                   WHERE step_id = ?""",
                (outcome, _json(result or {}), customer_id, contact_id, location_id, step_id),
            )

    def creation_journal(self, proposal_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM creation_journal WHERE proposal_id = ? ORDER BY at, step_id",
            (proposal_id,),
        ).fetchall()
        found = []
        for row in rows:
            found.append({
                "step_id": row["step_id"],
                "step": row["step"],
                "outcome": row["outcome"],
                "intent": json.loads(row["intent_json"]),
                "result": json.loads(row["result_json"]) if row["result_json"] else None,
                "customer_id": row["customer_id"],
                "contact_id": row["contact_id"],
                "location_id": row["location_id"],
            })
        return found

    def audit_events(self, proposal_id: str | None = None) -> list[dict[str, Any]]:
        if proposal_id:
            rows = self._conn.execute("SELECT * FROM audit WHERE proposal_id = ? ORDER BY id", (proposal_id,)).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM audit ORDER BY id").fetchall()
        return [dict(row) for row in rows]
