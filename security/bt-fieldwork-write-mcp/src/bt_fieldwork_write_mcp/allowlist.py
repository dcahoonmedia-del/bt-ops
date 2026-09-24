"""Strict typed operations. Unknown names and extra fields fail closed."""

from __future__ import annotations

from typing import Any

OP_LOCATION_NOTES = "update_service_location_notes"
OP_WORK_ORDER_NOTES = "update_work_order_notes"
OP_CREATE_WORK_ORDER = "create_work_order"

ALLOWED_OPS = frozenset({OP_LOCATION_NOTES, OP_WORK_ORDER_NOTES, OP_CREATE_WORK_ORDER})

LOCATION_NOTE_FIELDS = frozenset({"customer_id", "location_id", "notes"})
WORK_ORDER_NOTE_FIELDS = frozenset({"work_order_id", "service_appointment_id", "instructions", "private_notes"})
CREATE_FIELDS = frozenset(
    {
        "customer_id",
        "service_location_id",
        "repeat_type",
        "repeat_period",
        "line_items",
        "occurrences",
    }
)
LINE_ITEM_FIELDS = frozenset({"name", "type", "quantity", "price"})
OCCURRENCE_FIELDS = frozenset({"service_route_ids", "starts_at", "duration", "use_time_window"})

FORBIDDEN_OPS = frozenset(
    {
        "create_customer",
        "on_our_way",
        "send_message",
        "send_sms",
        "send_email",
        "http",
        "passthrough",
    }
)

GATE_WRITES_DISABLED = "writes_disabled"
GATE_MAPPING_UNVERIFIED = "work_order_id_mapping_unverified"
GATE_SCHEMA_UNVERIFIED = "work_order_schema_unverified"
GATE_LEAD_STATUS = "never_lead_status_accounts"
GATE_UNKNOWN_FIELD = "unknown_field"
GATE_UNKNOWN_OP = "unknown_operation"
GATE_AUTH = "oauth_rejected"
GATE_OPERATOR = "operator_approval_required"
GATE_STALE = "stale_state"
GATE_REPLAY = "approval_replayed"
GATE_EXPIRED = "approval_or_proposal_expired"
GATE_IDENTITY = "identity_mismatch"
GATE_DUPLICATE = "duplicate_in_flight"
GATE_AMBIGUOUS = "ambiguous_remote_write_no_retry"
GATE_READBACK = "readback_failed"
GATE_AUTH_UNRESOLVED = "fieldwork_api_auth_unresolved"
GATE_ARRIVAL_WINDOW = "arrival_window_unverified"

LEAD_STATUSES = frozenset({"lead", "leads"})


class UnknownFieldError(ValueError):
    def __init__(self, fields: list[str]) -> None:
        super().__init__(f"{GATE_UNKNOWN_FIELD}:{','.join(sorted(fields))}")
        self.fields = fields


def assert_only(payload: dict[str, Any], allowed: frozenset[str], *, label: str) -> None:
    extra = sorted(str(key) for key in payload if key not in allowed)
    if extra:
        raise UnknownFieldError(extra)


def require_op(operation: str) -> str:
    if operation in FORBIDDEN_OPS:
        raise ValueError(GATE_UNKNOWN_OP)
    if operation not in ALLOWED_OPS:
        raise ValueError(GATE_UNKNOWN_OP)
    return operation


def is_lead_status(customer: dict[str, Any] | None) -> bool:
    if not customer:
        return False
    status = str(customer.get("customer_status") or customer.get("status") or customer.get("type") or "").strip().lower()
    return status in LEAD_STATUSES


def current_gates(*, writes_enabled: bool, mapping_verified: bool) -> dict[str, Any]:
    return {
        "writes_enabled": bool(writes_enabled),
        "work_order_id_mapping_verified": bool(mapping_verified),
        "work_order_schema_verified": bool(mapping_verified),
        "arrival_window_verified": False,
        "fieldwork_api_auth_verified": False,
        "check_connection_is_not_auth_proof": True,
        "customer_create": False,
        "lead_status_accounts": False,
        "messaging_tools": False,
        "generic_http": False,
        "closed": [
            GATE_AUTH_UNRESOLVED,
            GATE_ARRIVAL_WINDOW,
            *( [] if writes_enabled else [GATE_WRITES_DISABLED] ),
            *( [] if mapping_verified else [GATE_MAPPING_UNVERIFIED, GATE_SCHEMA_UNVERIFIED] ),
        ],
    }
