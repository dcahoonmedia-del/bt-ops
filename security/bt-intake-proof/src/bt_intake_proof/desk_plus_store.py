"""Isolated Daniel plus-control cursor and seen tables.

Never writes contactus@ watch_cursors. contactus intake history is untouched.
Schema setup uses execute(), never executescript(), so it cannot implicitly
commit an active revise transaction.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .constants import PLUS_DISCOVERY_CURSOR_KEY, STALE_PLUS_CONTROL_ID
from .store import utc_now


PLUS_CURSOR_KEY = PLUS_DISCOVERY_CURSOR_KEY
STATUS_DISCOVERED = "discovered"
STATUS_AWAITING_LABEL = "awaiting_label"
STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_PROCESSED = "processed"
STATUS_SKIPPED = "skipped"
STATUS_BLOCKED = "blocked"
CLAIM_LEASE = timedelta(minutes=2)


def _parse_time(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _add_column(conn: Any, table: str, name: str, spec: str) -> None:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if name in cols:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {spec}")


def ensure_plus_tables(layer: Any) -> None:
    """Create isolated plus tables. Safe beside an open transaction: no executescript."""
    conn = layer.conn
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS plus_control_cursors (
            cursor_key TEXT PRIMARY KEY,
            history_id TEXT NOT NULL,
            profile_history_id TEXT,
            last_reconcile_at TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS plus_control_seen (
            gmail_message_id TEXT PRIMARY KEY,
            first_seen_at TEXT NOT NULL,
            last_event TEXT,
            status TEXT NOT NULL,
            reason TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
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
        )
        """
    )
    _add_column(conn, "plus_control_seen", "claimed_at", "TEXT")
    _add_column(conn, "plus_control_seen", "claimed_by", "TEXT")
    _add_column(conn, "plus_result_outbox", "body_digest", "TEXT")
    _add_column(conn, "plus_result_outbox", "payload_digest", "TEXT")


def contactus_watch_untouched(layer: Any, mailbox: str) -> dict[str, Any] | None:
    """Read-only helper. Plus code must not call upsert_watch for contactus@."""
    return layer.store.get_watch(mailbox)


def get_plus_cursor(layer: Any) -> dict[str, Any] | None:
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
    """Advance-only checkpoint. Never writes watch_cursors. Caller owns the transaction."""
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
    status: str = STATUS_DISCOVERED,
    reason: str | None = None,
) -> dict[str, Any]:
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
    claimed_at: str | None = None,
    claimed_by: str | None = None,
) -> None:
    layer.conn.execute(
        """
        UPDATE plus_control_seen
        SET status = ?,
            reason = COALESCE(?, reason),
            last_event = COALESCE(?, last_event),
            updated_at = ?,
            claimed_at = COALESCE(?, claimed_at),
            claimed_by = COALESCE(?, claimed_by)
        WHERE gmail_message_id = ?
        """,
        (status, reason, event, utc_now(), claimed_at, claimed_by, gmail_message_id),
    )


def get_seen(layer: Any, gmail_message_id: str) -> dict[str, Any] | None:
    row = layer.conn.execute(
        "SELECT * FROM plus_control_seen WHERE gmail_message_id = ?",
        (gmail_message_id,),
    ).fetchone()
    return dict(row) if row else None


def new_worker_id() -> str:
    return uuid4().hex


def lease_expired(row: dict[str, Any], *, now: datetime | None = None) -> bool:
    if str(row.get("status") or "") != STATUS_PROCESSING:
        return False
    claimed = _parse_time(row.get("claimed_at"))
    if claimed is None:
        return True
    clock = now or datetime.now(timezone.utc)
    return clock - claimed >= CLAIM_LEASE


