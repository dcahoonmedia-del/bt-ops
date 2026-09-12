"""Host-side desk round trip: deliver results, execute desk-queued sends, verify.

Phase E leftovers are never selected. Ambiguous/unknown sends are not retried.
"""

from __future__ import annotations

from typing import Any

from .bounded_send import execute_desk_queued_sends
from .cases import CaseLayer
from .contactus_send import configured_send_transport
from .desk_bridge import deliver_pending_desk_mail, enqueue_send_followup, ensure_bridge_tables
from .phasee_constants import STATUS_ATTEMPTED, STATUS_UNKNOWN
from .send_bind import QUEUED_BY_DESK, ensure_send_tables
from .send_verify import verify_sent
from .store import ReceiptStore


def verify_attempted_desk_sends(layer: CaseLayer, transport: Any) -> list[dict[str, Any]]:
    ensure_send_tables(layer)
    rows = layer.conn.execute(
        """
        SELECT id, status FROM case_send_actions
        WHERE queued_by = ? AND status = ?
        ORDER BY id
        """,
        (QUEUED_BY_DESK, STATUS_ATTEMPTED),
    ).fetchall()
    results = []
    for row in rows:
        results.append(verify_sent(layer, row["id"], transport))
    unknown = layer.conn.execute(
        "SELECT id FROM case_send_actions WHERE queued_by = ? AND status = ?",
        (QUEUED_BY_DESK, STATUS_UNKNOWN),
    ).fetchall()
    for row in unknown:
        results.append({"ok": False, "action_id": row["id"], "reason": "unknown_must_reconcile", "retried": False})
    return results


def finish_desk_roundtrip(
    store: ReceiptStore,
    *,
    send_transport: Any | None = None,
    verify_transport: Any | None = None,
) -> dict[str, Any]:
    layer = CaseLayer(store)
    ensure_bridge_tables(layer)
    ensure_send_tables(layer)
    send = send_transport or configured_send_transport()
    delivered = deliver_pending_desk_mail(layer, send)
    executed = execute_desk_queued_sends(layer, send)
    for item in executed:
        enqueue_send_followup(layer, item)
    verified: list[dict[str, Any]] = []
    if verify_transport is not None:
        verified = verify_attempted_desk_sends(layer, verify_transport)
    delivered_after = deliver_pending_desk_mail(layer, send)
    return {
        "delivered": delivered + delivered_after,
        "executed": executed,
        "verified": verified,
    }
