"""One plus-control poll: discover, independently authorize, save once, one result."""

from __future__ import annotations

from typing import Any

from .constants import MAILBOX, STALE_PLUS_CONTROL_ID, TRANSPORT_PLUS
from .desk_plus_discover import classify_plus_metadata, discover_plus_controls, resolve_plus_labels
from .desk_plus_result_send import (
    REASON_CHANNEL_NOT_READY,
    deliver_plus_results,
    plus_result_channel_ready,
    reconcile_plus_result_outbox,
    unblock_plus_results_if_ready,
)
from .desk_plus_store import (
    STATUS_AWAITING_LABEL,
    STATUS_BLOCKED,
    STATUS_PROCESSED,
    STATUS_SKIPPED,
    claim_seen,
    contactus_watch_untouched,
    ensure_plus_tables,
    get_seen,
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


def _discover_or_plus_client(client: Any | None) -> Any:
    if client is not None:
        return client
    from .desk_plus_discover import _discover_client

    return _discover_client()


def process_discovered_plus_control(
    layer: Any,
    gmail_message_id: str,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    from .desk_bridge import process_plus_control_mail

    ensure_plus_tables(layer)
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
    already = get_seen(layer, mid)
    if already and already.get("status") == STATUS_PROCESSED:
        result = process_plus_control_mail(layer, gmail_message_id=mid)
        result["replayed"] = True
        result["contactus_traffic"] = False
        return result
    gmail = _discover_or_plus_client(client)
    resolved = resolve_plus_labels(gmail) if gmail is not None else {}
    subset = classify_plus_metadata(layer, gmail, mid, event="revalidate", resolved=resolved)
    if subset.get("awaiting_label") or subset.get("status") == STATUS_AWAITING_LABEL:
        return {
            "ok": False,
            "reason": subset.get("reason") or "control_label_missing",
            "gmail_message_id": mid,
            "processed": False,
            "awaiting_label": True,
            "contactus_traffic": False,
            "raw_fetched": False,
        }
    if not subset.get("ok"):
        if subset.get("reason") == "already_claimed":
            return {"ok": False, "reason": "already_claimed", "gmail_message_id": mid, "processed": False}
        return {
            "ok": False,
            "reason": str(subset.get("reason") or "plus_subset_rejected"),
            "gmail_message_id": mid,
            "processed": False,
            "contactus_traffic": False,
            "raw_fetched": False,
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
    reconciled = reconcile_plus_result_outbox(layer, client=client)
    unblocked = unblock_plus_results_if_ready(layer)
    processed: list[dict[str, Any]] = []
    ids = list(dict.fromkeys(list(discovered.get("candidates") or []) + pending_seen_ids(layer)))
    ready = plus_result_channel_ready()
    if not ready.get("ready"):
        for mid in ids:
            if is_stale_forbidden(mid):
                continue
            seen = get_seen(layer, mid)
            if seen and seen.get("status") in {STATUS_PROCESSED, STATUS_SKIPPED}:
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
            "reconciled": reconciled,
            "consumed": False,
            "contactus_traffic": False,
            "contactus_watch_unchanged": contactus_watch_untouched(layer, MAILBOX) == watch_before,
            "stale_excluded": STALE_PLUS_CONTROL_ID,
            "exactly_once_delivery": False,
        }
    for mid in ids:
        if is_stale_forbidden(mid):
            record_seen(layer, mid, event="forbidden", status=STATUS_SKIPPED, reason="stale_plus_control_forbidden")
            update_seen(layer, mid, status=STATUS_SKIPPED, reason="stale_plus_control_forbidden")
            processed.append({"ok": False, "reason": "stale_plus_control_forbidden", "gmail_message_id": mid})
            continue
        processed.append(process_discovered_plus_control(layer, mid, client=client))
    delivered = deliver_plus_results(layer, transport)
    return {
        "ok": True,
        "transport": TRANSPORT_PLUS,
        "discovery": discovered,
        "processed": processed,
        "delivered": delivered,
        "reconciled": reconciled,
        "unblocked_results": unblocked,
        "contactus_traffic": False,
        "contactus_outbox_delta": _contactus_outbox_count(layer) - contactus_before,
        "contactus_watch_unchanged": contactus_watch_untouched(layer, MAILBOX) == watch_before,
        "stale_excluded": STALE_PLUS_CONTROL_ID,
        "exactly_once_delivery": False,
    }


def recover_plus_result_sends(layer: Any, sent_records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Reconcile uncertain plus results via Daniel readonly SENT, then deliver pending only."""
    del sent_records
    ensure_plus_tables(layer)
    reconciled = reconcile_plus_result_outbox(layer)
    unblocked = unblock_plus_results_if_ready(layer)
    delivered = deliver_plus_results(layer)
    return {
        "ok": True,
        "reconciled": reconciled,
        "delivered": delivered,
        "unblocked_results": unblocked,
        "blind_retry": False,
        "exactly_once_delivery": False,
        "contactus_traffic": False,
    }