def claim_seen(layer: Any, gmail_message_id: str, *, worker_id: str | None = None) -> bool:
    """Lease an authorized candidate. Expired processing leases may be reclaimed.

    Discovered and awaiting-label rows are not executable. Schema must already exist.
    """
    row = get_seen(layer, gmail_message_id)
    if row is None:
        return False
    status = str(row.get("status") or "")
    if status == STATUS_PROCESSING and not lease_expired(row):
        return False
    if status not in {STATUS_PENDING, STATUS_BLOCKED} and not (
        status == STATUS_PROCESSING and lease_expired(row)
    ):
        return False
    worker = worker_id or new_worker_id()
    now = utc_now()
    cur = layer.conn.execute(
        """
        UPDATE plus_control_seen
        SET status = ?, claimed_at = ?, claimed_by = ?, updated_at = ?
        WHERE gmail_message_id = ? AND (
            status IN (?, ?)
            OR (status = ? AND (claimed_at IS NULL OR claimed_at <= ?))
        )
        """,
        (
            STATUS_PROCESSING,
            now,
            worker,
            now,
            gmail_message_id,
            STATUS_PENDING,
            STATUS_BLOCKED,
            STATUS_PROCESSING,
            (datetime.now(timezone.utc) - CLAIM_LEASE).isoformat(),
        ),
    )
    return int(cur.rowcount or 0) == 1


def executable_seen_ids(layer: Any) -> list[str]:
    """Authorized or reclaimable rows only. Awaiting-label is not executable."""
    rows = layer.conn.execute(
        "SELECT * FROM plus_control_seen ORDER BY first_seen_at"
    ).fetchall()
    out: list[str] = []
    for row in rows:
        item = dict(row)
        status = str(item.get("status") or "")
        if status in {STATUS_PENDING, STATUS_BLOCKED}:
            out.append(str(item["gmail_message_id"]))
        elif lease_expired(item):
            out.append(str(item["gmail_message_id"]))
    return out


def pending_seen_ids(layer: Any) -> list[str]:
    return executable_seen_ids(layer)


def unclassified_seen_ids(layer: Any) -> list[str]:
    rows = layer.conn.execute(
        """
        SELECT gmail_message_id FROM plus_control_seen
        WHERE status IN (?, ?)
        ORDER BY first_seen_at
        """,
        (STATUS_DISCOVERED, STATUS_AWAITING_LABEL),
    ).fetchall()
    return [str(row["gmail_message_id"]) for row in rows]


def is_stale_forbidden(gmail_message_id: str) -> bool:
    return str(gmail_message_id or "").strip() == STALE_PLUS_CONTROL_ID


def checkpoint_history_events(
    layer: Any,
    events: list[dict[str, str]],
    *,
    history_id: str,
    profile_history_id: str | None = None,
    reconciled: bool = False,
) -> dict[str, Any]:
    """Persist every recoverable event, then advance the cursor in one transaction."""
    own_txn = not layer.conn.in_transaction
    if own_txn:
        layer.conn.execute("BEGIN IMMEDIATE")
    try:
        for item in events:
            mid = str(item.get("id") or "").strip()
            if not mid:
                continue
            event = str(item.get("event") or "history")
            if is_stale_forbidden(mid):
                record_seen(layer, mid, event=event, status=STATUS_SKIPPED, reason="stale_plus_control_forbidden")
                update_seen(layer, mid, status=STATUS_SKIPPED, reason="stale_plus_control_forbidden", event=event)
                continue
            existing = get_seen(layer, mid)
            if existing and existing.get("status") in {STATUS_PROCESSED, STATUS_SKIPPED}:
                continue
            if existing:
                record_seen(layer, mid, event=event, status=str(existing.get("status") or STATUS_DISCOVERED))
            else:
                record_seen(layer, mid, event=event, status=STATUS_DISCOVERED, reason=event)
        saved = save_plus_cursor(
            layer,
            history_id,
            profile_history_id=profile_history_id,
            reconciled=reconciled,
        )
        if own_txn:
            layer.conn.execute("COMMIT")
        return saved
    except Exception:
        if own_txn and layer.conn.in_transaction:
            layer.conn.execute("ROLLBACK")
        raise
