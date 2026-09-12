"""SQLite receipt store. Pub/Sub ack is allowed only after this commit succeeds."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .constants import (
    ALLOWED_SENDER,
    DISPATCH_PENDING,
    DISPATCH_SKIPPED,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def body_hash(payload: str | bytes | None) -> str:
    if payload is None:
        data = b""
    elif isinstance(payload, bytes):
        data = payload
    else:
        data = payload.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


class ReceiptStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._create()

    def close(self) -> None:
        self.conn.close()

    def _create(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS watch_cursors (
                mailbox TEXT PRIMARY KEY,
                history_id TEXT NOT NULL,
                watch_expiration TEXT,
                topic TEXT,
                last_notification_at TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY,
                mailbox TEXT NOT NULL,
                gmail_message_id TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                rfc_message_id TEXT,
                sender TEXT,
                recipients_json TEXT,
                subject TEXT,
                gmail_received_at TEXT,
                detected_at TEXT NOT NULL,
                body_text TEXT,
                raw_message TEXT,
                body_hash TEXT NOT NULL,
                labels_before_json TEXT,
                labels_after_json TEXT,
                detection_path TEXT NOT NULL,
                classification TEXT NOT NULL,
                test_marker TEXT,
                eligible INTEGER NOT NULL,
                skip_reasons_json TEXT,
                codex_dispatch_state TEXT NOT NULL,
                codex_dispatch_id TEXT,
                created_at TEXT NOT NULL,
                UNIQUE (mailbox, gmail_message_id)
            );

            CREATE TABLE IF NOT EXISTS pubsub_notifications (
                pubsub_message_id TEXT PRIMARY KEY,
                history_id TEXT,
                committed_at TEXT NOT NULL,
                acked_at TEXT
            );
            """
        )

    def upsert_watch(
        self,
        mailbox: str,
        *,
        history_id: str,
        expiration: str | None,
        topic: str | None,
    ) -> None:
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO watch_cursors (mailbox, history_id, watch_expiration, topic, last_notification_at, updated_at)
            VALUES (?, ?, ?, ?, NULL, ?)
            ON CONFLICT(mailbox) DO UPDATE SET
                history_id = excluded.history_id,
                watch_expiration = excluded.watch_expiration,
                topic = excluded.topic,
                updated_at = excluded.updated_at
            """,
            (mailbox, str(history_id), expiration, topic, now),
        )

    def get_watch(self, mailbox: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM watch_cursors WHERE mailbox = ?",
            (mailbox,),
        ).fetchone()
        return dict(row) if row else None

    def get_receipt(self, mailbox: str, gmail_message_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM receipts WHERE mailbox = ? AND gmail_message_id = ?",
            (mailbox, gmail_message_id),
        ).fetchone()
        return dict(row) if row else None

    def list_receipts(self, mailbox: str | None = None) -> list[dict[str, Any]]:
        if mailbox:
            rows = self.conn.execute(
                "SELECT * FROM receipts WHERE mailbox = ? ORDER BY id",
                (mailbox,),
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM receipts ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def eligible_receipts(self, mailbox: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM receipts WHERE mailbox = ? AND eligible = 1 ORDER BY id",
            (mailbox,),
        ).fetchall()
        return [dict(row) for row in rows]

    def labels_unchanged(self, receipt: dict[str, Any]) -> bool:
        return receipt.get("labels_before_json") == receipt.get("labels_after_json")

    def mark_dispatched(self, mailbox: str, gmail_message_id: str, dispatch_id: str) -> None:
        self.conn.execute(
            """
            UPDATE receipts
            SET codex_dispatch_state = ?, codex_dispatch_id = ?
            WHERE mailbox = ? AND gmail_message_id = ?
            """,
            ("delivered", dispatch_id, mailbox, gmail_message_id),
        )

    def commit_notification(
        self,
        *,
        mailbox: str,
        history_id: str,
        detection_path: str,
        pubsub_message_id: str | None,
        receipts: Iterable[dict[str, Any]],
    ) -> dict[str, Any]:
        """Persist cursor + receipts atomically. Caller may ack only if ok is True."""
        inserted = 0
        duplicates = 0
        skipped = 0
        now = utc_now()
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            existing_cursor = self.get_watch(mailbox)
            self.conn.execute(
                """
                INSERT INTO watch_cursors (mailbox, history_id, watch_expiration, topic, last_notification_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(mailbox) DO UPDATE SET
                    history_id = excluded.history_id,
                    last_notification_at = excluded.last_notification_at,
                    updated_at = excluded.updated_at
                """,
                (
                    mailbox,
                    str(history_id),
                    (existing_cursor or {}).get("watch_expiration"),
                    (existing_cursor or {}).get("topic"),
                    now,
                    now,
                ),
            )
            for receipt in receipts:
                eligible = bool(receipt.get("eligible"))
                if not eligible:
                    # Isolated-test harness: omit unmarked/customer bodies. Not production capture.
                    skipped += 1
                    sender = receipt.get("sender") or ""
                    if sender.lower() != ALLOWED_SENDER:
                        sender = ""
                    self.conn.execute(
                        """
                        INSERT OR IGNORE INTO receipts (
                            mailbox, gmail_message_id, thread_id, rfc_message_id, sender,
                            recipients_json, subject, gmail_received_at, detected_at,
                            body_text, raw_message, body_hash, labels_before_json,
                            labels_after_json, detection_path, classification, test_marker,
                            eligible, skip_reasons_json, codex_dispatch_state,
                            codex_dispatch_id, created_at
                        ) VALUES (?, ?, ?, NULL, ?, '[]', NULL, NULL, ?, NULL, NULL, ?,
                                  '[]', '[]', ?, ?, NULL, 0, ?, ?, NULL, ?)
                        """,
                        (
                            mailbox,
                            receipt["gmail_message_id"],
                            receipt.get("thread_id") or "",
                            sender,
                            now,
                            body_hash(""),
                            detection_path,
                            receipt.get("classification") or "ineligible",
                            _json(receipt.get("reasons") or []),
                            DISPATCH_SKIPPED,
                            now,
                        ),
                    )
                    continue

                payload = (
                    receipt.get("raw_message")
                    if receipt.get("raw_message") is not None
                    else receipt.get("body_text")
                )
                digest = receipt.get("body_hash") or body_hash(payload)
                cur = self.conn.execute(
                    """
                    INSERT OR IGNORE INTO receipts (
                        mailbox, gmail_message_id, thread_id, rfc_message_id, sender,
                        recipients_json, subject, gmail_received_at, detected_at,
                        body_text, raw_message, body_hash, labels_before_json,
                        labels_after_json, detection_path, classification, test_marker,
                        eligible, skip_reasons_json, codex_dispatch_state,
                        codex_dispatch_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, '[]', ?, NULL, ?)
                    """,
                    (
                        mailbox,
                        receipt["gmail_message_id"],
                        receipt["thread_id"],
                        receipt.get("rfc_message_id"),
                        receipt.get("sender"),
                        _json(receipt.get("recipients") or []),
                        receipt.get("subject"),
                        receipt.get("gmail_received_at"),
                        receipt.get("detected_at") or now,
                        receipt.get("body_text"),
                        receipt.get("raw_message"),
                        digest,
                        _json(receipt.get("labels_before") or []),
                        _json(receipt.get("labels_after") or receipt.get("labels_before") or []),
                        detection_path,
                        receipt["classification"],
                        receipt.get("test_marker"),
                        DISPATCH_PENDING,
                        now,
                    ),
                )
                if cur.rowcount == 1:
                    inserted += 1
                else:
                    duplicates += 1
            if pubsub_message_id:
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO pubsub_notifications (pubsub_message_id, history_id, committed_at, acked_at)
                    VALUES (?, ?, ?, NULL)
                    """,
                    (pubsub_message_id, str(history_id), now),
                )
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return {
            "ok": True,
            "inserted": inserted,
            "duplicates": duplicates,
            "skipped_ineligible": skipped,
            "history_id": str(history_id),
            "mailbox": mailbox,
            "detection_path": detection_path,
            "pubsub_message_id": pubsub_message_id,
        }

    def mark_acked(self, pubsub_message_id: str) -> None:
        self.conn.execute(
            "UPDATE pubsub_notifications SET acked_at = ? WHERE pubsub_message_id = ?",
            (utc_now(), pubsub_message_id),
        )


def should_ack(commit_result: dict[str, Any] | None, error: BaseException | None = None) -> bool:
    """Ack only after durable receipt/cursor handling succeeded."""
    if error is not None:
        return False
    return bool(commit_result and commit_result.get("ok"))
