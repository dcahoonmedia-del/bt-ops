"""Isolated Daniel plus-control cursor and seen tables.

Never writes contactus@ watch_cursors. contactus intake history is untouched.
"""

from __future__ import annotations

from typing import Any

from .constants import PLUS_DISCOVERY_CURSOR_KEY, STALE_PLUS_CONTROL_ID
from .store import utc_now


PLUS_CURSOR_KEY = PLUS_DISCOVERY_CURSOR_KEY
STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_PROCESSED = "processed"
STATUS_SKIPPED = "skipped"
STATUS_BLOCKED = "blocked"


def ensure_plus_tables(layer: Any) -> None:
    layer.conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS plus_control_cursors (
            cursor_key TEXT PRIMARY KEY,
            history_id TEXT NOT NULL,
            profile_history_id TEXT,
            last_reconcile_at TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS plus_control_seen (
            gmail_message_id TEXT PRIMARY KEY,
            first_seen_at TEXT NOT NULL,
            last_event TEXT,
            status TEXT NOT NULL,
            reason TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS plus_result_outbox (
            id INTEGER PRIMARY KEY,
            control_gmail_id TEXT NOT NULL,
            nonce TEXT,
            kind TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT NOT NULL,
            provider_id TEXT,
            rfc_message_id TEXT,
            created_at TEXT NOT NULL,
            sent_at TEXT,
            UNIQUE (control_gmail_id, kind)
        );
        """
    )


def contactus_watch_untouched(layer: Any, mailbox: str) -> dict[str, Any] | None:
    """Read-only helper. Plus code must not call upsert_watch for contactus@."""
    return layer.store.get_watch(mailbox)


def get_plus_cursor(layer: Any) -> dict[str, Any] | None:
    ensure_plus_tables(layer)
    row = layer.conn.execute(
        "SELECT * FROM plus_control_cursors WHERE cursor_key = ?",
        (PLUS_CURSOR_KEY,),
    ).fetchone()
    return dict(row) if row else None


def _later_history_id(current: str, incoming: str) -> str:
    if current.isdigit() and incoming.isdigit() and int(incoming) < int(current):
        return current
    return incoming or current


def save_plus_cursor(
    layer: Any,
    history_id: str,
    *,
    profile_history_id: str | None = None,
    reconciled: bool = False,
) -> dict[str, Any]:
    """Advance-only checkpoint. Never writes watch_cursors."""
    ensure_plus_tables(layer)
    now = utc_now()
    existing = get_plus_cursor(layer)
    kept = _later_history_id(str((existing or {}).get("history_id") or ""), str(history_id or ""))
    profile = profile_history_id if profile_history_id is not None else (existing or {}).get("profile_history_id")
    reconcile_at = now if reconciled else (existing or {}).get("last_reconcile_at")
    layer.conn.execute(
        """
        INSERT INTO plus_control_cursors (cursor_key, history_id, profile_history_id, last_reconcile_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(cursor_key) DO UPDATE SET
            history_id = excluded.history_id,
            profile_history_id = excluded.profile_history_id,
            last_reconcile_at = excluded.last_reconcile_at,
            updated_at = excluded.updated_at
        """,
        (PLUS_CURSOR_KEY, kept, profile, reconcile_at, now),
    )
    saved = get_plus_cursor(layer)
    assert saved is not None
    return saved


def record_seen(
    layer: Any,
    gmail_message_id: str,
    *,
    event: str,
    status: str = STATUS_PENDING,
    reason: str | None = None,
) -> dict[str, Any]:
    ensure_plus_tables(layer)
    now = utc_now()
    layer.conn.execute(
        """
        INSERT INTO plus_control_seen (gmail_message_id, first_seen_at, last_event, status, reason, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(gmail_message_id) DO UPDATE SET
            last_event = excluded.last_event,
            updated_at = excluded.updated_at
        """,
        (gmail_message_id, now, event, status, reason, now),
    )
    row = layer.conn.execute(
        "SELECT * FROM plus_control_seen WHERE gmail_message_id = ?",
        (gmail_message_id,),
    ).fetchone()
    return dict(row) if row else {"gmail_message_id": gmail_message_id, "status": status}


def update_seen(
    layer: Any,
    gmail_message_id: str,
    *,
    status: str,
    reason: str | None = None,
    event: str | None = None,
) -> None:
    ensure_plus_tables(layer)
    layer.conn.execute(
        """
        UPDATE plus_control_seen
        SET status = ?, reason = COALESCE(?, reason), last_event = COALESCE(?, last_event), updated_at = ?
        WHERE gmail_message_id = ?
        """,
        (status, reason, event, utc_now(), gmail_message_id),
    )


def get_seen(layer: Any, gmail_message_id: str) -> dict[str, Any] | None:
    ensure_plus_tables(layer)
    row = layer.conn.execute(
        "SELECT * FROM plus_control_seen WHERE gmail_message_id = ?",
        (gmail_message_id,),
    ).fetchone()
    return dict(row) if row else None


def claim_seen(layer: Any, gmail_message_id: str) -> bool:
    """Single-claim processing. Returns False if another worker already claimed it."""
    ensure_plus_tables(layer)
    record_seen(layer, gmail_message_id, event="claim", status=STATUS_PENDING)
    cur = layer.conn.execute(
        """
        UPDATE plus_control_seen
        SET status = ?, updated_at = ?
        WHERE gmail_message_id = ? AND status IN (?, ?)
        """,
        (STATUS_PROCESSING, utc_now(), gmail_message_id, STATUS_PENDING, STATUS_BLOCKED),
    )
    return int(cur.rowcount or 0) == 1


def pending_seen_ids(layer: Any) -> list[str]:
    ensure_plus_tables(layer)
    rows = layer.conn.execute(
        """
        SELECT gmail_message_id FROM plus_control_seen
        WHERE status IN (?, ?)
        ORDER BY first_seen_at
        """,
        (STATUS_PENDING, STATUS_BLOCKED),
    ).fetchall()
    return [str(row["gmail_message_id"]) for row in rows]


def is_stale_forbidden(gmail_message_id: str) -> bool:
    return str(gmail_message_id or "").strip() == STALE_PLUS_CONTROL_ID
