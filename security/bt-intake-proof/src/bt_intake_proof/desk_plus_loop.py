"""One plus-control poll: discover, independently authorize, save once, one result."""

from __future__ import annotations

from typing import Any

from .constants import MAILBOX, STALE_PLUS_CONTROL_ID, TRANSPORT_PLUS
from .desk_plus_discover import discover_plus_controls
from .desk_plus_result_send import (
    REASON_CHANNEL_NOT_READY,
    deliver_plus_results,
    plus_result_channel_ready,
    reconcile_plus_result_outbox,
)
from .desk_plus_store import (
    STATUS_BLOCKED,
    STATUS_PROCESSED,
    STATUS_SKIPPED,
    claim_seen,
    contactus_watch_untouched,
    ensure_plus_tables,
    is_stale_forbidden,
    pending_seen_ids,
    record_seen,
    update_seen,
)


def _contactus_outbox_count(layer: Any) -> int:
    row = layer.conn.execute(
        "SELECT COUNT(*) AS n FROM sqlite_master WHERE type='table' AND name='desk_result_outbox'"
    ).fetchone()
    if not row or not row["n"]:
        return 0
    return int(layer.conn.execute("SELECT COUNT(*) AS n FROM desk_result_outbox").fetchone()["n"])


def process_discovered_plus_control(layer: Any, gmail_message_id: str) -> dict[str, Any]:
    from .desk_bridge import process_plus_control_mail

    mid = str(gmail_message_id or "").strip()
    if is_stale_forbidden(mid):
        record_seen(layer, mid, event="forbidden", status=STATUS_SKIPPED, reason="stale_plus_control_forbidden")
        update_seen(layer, mid, status=STATUS_SKIPPED, reason="stale_plus_control_forbidden")
        return {
            "ok": False,
            "reason": "stale_plus_control_forbidden",
            "gmail_message_id": mid,
            "processed": False,
            "contactus_traffic": False,
        }
    ready = plus_result_channel_ready()
    if not ready.get("ready"):
        record_seen(layer, mid, event="blocked_channel", status=STATUS_BLOCKED, reason=REASON_CHANNEL_NOT_READY)
        update_seen(layer, mid, status=STATUS_BLOCKED, reason=REASON_CHANNEL_NOT_READY)
        return {
            "ok": False,
            "reason": REASON_CHANNEL_NOT_READY,
            "gmail_message_id": mid,
            "processed": False,
            "consumed": False,
            "contactus_traffic": False,
            "activation_blocker": ready.get("blocker"),
        }
    if not claim_seen(layer, mid):
        return {"ok": False, "reason": "already_claimed", "gmail_message_id": mid, "processed": False}
    before_contactus = _contactus_outbox_count(layer)
    watch_before = contactus_watch_untouched(layer, MAILBOX)
    result = process_plus_control_mail(layer, gmail_message_id=mid)
    result["contactus_traffic"] = False
    result["contactus_outbox_delta"] = _contactus_outbox_count(layer) - before_contactus
    result["contactus_watch_unchanged"] = contactus_watch_untouched(layer, MAILBOX) == watch_before
    if result.get("reason") == REASON_CHANNEL_NOT_READY:
        update_seen(layer, mid, status=STATUS_BLOCKED, reason=REASON_CHANNEL_NOT_READY)
        return result
    update_seen(
        layer,
        mid,
        status=STATUS_PROCESSED,
        reason=None if result.get("ok") else str(result.get("reason") or "failed"),
    )
    return result


def poll_plus_controls_once(layer: Any, *, client: Any | None = None, transport: Any | None = None) -> dict[str, Any]:
    """Discover, independently re-check, save at most once, deliver pending plus results."""
    ensure_plus_tables(layer)
    watch_before = contactus_watch_untouched(layer, MAILBOX)
    contactus_before = _contactus_outbox_count(layer)
    discovered = discover_plus_controls(layer, client=client)
    processed: list[dict[str, Any]] = []
    ids = list(dict.fromkeys(list(discovered.get("candidates") or []) + pending_seen_ids(layer)))
    ready = plus_result_channel_ready()
    if not ready.get("ready"):
        for mid in ids:
            if is_stale_forbidden(mid):
                continue
            record_seen(layer, mid, event="blocked_channel", status=STATUS_BLOCKED, reason=REASON_CHANNEL_NOT_READY)
            update_seen(layer, mid, status=STATUS_BLOCKED, reason=REASON_CHANNEL_NOT_READY)
        return {
            "ok": False,
            "reason": REASON_CHANNEL_NOT_READY,
            "activation_blocker": ready.get("blocker"),
            "discovery": discovered,
            "processed": [],
            "delivered": [],
            "consumed": False,
            "contactus_traffic": False,
            "contactus_watch_unchanged": contactus_watch_untouched(layer, MAILBOX) == watch_before,
            "stale_excluded": STALE_PLUS_CONTROL_ID,
        }
    for mid in ids:
        if is_stale_forbidden(mid):
            record_seen(layer, mid, event="forbidden", status=STATUS_SKIPPED, reason="stale_plus_control_forbidden")
            update_seen(layer, mid, status=STATUS_SKIPPED, reason="stale_plus_control_forbidden")
            processed.append({"ok": False, "reason": "stale_plus_control_forbidden", "gmail_message_id": mid})
            continue
        processed.append(process_discovered_plus_control(layer, mid))
    delivered = deliver_plus_results(layer, transport)
    return {
        "ok": True,
        "transport": TRANSPORT_PLUS,
        "discovery": discovered,
        "processed": processed,
        "delivered": delivered,
        "contactus_traffic": False,
        "contactus_outbox_delta": _contactus_outbox_count(layer) - contactus_before,
        "contactus_watch_unchanged": contactus_watch_untouched(layer, MAILBOX) == watch_before,
        "stale_excluded": STALE_PLUS_CONTROL_ID,
        "exactly_once_delivery": False,
    }


def recover_plus_result_sends(layer: Any, sent_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Reconcile uncertain plus results, then deliver only still-pending rows."""
    reconciled = reconcile_plus_result_outbox(layer, sent_records)
    delivered = deliver_plus_results(layer)
    return {
        "ok": True,
        "reconciled": reconciled,
        "delivered": delivered,
        "blind_retry": False,
        "exactly_once_delivery": False,
        "contactus_traffic": False,
    }
