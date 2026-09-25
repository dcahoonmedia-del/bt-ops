"""Strict typed operations. Unknown names and extra fields fail closed."""

from __future__ import annotations

from typing import Any

OP_LOCATION_NOTES = "update_service_location_notes"
OP_WORK_ORDER_NOTES = "update_work_order_notes"
OP_WORK_ORDER_SCHEDULE = "update_work_order_schedule"
OP_CREATE_WORK_ORDER = "create_work_order"

ALLOWED_OPS = frozenset({OP_LOCATION_NOTES, OP_WORK_ORDER_NOTES, OP_WORK_ORDER_SCHEDULE, OP_CREATE_WORK_ORDER})

LOCATION_NOTE_FIELDS = frozenset({"customer_id", "location_id", "notes"})
WORK_ORDER_NOTE_FIELDS = frozenset({"work_order_id", "service_appointment_id", "instructions", "private_notes"})
WORK_ORDER_SCHEDULE_FIELDS = frozenset({"work_order_id", "service_appointment_id", "starts_at", "duration", "service_route_ids"})
NOTE_TEXT_FIELDS = ("instructions", "private_notes")
SCHEDULE_WRITE_FIELDS = ("starts_at", "duration", "service_route_ids")
ARRIVAL_FIELDS = ("arrival_time_window", "arrival_time_window_start", "arrival_time_window_end", "arrival_time_window_str")
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
GATE_LIVE_PATCH_UNTESTED = "live_patch_untested"
GATE_READONLY = "readonly_api_role"
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
GATE_RECURRING = "recurring_series_rejected"

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
    found: list[str] = []
    for key in ("status", "customer_status"):
        if key not in customer or customer[key] is None:
            continue
        text = str(customer[key]).strip().lower()
        if text:
            found.append(text)
    return len(set(found)) == 1 and found[0] in LEAD_STATUSES


def current_gates(
    *,
    writes_enabled: bool,
    mapping_verified: bool,
    api_role: str = "readonly",
    credential_ready: bool = False,
    oauth_ready: bool = False,
    auth_verified: bool = False,
    live_ready: bool = False,
    approval_mode: str = "operator",
    approval_supported: bool = False,
) -> dict[str, Any]:
    normalized = str(api_role or "readonly").strip().lower().replace("-", "_").replace(" ", "_")
    readonly = normalized != "writer"
    write_blocks = []
    if not writes_enabled:
        write_blocks.append(GATE_WRITES_DISABLED)
    if readonly:
        write_blocks.append(GATE_READONLY)
    work_order_blocks = list(write_blocks)
    if not mapping_verified:
        work_order_blocks.append(GATE_MAPPING_UNVERIFIED)
    return {
        "writes_enabled": bool(writes_enabled) and not readonly,
        "api_role": normalized,
        "auth_query_parameter": "api_key",
        "authorization_header_auth": False,
        "fieldwork_get_protocol_historically_verified": True,
        "credential_ready": bool(credential_ready),
        "oauth_ready": bool(oauth_ready),
        "fieldwork_get_auth_verified": bool(auth_verified),
        "fieldwork_api_auth_verified": bool(auth_verified),
        "live_ready": bool(live_ready),
        "approval_mode": approval_mode,
        "approval_mode_supported": bool(approval_supported),
        "check_connection_is_not_auth_proof": True,
        "work_order_get_id_pairs_verified": True,
        "work_order_id_mapping_verified": bool(mapping_verified),
        "live_patch_tested": False,
        "work_order_schema_verified": False,
        "arrival_window_read_known": True,
        "arrival_window_write_verified": False,
        "arrival_window_verified": False,
        "customer_create": False,
        "lead_status_accounts": False,
        "messaging_tools": False,
        "generic_http": False,
        "operations": {
            "update_service_location_notes": {"propose": True, "execute_blocked_by": list(write_blocks)},
            "update_work_order_notes": {"propose": bool(mapping_verified), "execute_role": "client.get_api_role", "execute_blocked_by": list(work_order_blocks), "fields": ["instructions", "private_notes"]},
            "update_work_order_schedule": {"propose": bool(mapping_verified), "single_occurrence": True, "execute_role": "client.get_api_role", "execute_blocked_by": list(work_order_blocks), "fields": ["starts_at", "duration", "service_route_ids"], "arrival_window_preserved": False, "arrival_coupling": "fixed_window_selected_by_start_when_occurrence_evidence_is_fresh", "explicit_arrival_window_edit": False},
            "create_work_order": {"propose": False, "execute_blocked_by": [GATE_SCHEMA_UNVERIFIED]},
            "schedule_or_arrival_window_write": {"propose": False, "execute_blocked_by": [GATE_ARRIVAL_WINDOW]},
            "list_users": {"read": True, "endpoint": "GET /v3.1/users", "projection": "staff_and_branch_fields", "stripe_pk": False},
            "list_service_locations": {"read": True, "endpoint": "GET /v3.1/customers/{customer_id}/service_locations", "customer_required": True, "global_endpoint": False},
            "list_schedule_filtered": {"read": True, "server_side_filtering": False, "local_filter": ["date", "status", "service_route_ids", "customer_id", "service_location_id"], "query_sent": ["start_date", "end_date", "current_technician", "sort_direction", "work_pool", "filter[status]", "filter[service_routes_ids][]"]},
        },
        "rollout_safeguard": "readonly_api_role" if readonly else "writer",
        "closed_contracts": [GATE_SCHEMA_UNVERIFIED, GATE_ARRIVAL_WINDOW],
    }
