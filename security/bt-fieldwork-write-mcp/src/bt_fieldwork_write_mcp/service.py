"""Propose / independently approve / execute. Writes stay disabled by default."""

from __future__ import annotations

import hmac
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .allowlist import (
    GATE_ARRIVAL_WINDOW,
    GATE_AUTH,
    GATE_CREATE_RESPONSE,
    GATE_EXPIRED,
    GATE_AMBIGUOUS,
    GATE_IDENTITY,
    GATE_MAPPING_UNVERIFIED,
    GATE_READONLY,
    GATE_RECURRING,
    GATE_OPERATOR,
    GATE_PARTIAL,
    GATE_READBACK,
    GATE_REPLAY,
    GATE_STALE,
    GATE_UNKNOWN_OP,
    GATE_WRITES_DISABLED,
    LOCATION_NOTE_FIELDS,
    ARRIVAL_FIELDS,
    NOTE_TEXT_FIELDS,
    CUSTOMER_EMAIL_FIELDS,
    GATE_STATUS_FAILED,
    GATE_WORK_POOL_API,
    GATE_WORK_POOL_PRECONDITION,
    OP_ADD_CUSTOMER_CONTACT,
    OP_CREATE_CUSTOMER,
    OP_CREATE_WORK_ORDER,
    OP_LOCATION_NOTES,
    OP_UPDATE_CUSTOMER_PRIMARY_EMAIL,
    OP_UPDATE_WORK_ORDER_STATUS,
    OP_WORK_ORDER_NOTES,
    OP_WORK_ORDER_SCHEDULE,
    OP_WORK_POOL_SCHEDULE,
    SCHEDULE_WRITE_FIELDS,
    WORK_POOL_PUBLIC_API_VERIFIED,
    WORK_POOL_REMAINING_CHECK,
    WORK_POOL_SCHEDULE_FIELDS,
    CUSTOMER_CONTACT_FIELDS,
    WORK_ORDER_NOTE_FIELDS,
    WORK_ORDER_SCHEDULE_FIELDS,
    WORK_ORDER_STATUS_FIELDS,
    UnknownFieldError,
    assert_only,
    current_gates,
    require_op,
)
from .approval import mint_operator_token, token_fingerprint, verify_operator_token
from .config import Settings
from .digest import canonical, proposal_digest, sha256_hex
from .errors import AmbiguousWriteError, GateError
from .fieldwork import TypedFieldworkClient, location_snapshot, resolve_work_order_status, snapshot_hash, work_pool_schedule_body


def _offset_iso(value: Any) -> bool:
    if not isinstance(value, str) or "T" not in value or value.endswith("Z"):
        return False
    tail = value[10:]
    if "+" not in tail and "-" not in tail:
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None
from .redact import redact
from .store import WriteStore


def _utc(now: datetime | None = None) -> datetime:
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    return clock.astimezone(timezone.utc)


def _iso(clock: datetime) -> str:
    return clock.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _work_order_steps(documented: dict[str, Any], starts: dict[str, Any], occurrence: dict[str, Any]) -> list[dict[str, Any]]:
    post = {"method": "POST", "path": "/work_orders", "body": documented, "clock_in_post_body": starts.get("kind") != "offset_timestamp"}
    if starts.get("kind") != "offset_timestamp":
        return [post]
    post["starts_at_in_post"] = starts.get("calendar_date")
    post["reason"] = "create_spec_types_starts_at_as_date"
    return [
        post,
        {
            "method": "PATCH",
            "path": "/work_orders/{service_appointment_id}",
            "occurrence_id": "{occurrence_id}",
            "starts_at": starts.get("starts_at"),
            "duration": occurrence.get("duration"),
            "service_route_ids": list(occurrence.get("service_route_ids") or []),
            "reason": "documented_schedule_patch_sets_the_approved_offset",
        },
    ]


def _normalized_start(value: Any) -> Any:
    if not value:
        return value
    from zoneinfo import ZoneInfo
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("offset_required")
        return parsed.astimezone(ZoneInfo("America/New_York")).isoformat()
    except ValueError:
        raise GateError("schedule_date_unverified") from None


class WriteService:
    def __init__(
        self,
        settings: Settings,
        store: WriteStore,
        client: TypedFieldworkClient,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.client = client
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._readiness: dict[str, Any] | None = None
        from .schedule import verified_window_evidence

        self.window_evidence = verified_window_evidence()

    def readiness(self, settings: Settings | None = None) -> dict[str, Any]:
        """One profile read and one auth snapshot. Later gates() calls reuse it."""
        settings = settings or self.settings
        role_error = None
        try:
            role = self.client.get_api_role()
        except Exception as exc:
            role, role_error = "unknown", getattr(exc, "gate", "read_rejected")
        normalized = str(role or "unknown").strip().lower().replace("-", "_").replace(" ", "_")
        credential_ready = bool(getattr(self.client, "api_key_present", lambda: False)())
        if settings.auth_mode == "auth0_bridge":
            from .auth0_bridge import bridge_blockers

            auth_configured = not bridge_blockers(settings)
        else:
            auth_configured = settings.oauth_ready()
        approval_supported = settings.approval_mode == "chatgpt_confirmation"
        auth_verified = role_error is None and normalized in {"writer", "readonly"}
        writer = auth_verified and normalized == "writer"
        live_ready = bool(credential_ready and auth_configured and writer and settings.writes_enabled and approval_supported)
        gates = current_gates(
            writes_enabled=settings.writes_enabled,
            mapping_verified=settings.mapping_verified,
            api_role=normalized,
            credential_ready=credential_ready,
            oauth_ready=auth_configured,
            auth_verified=auth_verified,
            live_ready=live_ready,
            approval_mode=settings.approval_mode if approval_supported else "unsupported",
            approval_supported=approval_supported,
        )
        body = {
            "ok": True,
            "reads_ready": auth_verified,
            "live_ready": live_ready,
            "fieldwork_api_auth_verified": auth_verified,
            "role_check_error": role_error,
            "credential_ready": credential_ready,
            "direct_jwt_configured": settings.auth_mode != "auth0_bridge" and settings.oauth_ready(),
            "auth0_bridge_configured": settings.auth_mode == "auth0_bridge" and auth_configured,
            "live_auth0_login_observed_by_this_process": bool(getattr(self, "authenticated_call_observed", False)),
            "offline_access_requested": settings.auth0_offline_access,
            "offline_access_required_on_access_token": False,
            "offline_access_observed_by_this_process": bool(getattr(self, "offline_access_observed", False)),
            "existing_downstream_sessions_remain_usable": True,
            "refresh_token_needs_one_new_authorization": not bool(getattr(self, "offline_access_observed", False)),
            "approval_mode": settings.approval_mode if approval_supported else "unsupported",
            "approval_mode_configured": settings.approval_mode,
            "approval_mode_supported": approval_supported,
            "live_patch_tested": False,
            "live_patch_tested_is_a_status_not_a_write_block": True,
            "gates": gates,
        }
        self._readiness = body
        return body

    def gates(self) -> dict[str, Any]:
        if self._readiness is None:
            return self.readiness()["gates"]
        return self._readiness["gates"]

    def _fail(self, gate: str, **detail: Any) -> dict[str, Any]:
        payload = {"ok": False, "gate": gate, "gates": self.gates()}
        payload.update(redact(detail))
        return payload

    def _identity_or_reject(self, identity: dict[str, str] | None) -> dict[str, str] | dict[str, Any]:
        if not identity or not identity.get("sub") or not identity.get("email"):
            return self._fail(GATE_AUTH)
        return {"sub": str(identity["sub"]), "email": str(identity["email"]).lower()}

    def propose(self, operation: str, payload: dict[str, Any], identity: dict[str, str] | None) -> dict[str, Any]:
        self.readiness()
        ident = self._identity_or_reject(identity)
        if "ok" in ident and ident.get("ok") is False:
            return ident
        identity = ident  # type: ignore[assignment]
        try:
            require_op(operation)
        except ValueError:
            return self._fail(GATE_UNKNOWN_OP, operation=operation)
        try:
            if operation == OP_LOCATION_NOTES:
                return self._propose_location_notes(payload, identity)
            if operation == OP_WORK_ORDER_NOTES:
                if not self.settings.mapping_verified:
                    return self._fail(GATE_MAPPING_UNVERIFIED, operation=operation)
                return self._propose_work_order_notes(payload, identity)
            if operation == OP_WORK_ORDER_SCHEDULE:
                if not self.settings.mapping_verified:
                    return self._fail(GATE_MAPPING_UNVERIFIED, operation=operation)
                return self._propose_work_order_schedule(payload, identity)
            if operation == OP_WORK_POOL_SCHEDULE:
                if not self.settings.mapping_verified:
                    return self._fail(GATE_MAPPING_UNVERIFIED, operation=operation)
                return self._propose_work_pool_schedule(payload, identity)
            if operation == OP_CREATE_WORK_ORDER:
                return self._propose_create(payload, identity)
            if operation == OP_CREATE_CUSTOMER:
                return self._propose_customer(payload, identity)
            if operation == OP_UPDATE_CUSTOMER_PRIMARY_EMAIL:
                return self._propose_customer_email(payload, identity)
            if operation == OP_UPDATE_WORK_ORDER_STATUS:
                if not self.settings.mapping_verified:
                    return self._fail(GATE_MAPPING_UNVERIFIED, operation=operation)
                return self._propose_work_order_status(payload, identity)
            if operation == OP_ADD_CUSTOMER_CONTACT:
                return self._propose_contact(payload, identity)
        except UnknownFieldError as exc:
            return self._fail(exc.args[0].split(":")[0], fields=exc.fields)
        except GateError as exc:
            return self._fail(exc.gate, **exc.detail)
        return self._fail(GATE_UNKNOWN_OP, operation=operation)

    def _propose_location_notes(self, payload: dict[str, Any], identity: dict[str, str]) -> dict[str, Any]:
        assert_only(payload, LOCATION_NOTE_FIELDS, label="location")
        customer_id = str(payload.get("customer_id") or "")
        location_id = str(payload.get("location_id") or "")
        notes = payload.get("notes")
        if not customer_id or not location_id or not isinstance(notes, str):
            return self._fail("unknown_field", fields=["customer_id", "location_id", "notes"])
        customer = self.client.get_customer(customer_id)
        location = self.client.get_location(customer_id, location_id)
        self.client.assert_location_identity(customer_id, location_id, customer, location)
        before = location_snapshot(customer, location)
        after = dict(before)
        after["notes"] = notes
        return self._persist_proposal(OP_LOCATION_NOTES, payload, identity, f"location:{customer_id}:{location_id}", before, after)

    def _live_api_role(self) -> str:
        getter = getattr(self.client, "get_api_role", None)
        if not callable(getter):
            return "readonly"
        try:
            role = getter()
        except Exception:
            return "readonly"
        return str(role or "readonly").strip().lower().replace("-", "_").replace(" ", "_")

    def _require_active_location(self, row: dict[str, Any]) -> dict[str, Any]:
        customer_id = str(row.get("customer_id") or "")
        location_id = str(row.get("service_location_id") or row.get("location_id") or "")
        if not customer_id.isdigit() or not location_id.isdigit():
            raise GateError("identity_mismatch")
        customer = self.client.get_customer(customer_id)
        self.client.reject_if_lead(customer)
        location = self.client.get_location(customer_id, location_id)
        self.client.assert_location_identity(customer_id, location_id, customer, location)
        return location_snapshot(customer, location)

    def _reject_series(self, row: dict[str, Any]) -> None:
        repeat = str(row.get("repeat_type") or "").strip().lower()
        if repeat and repeat not in {"none", "one_time"}:
            raise GateError(GATE_RECURRING)
        if row.get("series_id") or row.get("recurring") is True:
            raise GateError(GATE_RECURRING)
        series = row.get("appointment_occurrences")
        if isinstance(series, list) and len(series) > 1:
            raise GateError(GATE_RECURRING)

    def _occurrence_snapshot(self, row: dict[str, Any]) -> dict[str, Any]:
        identity = self._require_active_location(row)
        snap = {
            "work_order_id": row.get("id"),
            "service_appointment_id": row.get("service_appointment_id"),
            "customer_id": identity["customer_id"],
            "customer_status": identity["customer_status"],
            "location_id": identity["location_id"],
            "name": identity["name"],
            "tax_rate_id": identity["tax_rate_id"],
            "address_id": identity["address_id"],
            "instructions": row.get("instructions"),
            "private_notes": row.get("private_notes"),
            "starts_at": _normalized_start(row.get("starts_at")),
            "duration": row.get("duration"),
            "service_route_ids": [item for item in (row.get("service_route_ids") or [])],
        }
        for key in ARRIVAL_FIELDS:
            snap[key] = row.get(key)
        return snap

    def _propose_work_order_notes(self, payload: dict[str, Any], identity: dict[str, str]) -> dict[str, Any]:
        assert_only(payload, WORK_ORDER_NOTE_FIELDS, label="work_order")
        texts = [key for key in NOTE_TEXT_FIELDS if key in payload]
        if not texts or any(not isinstance(payload[key], str) for key in texts):
            return self._fail("unknown_field", fields=list(NOTE_TEXT_FIELDS))
        work_order_id = str(payload.get("work_order_id") or "")
        appointment_id = str(payload.get("service_appointment_id") or "")
        if not work_order_id.isdigit() or not appointment_id.isdigit():
            return self._fail("identity_mismatch")
        row = self.client.get_work_order(work_order_id)
        if str(row.get("id")) != work_order_id or str(row.get("service_appointment_id")) != appointment_id:
            return self._fail("identity_mismatch")
        self._reject_series(row)
        if "instructions" not in row or "private_notes" not in row:
            return self._fail("typed_read_incomplete", proposal=False, reason="instructions_or_private_notes_absent")
        before = self._occurrence_snapshot(row)
        after = dict(before)
        for key in texts:
            after[key] = payload[key]
        result = self._persist_proposal(OP_WORK_ORDER_NOTES, payload, identity, f"work_order:{work_order_id}", before, after)
        result["patch_fields"] = texts
        return result

    def _propose_work_order_schedule(self, payload: dict[str, Any], identity: dict[str, str]) -> dict[str, Any]:
        assert_only(payload, WORK_ORDER_SCHEDULE_FIELDS, label="schedule")
        if any(key in payload for key in ARRIVAL_FIELDS):
            return self._fail(GATE_ARRIVAL_WINDOW)
        starts_at = payload.get("starts_at")
        duration = payload.get("duration")
        routes = payload.get("service_route_ids")
        if not _offset_iso(starts_at) or isinstance(duration, bool) or not isinstance(duration, int) or duration <= 0:
            return self._fail("unknown_field", fields=["starts_at", "duration", "service_route_ids"])
        if not isinstance(routes, list) or not routes or any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in routes):
            return self._fail("unknown_field", fields=["service_route_ids"])
        work_order_id = str(payload.get("work_order_id") or "")
        appointment_id = str(payload.get("service_appointment_id") or "")
        if not work_order_id.isdigit() or not appointment_id.isdigit():
            return self._fail("identity_mismatch")
        row = self.client.get_work_order(work_order_id)
        if str(row.get("id")) != work_order_id or str(row.get("service_appointment_id")) != appointment_id:
            return self._fail("identity_mismatch")
        self._reject_series(row)
        before = self._occurrence_snapshot(row)
        before["service_route_ids"] = list(before.get("service_route_ids") or routes)
        from .schedule import SCHEDULE_MODEL, predict_fixed_shift

        after, reason = predict_fixed_shift(before, str(starts_at), duration, list(routes), self.window_evidence, _utc(self._now()))
        if after is None:
            return self._fail("schedule_coupling_unverified", reason=reason, explicit_arrival_window_edit=False)
        result = self._persist_proposal(OP_WORK_ORDER_SCHEDULE, payload, identity, f"work_order:{work_order_id}", before, after)
        result["patch_fields"] = list(SCHEDULE_WRITE_FIELDS)
        result["schedule_model"] = SCHEDULE_MODEL
        result["arrival_coupling"] = "fixed_window_selected_by_start"
        result["explicit_arrival_window_edit"] = False
        result["specific_sent"] = False
        result["fixed_window_id"] = after["fixed_window_id"]
        result["window_evidence_source"] = after["window_evidence_source"]
        result["occurrence_evidence_field"] = after["occurrence_evidence_field"]
        result["predicted_changes"] = {
            "starts_at": after["starts_at"],
            "ends_at": after["ends_at"],
            "duration": duration,
            "arrival_time_window": after["arrival_time_window"],
            "arrival_time_window_start": after["arrival_time_window_start"],
            "arrival_time_window_end": after["arrival_time_window_end"],
            "fixed_window_id": after["fixed_window_id"],
        }
        return result

    def _work_pool_snapshot(self, row: dict[str, Any]) -> dict[str, Any]:
        identity = self._require_active_location(row)
        lines = row.get("line_items")
        projected = None
        if isinstance(lines, list):
            projected = [
                {key: item.get(key) for key in ("name", "quantity", "price", "payable_id", "payable_type")}
                for item in lines
                if isinstance(item, dict)
            ]
        snap = {
            "work_order_id": str(row.get("id")),
            "service_appointment_id": str(row.get("service_appointment_id")),
            "customer_id": str(identity["customer_id"]),
            "location_id": str(identity["location_id"]),
            "instructions": row.get("instructions"),
            "private_notes": row.get("private_notes"),
            "production_value": row.get("production_value"),
            "confirmed": row.get("confirmed"),
            "specific": row.get("specific"),
            "status": row.get("status"),
            "starts_at": _normalized_start(row.get("starts_at")) if row.get("starts_at") else row.get("starts_at"),
            "duration": row.get("duration"),
            "service_route_ids": [item for item in (row.get("service_route_ids") or [])],
            "line_items": projected,
            "repeat_type_present": "repeat_type" in row,
            "repeat_type": row.get("repeat_type") if "repeat_type" in row else None,
            "time_window_kind_present": "time_window_kind" in row,
        }
        for key in ARRIVAL_FIELDS:
            snap[key] = row.get(key)
        return snap

    def _propose_work_pool_schedule(self, payload: dict[str, Any], identity: dict[str, str]) -> dict[str, Any]:
        assert_only(payload, WORK_POOL_SCHEDULE_FIELDS, label="work_pool_schedule")
        starts_at = payload.get("starts_at")
        duration = payload.get("duration")
        routes = payload.get("service_route_ids")
        if not _offset_iso(starts_at) or isinstance(duration, bool) or not isinstance(duration, int) or duration <= 0:
            return self._fail("unknown_field", fields=["starts_at", "duration", "service_route_ids"])
        if not isinstance(routes, list) or not routes or any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in routes):
            return self._fail("unknown_field", fields=["service_route_ids"])
        work_order_id = str(payload.get("work_order_id") or "")
        appointment_id = str(payload.get("service_appointment_id") or "")
        if not work_order_id.isdigit() or not appointment_id.isdigit() or work_order_id == appointment_id:
            return self._fail(GATE_IDENTITY)
        row = self.client.get_work_order(work_order_id)
        if str(row.get("id")) != work_order_id or str(row.get("service_appointment_id")) != appointment_id:
            return self._fail(GATE_IDENTITY)
        self._reject_series(row)
        if row.get("specific") is not False:
            return self._fail(GATE_WORK_POOL_PRECONDITION, reason="specific_not_false")
        if row.get("status") != "Work Pool":
            return self._fail(GATE_WORK_POOL_PRECONDITION, reason="status_not_work_pool")
        if row.get("confirmed") is not False:
            return self._fail(GATE_WORK_POOL_PRECONDITION, reason="confirmed_not_false")
        before = self._work_pool_snapshot(row)
        normalized = _normalized_start(starts_at)
        prepared = work_pool_schedule_body(
            appointment_id,
            work_order_id,
            normalized,
            duration,
            list(routes),
            specific=True,
        )
        after = {
            "intent": "work_pool_to_scheduled_time",
            "work_order_id": work_order_id,
            "service_appointment_id": appointment_id,
            "specific_before": False,
            "specific": True,
            "status_before": "Work Pool",
            "status_sent": False,
            "browser_observed_status_after": "Scheduled",
            "public_api_status_equivalence": "unverified",
            "arrival_mode": "not_inferred",
            "live_execution_available": False,
            "starts_at": normalized,
            "duration": duration,
            "service_route_ids": list(routes),
            "confirmed_sent": False,
            "notes_sent": False,
            "price_sent": False,
            "production_sent": False,
            "recurrence_sent": False,
            "series_update_sent": False,
            "communications_sent": False,
            "patch": prepared,
        }
        result = self._persist_proposal(OP_WORK_POOL_SCHEDULE, payload, identity, f"work_order:{work_order_id}", before, after)
        if result.get("ok"):
            result["intent"] = after["intent"]
            result["status_sent"] = False
            result["arrival_mode"] = "not_inferred"
            result["live_execution_available"] = False
            result["public_api_status_equivalence"] = "unverified"
            result["public_api_verified"] = WORK_POOL_PUBLIC_API_VERIFIED
            result["repeat_type_verified"] = before["repeat_type_present"]
        return result

    def _propose_create(self, payload: dict[str, Any], identity: dict[str, str]) -> dict[str, Any]:
        from .create_contract import work_order_request
        from .creation_flow import prepare_work_order, route_staff, schedule_view

        caller = work_order_request(payload)
        self._require_active_location(payload)
        prepared = prepare_work_order(
            self.client,
            caller["service_appointment"],
            caller.get("template_id"),
            configured_template_id=self.settings.pestguard_initial_template_id,
            configured_service_id=self.settings.pestguard_initial_service_id,
        )
        applied = prepared["applied"]
        catalog = prepared["catalog"]
        documented = {"service_appointment": applied["service_appointment"]}
        occurrence = documented["service_appointment"]["appointment_occurrences_attributes"][0]
        starts = applied.get("starts") or {}
        staff = route_staff(self.client, list(occurrence["service_route_ids"]))
        schedule_at = str(applied.get("schedule_starts_at") or occurrence["starts_at"])
        schedule = schedule_view(self.client, schedule_at, list(occurrence["service_route_ids"]))
        template = catalog.get("template") if isinstance(catalog.get("template"), dict) else {}
        template_consulted = bool(prepared["template_consulted"])
        sent_line = documented["service_appointment"]["line_items_attributes"][0]
        after = {
            "exists": False,
            "caller_appointment": caller["service_appointment"],
            "template_id": template.get("id") if template_consulted else None,
            "template_consulted": template_consulted,
            "documented_request": documented,
            "association": {"customer_id": documented["service_appointment"]["customer_id"], "service_location_id": documented["service_appointment"]["service_location_id"]},
            "catalog": {"template_id": template.get("id") if template_consulted else None, "template_name": template.get("name") if template_consulted else None, "template_consulted": template_consulted, "repeat_type": template.get("repeat_type") if template_consulted else documented["service_appointment"].get("repeat_type"), "repeat_period": template.get("repeat_period") if template_consulted else documented["service_appointment"].get("repeat_period"), "line": catalog["line"], "observed_line": catalog.get("observed_line"), "service": catalog.get("service"), "work_order_defaults": catalog.get("defaults") if template_consulted else None, "service_list_complete": catalog.get("service_list_complete"), "service_list_caveat": catalog.get("service_list_caveat")},
            "route_staff": staff,
            "schedule": schedule,
            "duration": occurrence.get("duration"),
            "instructions": occurrence.get("instructions"),
            "production_value": occurrence.get("production_value") if applied.get("production_sent") else None,
            "production_source": applied.get("production_source"),
            "production_sent": applied.get("production_sent"),
            "callback": occurrence.get("callback") if applied.get("callback_sent") else None,
            "callback_source": applied.get("callback_source"),
            "callback_sent": applied.get("callback_sent"),
            "duration_source": applied.get("duration_source"),
            "instructions_source": applied.get("instructions_source"),
            "service_record": applied.get("service_record"),
            "active_eligibility": applied.get("active_eligibility"),
            "active_flag_fabricated": False,
            "execution_blocked": bool(prepared["execution_blocked"]),
            "execution_block_reason": prepared.get("execution_block_reason"),
            "list_membership_proves_active": False,
            "selectability_source": prepared.get("selectability_source"),
            "catalog_membership": prepared.get("catalog_membership"),
            "work_order_selectability": prepared.get("work_order_selectability"),
            "catalog_equivalence": prepared.get("catalog_equivalence"),
            "universal_api_guarantee": prepared.get("universal_api_guarantee"),
            "eligibility_evidence": list(prepared["eligibility_evidence"]) if prepared.get("eligibility_evidence") else None,
            "missing_evidence": list(prepared["missing_evidence"]) if prepared.get("missing_evidence") else None,
            "line_total": applied.get("line_total"),
            "price": applied.get("price"),
            "standard_price": applied.get("standard_price"),
            "price_source": applied.get("price_source"),
            **({} if applied.get("price_resolution") is None else {"price_resolution": applied["price_resolution"]}),
            "service_pricing": {"name": sent_line.get("name"), "price": applied.get("price"), "standard_price": applied.get("standard_price"), "price_source": applied.get("price_source"), "quantity": sent_line.get("quantity"), "payable_id": sent_line.get("payable_id"), "payable_type": sent_line.get("payable_type"), "taxable": sent_line.get("taxable"), "total": applied.get("line_total"), "production_value": occurrence.get("production_value") if applied.get("production_sent") else None, "production_source": applied.get("production_source"), "callback": occurrence.get("callback") if applied.get("callback_sent") else None, "callback_source": applied.get("callback_source")},
            "auto_generates_invoice": catalog.get("auto_generates_invoice"),
            "invoice_generation_disclosed": catalog["invoice_generation_disclosed"],
            "invoice_generation_reason": catalog["invoice_generation_reason"],
            "billing_frequency_0_means_normal_invoice_generation": template_consulted,
            "starts_at_kind": starts.get("kind", "date"),
            "starts_at_instant": starts.get("instant"),
            "starts_at_timezone": starts.get("timezone"),
            "starts_at_post_ready": starts.get("post_ready", True),
            "starts_at_post_clock_live_tested": False,
            "timed_create_ready": False,
            "first_live_creation_approval_required": True,
            "starts_at_datetime_format_unverified": True,
            "post_clock_missing_proof": "Saved create spec types starts_at as date and gives no time example. GET evidence is not POST support. A fresh public create-page fetch returned HTTP 404, so no POST clock field was verified.",
            "use_time_window_sent": False,
            "promised_window_enforced": False,
            "arrival_window_post_verified": False,
            "response_schema_verified": False,
            "schema_ready": True,
            "timed_execution_blocked": False,
            "schedule_patch": None if starts.get("kind") != "offset_timestamp" else {"starts_at": starts.get("starts_at"), "duration": occurrence.get("duration"), "service_route_ids": list(occurrence.get("service_route_ids") or [])},
            "api_steps": _work_order_steps(documented, starts, occurrence),
            "live_tested": False,
            "initial_treatment_only": template_consulted,
            "recurrence": False,
            "agreement": False,
        }
        result = self._persist_proposal(
            OP_CREATE_WORK_ORDER,
            payload,
            identity,
            f"work_order:{payload.get('customer_id')}:{payload.get('service_location_id')}:{schedule_at}:{applied.get('price')}:{','.join(str(item) for item in occurrence.get('service_route_ids') or [])}",
            {"exists": False},
            after,
        )
        if result.get("ok"):
            result["starts_at_datetime_format_unverified"] = True
            result["response_schema_verified"] = False
            result["schema_ready"] = after["schema_ready"]
            result["timed_execution_blocked"] = after["timed_execution_blocked"]
            result["live_tested"] = False
            result["promised_window_enforced"] = False
        return result

    def _propose_customer(self, payload: dict[str, Any], identity: dict[str, str]) -> dict[str, Any]:
        from .create_contract import customer_request
        from .creation_flow import duplicate_search, names_for, phones_for, resolve_duplicates

        plan = customer_request(payload)
        from .creation_flow import bind_residential_location

        bind_residential_location(plan, self.client, self.settings.residential_location_type_id)
        search = duplicate_search(self.client, payload)
        plan["duplicate_resolution"] = resolve_duplicates(
            search,
            confirmed_new=bool(plan.get("confirmed_new")),
            existing_customer_id=plan.get("existing_customer_id"),
            acknowledgment=plan.get("acknowledge_duplicate_coverage"),
        )
        after = {
            "exists": False,
            "documented_request": plan,
            "duplicate_search": {
                "complete": search["complete"],
                "candidate_ids": plan["duplicate_resolution"]["candidate_ids"],
                "coverage_gap": search["coverage_gap"],
                "searched_fields": search["searched_fields"],
                "unsearched_fields": search["unsearched_fields"],
                "coverage_acknowledged": plan["duplicate_resolution"]["coverage_acknowledged"],
                "no_duplicate_claim": search["no_duplicate_claim"],
            },
            "contact_requested": plan.get("contact"),
            "contact_count": plan.get("contact_count", 0),
            "primary_email": plan.get("primary_email"),
            "invoice_email": plan.get("invoice_email"),
            "location_email": plan.get("location_email"),
            "billing_phone_kind": plan.get("billing_phone_kind"),
            "phone_kind_supplied": plan.get("phone_kind_supplied"),
            "billing_phone_kind_source": plan.get("billing_phone_kind_source"),
            "property_type": plan.get("property_type"),
            "location_type_id": plan.get("location_type_id"),
            "intended_display_name": plan.get("intended_display_name"),
            "residential_name": plan.get("residential_name"),
            "reminders_type": 0,
            "creation_time_reminders_experiment": bool(plan.get("creation_time_reminders_experiment")),
            "creation_time_reminders_display": plan.get("creation_time_reminders_display"),
            "reminders_readback": "unverified_ui_verification_required" if plan.get("creation_time_reminders_experiment") else "unverified_when_get_omits_field",
            "notification_effects": plan.get("notification_effects"),
            "nested_location_address_attributes": False,
            "response_schema_verified": False,
            "schema_ready": True,
            "live_tested": False,
        }
        subject = "customer:" + "|".join(sorted(names_for(payload))) + ":" + "|".join(sorted(phones_for(payload)))
        result = self._persist_proposal(OP_CREATE_CUSTOMER, payload, identity, subject, {"exists": False}, after)
        if result.get("ok"):
            result["response_schema_verified"] = False
            result["schema_ready"] = True
            result["live_tested"] = False
        return result

    def _location_email_disclosure(self, customer_id: str) -> list[dict[str, Any]]:
        try:
            listed = self.client.list_service_locations(customer_id)
        except GateError:
            return []
        shown = []
        for item in listed.get("items") or []:
            location_id = item.get("id")
            if location_id is None:
                continue
            try:
                location = self.client.get_location(customer_id, str(location_id))
            except GateError:
                continue
            shown.append(
                {
                    "location_id": location.get("id"),
                    "email": location.get("email"),
                    "same_as_billing_address": location.get("same_as_billing_address"),
                }
            )
        return shown

    def _propose_customer_email(self, payload: dict[str, Any], identity: dict[str, str]) -> dict[str, Any]:
        assert_only(payload, CUSTOMER_EMAIL_FIELDS, label="customer_email")
        customer_id = str(payload.get("customer_id") or "")
        email = payload.get("primary_email")
        if not customer_id.isdigit():
            return self._fail(GATE_IDENTITY)
        if not isinstance(email, str) or not email.strip():
            return self._fail("unknown_field", fields=["primary_email"])
        customer = self.client.get_customer(customer_id)
        self.client.reject_if_lead(customer)
        if str(customer.get("id")) != customer_id:
            return self._fail(GATE_IDENTITY)
        requested = email.strip()
        before = {"customer_id": customer.get("id"), "name": customer.get("name"), "invoice_email": customer.get("invoice_email")}
        after = {
            "customer_id": customer.get("id"),
            "name": customer.get("name"),
            "invoice_email": requested,
            "location_email_patch": "not_sent",
            "same_as_billing_location_email_propagation": "observed_once_not_proven_for_other_locations",
            "notice_delivery": "not_audited",
            "observed_location_emails": self._location_email_disclosure(customer_id),
        }
        result = self._persist_proposal(
            OP_UPDATE_CUSTOMER_PRIMARY_EMAIL,
            {"customer_id": int(customer_id), "primary_email": requested},
            identity,
            f"customer_invoice_email:{customer_id}",
            before,
            after,
        )
        if result.get("ok"):
            result["live_tested"] = False
            result["changed_fields"] = ["invoice_email"]
        return result

    def _customer_email_stale(self, proposal: dict[str, Any]) -> dict[str, Any] | None:
        customer_id = str(proposal["payload"]["customer_id"])
        try:
            customer = self.client.get_customer(customer_id)
            self.client.reject_if_lead(customer)
        except GateError as exc:
            return self._fail(exc.gate, proposal_id=proposal["proposal_id"], **exc.detail)
        if customer.get("invoice_email") != proposal["before"].get("invoice_email") or str(customer.get("id")) != customer_id:
            self.store.release_open_guard(proposal["subject_key"], proposal["proposal_id"])
            self.store.set_status(proposal["proposal_id"], "stale")
            return self._fail(GATE_STALE, proposal_id=proposal["proposal_id"])
        return None

    def _execute_customer_email(self, proposal: dict[str, Any], clock: datetime) -> dict[str, Any]:
        customer_id = str(proposal["payload"]["customer_id"])
        requested = str(proposal["after"]["invoice_email"])
        try:
            attempt_id = self.store.begin_attempt(proposal["proposal_id"], proposal["subject_key"], _iso(clock))
        except GateError as exc:
            return self._fail(exc.gate, proposal_id=proposal["proposal_id"], **exc.detail)
        stale = self._customer_email_stale(proposal)
        if stale is not None:
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "failed_no_write")
            return stale
        ambiguous = False
        try:
            self.client.patch_customer_invoice_email(customer_id, requested)
        except AmbiguousWriteError:
            ambiguous = True
        except GateError as exc:
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "failed_no_write")
            return self._fail(exc.gate, proposal_id=proposal["proposal_id"], retry=False, **exc.detail)
        except Exception:
            ambiguous = True
        try:
            customer = self.client.get_customer(customer_id)
        except Exception:
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "ambiguous")
            return self._fail("ambiguous_remote_write_no_retry", proposal_id=proposal["proposal_id"], retry=False)
        if customer.get("invoice_email") != requested or str(customer.get("id")) != customer_id:
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "ambiguous")
            gate = "ambiguous_remote_write_no_retry" if ambiguous else GATE_READBACK
            return self._fail(gate, proposal_id=proposal["proposal_id"], retry=False, customer_id=customer.get("id"), invoice_email=customer.get("invoice_email"))
        self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "success")
        body = {
            "ok": True,
            "proposal_id": proposal["proposal_id"],
            "operation": OP_UPDATE_CUSTOMER_PRIMARY_EMAIL,
            "live_tested": False,
            "readback": {
                "customer_id": customer.get("id"),
                "name": customer.get("name"),
                "invoice_email": customer.get("invoice_email"),
                "location_email_patch": "not_sent",
                "same_as_billing_location_email_propagation": "observed_once_not_proven_for_other_locations",
                "notice_delivery": "not_audited",
                "observed_location_emails": self._location_email_disclosure(customer_id),
            },
            "gates": self.gates(),
        }
        if ambiguous:
            body["ambiguity_reconciled"] = True
            body["retry"] = False
        return body

    def _propose_contact(self, payload: dict[str, Any], identity: dict[str, str]) -> dict[str, Any]:
        from .create_contract import _contact
        from .creation_flow import _normalize_contact_email, contact_preflight, customer_identity_snapshot

        assert_only(payload, CUSTOMER_CONTACT_FIELDS, label="contact")
        customer_id = str(payload.get("customer_id") or "")
        if not customer_id.isdigit():
            return self._fail(GATE_IDENTITY, persisted=False, write_sent=False)
        contact = _contact(payload.get("contact"))
        customer = self.client.get_customer(customer_id)
        self.client.reject_if_lead(customer)
        if str(customer.get("id")) != customer_id:
            return self._fail(GATE_IDENTITY, persisted=False, write_sent=False)
        try:
            preflight = contact_preflight(self.client, customer_id, contact)
        except GateError as exc:
            detail = {key: value for key, value in exc.detail.items() if key not in {"reason", "write_sent", "persisted"}}
            return self._fail(exc.gate, reason=exc.detail.get("reason") or exc.gate, persisted=False, write_sent=False, **detail)
        if preflight.get("blocked"):
            extra = {"candidates": preflight.get("candidates") or [], "merge": False, "persisted": False, "write_sent": False}
            if preflight.get("contact_id") is not None:
                extra["contact_id"] = preflight["contact_id"]
            return self._fail(preflight.get("gate") or "duplicate_unresolved", reason=preflight["reason"], **extra)
        bound = customer_identity_snapshot(customer)
        after = {
            "customer_id": customer_id,
            "contact": contact,
            "method": "POST",
            "path": f"/customers/{customer_id}/contacts",
            "portal_access": "not_sent",
            "notification_changes": "not_sent",
            "duplicate_preflight": "normalized_email_and_name",
            "live_tested": False,
        }
        return self._persist_proposal(
            OP_ADD_CUSTOMER_CONTACT,
            payload,
            identity,
            f"customer_contact:{customer_id}:{_normalize_contact_email(contact.get('email'))}",
            {"exists": False, **bound},
            after,
        )

    def _execute_contact(self, proposal: dict[str, Any], clock: datetime) -> dict[str, Any]:
        from .creation_flow import bind_standalone_customer, commit_contact, contact_preflight, verify_contact

        contact = proposal["after"]["contact"]
        customer_id = str(proposal["after"]["customer_id"])
        try:
            attempt_id = self.store.begin_attempt(proposal["proposal_id"], proposal["subject_key"], _iso(clock))
        except GateError as exc:
            return self._fail(exc.gate, proposal_id=proposal["proposal_id"], **exc.detail)
        try:
            bind_standalone_customer(self.client, customer_id, proposal.get("before") or {})
            preflight = contact_preflight(self.client, customer_id, contact)
        except GateError as exc:
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "failed_no_write")
            detail = {key: value for key, value in exc.detail.items() if key not in {"reason", "retry", "write_sent"}}
            return self._fail(exc.gate, proposal_id=proposal["proposal_id"], reason=exc.detail.get("reason") or exc.gate, retry=False, write_sent=False, **detail)
        if preflight.get("blocked"):
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "failed_no_write")
            extra = {"candidates": preflight.get("candidates") or [], "merge": False, "write_sent": False, "retry": False}
            if preflight.get("contact_id") is not None:
                extra["contact_id"] = preflight["contact_id"]
            return self._fail(preflight.get("gate") or "duplicate_unresolved", proposal_id=proposal["proposal_id"], reason=preflight["reason"], **extra)
        posted = commit_contact(self, proposal, attempt_id, customer_id, contact, location_id=None, reject_existing=True)
        if not posted.get("ok"):
            stopped = posted.get("stopped") or {}
            extra = {key: stopped.get(key) for key in ("partial", "failed_step", "retry", "recovery") if key in stopped}
            if posted.get("reason"):
                extra["reason"] = posted["reason"]
            return self._fail(stopped.get("gate") or posted.get("gate") or GATE_PARTIAL, proposal_id=proposal["proposal_id"], **extra)
        try:
            readback = verify_contact(self.client, customer_id, int(posted["contact_id"]), contact)
        except GateError as exc:
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "ambiguous")
            detail = {key: value for key, value in exc.detail.items() if key != "reason"}
            return self._fail(GATE_PARTIAL, proposal_id=proposal["proposal_id"], reason=exc.detail.get("reason") or exc.gate, retry=False, contact_id=posted.get("contact_id"), **detail)
        self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "success")
        return {
            "ok": True,
            "proposal_id": proposal["proposal_id"],
            "operation": OP_ADD_CUSTOMER_CONTACT,
            "created_id": posted["contact_id"],
            "reconciled": bool(posted.get("reconciled")),
            "readback": readback,
            "live_tested": False,
            "portal_access": "not_sent",
            "notification_changes": "not_sent",
            "gates": self.gates(),
        }

    def _propose_work_order_status(self, payload: dict[str, Any], identity: dict[str, str]) -> dict[str, Any]:
        assert_only(payload, WORK_ORDER_STATUS_FIELDS, label="work_order_status")
        work_order_id = str(payload.get("work_order_id") or "")
        appointment_id = str(payload.get("service_appointment_id") or "")
        status = payload.get("status")
        if not work_order_id.isdigit() or not appointment_id.isdigit():
            return self._fail(GATE_IDENTITY, persisted=False, write_sent=False)
        if not isinstance(status, str) or not status.strip():
            return self._fail("unknown_field", fields=["status"], persisted=False, write_sent=False)
        row = self.client.get_work_order(work_order_id)
        if str(row.get("id")) != work_order_id or str(row.get("service_appointment_id")) != appointment_id:
            return self._fail(GATE_IDENTITY, persisted=False, write_sent=False)
        self._reject_series(row)
        entry = resolve_work_order_status(self.client.list_work_order_statuses(), status)
        before = self._status_snapshot(row)
        requested = status.strip()
        readback_values = sorted({entry["write"], *entry["labels"], requested})
        after = {
            "status": requested,
            "status_write": entry["write"],
            "readback_values": readback_values,
            "only_change": "status",
            "other_fields": "not_sent",
        }
        result = self._persist_proposal(
            OP_UPDATE_WORK_ORDER_STATUS,
            payload,
            identity,
            f"work_order:{work_order_id}",
            before,
            after,
        )
        if result.get("ok"):
            result["changed_fields"] = ["status"]
            result["live_tested"] = False
            result["other_fields"] = "not_sent"
        return result

    def _status_snapshot(self, row: dict[str, Any]) -> dict[str, Any]:
        identity = self._require_active_location(row)
        customer = self.client.get_customer(str(identity["customer_id"]))
        location = self.client.get_location(str(identity["customer_id"]), str(identity["location_id"]))
        address = location.get("address") if isinstance(location.get("address"), dict) else {}
        route_ids = [item for item in (row.get("service_route_ids") or [])]
        route = [
            {"id": item.get("id"), "name": item.get("name")}
            for item in (row.get("service_routes") or [])
            if isinstance(item, dict)
        ]
        if not route:
            route = [{"id": item} for item in route_ids]
        lines = row.get("line_items")
        projected = None
        if isinstance(lines, list):
            projected = [
                {key: item.get(key) for key in ("name", "description", "quantity", "price", "payable_id", "payable_type")}
                for item in lines
                if isinstance(item, dict)
            ]
        snap = {
            "customer_name": customer.get("name"),
            "location": location.get("name"),
            "location_address": {key: address.get(key) for key in ("street", "street2", "city", "state", "zip")},
            "work_order_id": str(row.get("id")),
            "service_appointment_id": str(row.get("service_appointment_id")),
            "customer_id": str(identity["customer_id"]),
            "location_id": str(identity["location_id"]),
            "status": row.get("status"),
            "starts_at": row.get("starts_at"),
            "duration": row.get("duration"),
            "service_route_ids": route_ids,
            "route": route,
            "instructions": row.get("instructions"),
            "private_notes": row.get("private_notes"),
            "repeat_type": row.get("repeat_type"),
            "production_value": row.get("production_value"),
            "line_items": projected,
            "specific": row.get("specific"),
            "locked": row.get("locked"),
            "confirmed": row.get("confirmed"),
            "ends_at": row.get("ends_at"),
        }
        for key in ARRIVAL_FIELDS:
            snap[key] = row.get(key)
        return snap

    def _work_order_status_stale(self, proposal: dict[str, Any]) -> dict[str, Any] | None:
        before = proposal["before"]
        try:
            row = self.client.get_work_order(str(before["work_order_id"]))
            if str(row.get("service_appointment_id")) != str(before["service_appointment_id"]):
                return self._fail(GATE_IDENTITY, proposal_id=proposal["proposal_id"])
            self._reject_series(row)
            current = self._status_snapshot(row)
        except GateError as exc:
            return self._fail(exc.gate, proposal_id=proposal["proposal_id"], **exc.detail)
        if snapshot_hash(current) != snapshot_hash(before):
            self.store.release_open_guard(proposal["subject_key"], proposal["proposal_id"])
            self.store.set_status(proposal["proposal_id"], "stale")
            return self._fail(GATE_STALE, proposal_id=proposal["proposal_id"])
        return None

    def _status_readback_matches(self, proposal: dict[str, Any], live: dict[str, Any]) -> bool:
        before = dict(proposal["before"])
        current = dict(live)
        live_status = current.pop("status", None)
        before.pop("status", None)
        accepted = {str(item) for item in (proposal["after"].get("readback_values") or [])}
        return snapshot_hash(current) == snapshot_hash(before) and str(live_status) in accepted

    def _execute_work_order_status(self, proposal: dict[str, Any], clock: datetime) -> dict[str, Any]:
        try:
            attempt_id = self.store.begin_attempt(proposal["proposal_id"], proposal["subject_key"], _iso(clock))
        except GateError as exc:
            return self._fail(exc.gate, proposal_id=proposal["proposal_id"], **exc.detail)
        stale = self._work_order_status_stale(proposal)
        if stale is not None:
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "failed_no_write")
            return stale
        write_value = str(proposal["after"]["status_write"])
        ambiguous = False
        try:
            self.client.patch_work_order_status(
                proposal["before"]["service_appointment_id"],
                proposal["before"]["work_order_id"],
                write_value,
            )
        except AmbiguousWriteError:
            ambiguous = True
        except GateError as exc:
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "failed_no_write")
            return self._fail(exc.gate, proposal_id=proposal["proposal_id"], retry=False, **exc.detail)
        except Exception:
            ambiguous = True
        return self._finish_status_readback(proposal, attempt_id, ambiguous=ambiguous)

    def _finish_status_readback(self, proposal: dict[str, Any], attempt_id: str, *, ambiguous: bool) -> dict[str, Any]:
        """One GET, then at most two more when that read is unavailable or still the prior status. Never PATCH again."""
        last_status = None
        for attempt in range(3):
            if attempt:
                time.sleep(0.05)
            try:
                row = self.client.get_work_order(str(proposal["before"]["work_order_id"]))
            except Exception:
                continue
            if str(row.get("id")) != str(proposal["before"]["work_order_id"]) or str(row.get("service_appointment_id")) != str(proposal["before"]["service_appointment_id"]):
                return self._status_readback_unverified(proposal, attempt_id, status=row.get("status"), readback_attempts=attempt + 1, reason="identity_mismatch")
            try:
                live = self._status_snapshot(row)
            except GateError as exc:
                if exc.gate == GATE_IDENTITY:
                    return self._status_readback_unverified(proposal, attempt_id, readback_attempts=attempt + 1, reason="identity_mismatch")
                continue
            except Exception:
                continue
            last_status = live.get("status")
            if self._status_readback_matches(proposal, live):
                self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "success")
                body = {
                    "ok": True,
                    "proposal_id": proposal["proposal_id"],
                    "operation": OP_UPDATE_WORK_ORDER_STATUS,
                    "live_tested": False,
                    "changed_fields": ["status"],
                    "other_fields": "not_sent",
                    "readback_attempts": attempt + 1,
                    "readback": {
                        "work_order_id": live["work_order_id"],
                        "service_appointment_id": live["service_appointment_id"],
                        "status": live["status"],
                        "customer_name": live["customer_name"],
                        "location": live["location"],
                        "starts_at": live["starts_at"],
                        "route": live["route"],
                    },
                    "gates": self.gates(),
                }
                if ambiguous:
                    body["ambiguity_reconciled"] = True
                    body["retry"] = False
                return body
            if self._status_still_prior(proposal, live):
                continue
            return self._status_readback_unverified(proposal, attempt_id, status=live.get("status"), readback_attempts=attempt + 1, reason="protected_field_mismatch")
        return self._status_readback_unverified(proposal, attempt_id, status=last_status, readback_attempts=3, reason="readback_unverified")

    def _status_still_prior(self, proposal: dict[str, Any], live: dict[str, Any]) -> bool:
        before = dict(proposal["before"])
        current = dict(live)
        live_status = current.pop("status", None)
        prior = before.pop("status", None)
        return snapshot_hash(current) == snapshot_hash(before) and str(live_status) == str(prior)

    def _status_readback_unverified(
        self,
        proposal: dict[str, Any],
        attempt_id: str,
        *,
        status: Any = None,
        readback_attempts: int,
        reason: str,
    ) -> dict[str, Any]:
        self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "ambiguous")
        return self._fail(
            GATE_AMBIGUOUS,
            proposal_id=proposal["proposal_id"],
            retry=False,
            status=status,
            readback_attempts=readback_attempts,
            reason=reason,
        )

    def _persist_proposal(
        self,
        operation: str,
        payload: dict[str, Any],
        identity: dict[str, str],
        subject_key: str,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> dict[str, Any]:
        clock = _utc(self._now())
        proposal_id = str(uuid.uuid4())
        created_at = _iso(clock)
        expires_at = _iso(clock + timedelta(seconds=self.settings.proposal_ttl_seconds))
        digest = proposal_digest(
            proposal_id=proposal_id,
            operation=operation,
            identity=identity,
            target=subject_key,
            before=before,
            after=after,
            payload=payload,
            created_at=created_at,
            expires_at=expires_at,
        )
        record = {
            "proposal_id": proposal_id,
            "operation": operation,
            "identity_sub": identity["sub"],
            "identity_email": identity["email"],
            "subject_key": subject_key,
            "before": before,
            "after": after,
            "payload": payload,
            "digest": digest,
            "created_at": created_at,
            "expires_at": expires_at,
        }
        try:
            self.store.create_proposal(record)
        except GateError as exc:
            return self._fail(exc.gate, **exc.detail)
        return {
            "ok": True,
            "proposal_id": proposal_id,
            "digest": digest,
            "operation": operation,
            "before": before,
            "after": after,
            "expires_at": record["expires_at"],
            "immutable": True,
            "approved": False,
            "gates": self.gates(),
        }

    def mint_approval(self, proposal_id: str) -> dict[str, Any]:
        """Operator-side helper. Not an MCP tool. Never called from model-supplied approved=true."""
        proposal = self.store.get_proposal(proposal_id)
        if proposal is None:
            return self._fail("unknown_operation", proposal_id=proposal_id)
        clock = _utc(self._now())
        if _parse_iso(proposal["expires_at"]) <= clock:
            return self._fail(GATE_EXPIRED, proposal_id=proposal_id)
        if not self.settings.operator_key:
            return self._fail(GATE_OPERATOR, reason="operator_key_missing")
        expires_at = _iso(clock + timedelta(seconds=self.settings.approval_ttl_seconds))
        token = mint_operator_token(self.settings.operator_key, proposal_id, proposal["digest"], expires_at)
        self.store.record_approval(token_fingerprint(token), proposal_id, proposal["digest"], _iso(clock), expires_at)
        return {"ok": True, "proposal_id": proposal_id, "expires_at": expires_at, "operator_approval": token}

    def execute(
        self,
        proposal_id: str,
        identity: dict[str, str] | None,
        *,
        operator_approval: str = "",
        approved: Any = None,
        expected_digest: str = "",
    ) -> dict[str, Any]:
        snap = self.readiness()
        ident = self._identity_or_reject(identity)
        if "ok" in ident and ident.get("ok") is False:
            return ident
        identity = ident  # type: ignore[assignment]
        if not self.settings.writes_enabled:
            return self._fail(GATE_WRITES_DISABLED, proposal_id=proposal_id)
        if snap.get("role_check_error"):
            return self._fail(str(snap["role_check_error"]), proposal_id=proposal_id)
        if snap["gates"]["api_role"] != "writer":
            return self._fail(GATE_READONLY, proposal_id=proposal_id)
        proposal = self.store.get_proposal(proposal_id)
        if proposal is None:
            return self._fail("unknown_operation", proposal_id=proposal_id)
        rebound = self._bound_digest(proposal)
        if not hmac.compare_digest(rebound, str(proposal["digest"])):
            return self._fail(GATE_OPERATOR, proposal_id=proposal_id, reason="stored_proposal_digest_mismatch")
        clock = _utc(self._now())
        if proposal["identity"] != identity:
            return self._fail(GATE_IDENTITY, proposal_id=proposal_id)
        if _parse_iso(proposal["expires_at"]) <= clock:
            self.store.release_open_guard(proposal["subject_key"], proposal_id)
            self.store.set_status(proposal_id, "expired")
            return self._fail(GATE_EXPIRED, proposal_id=proposal_id)
        if proposal["status"] == "ambiguous":
            extra = self._creation_partial(proposal) if proposal["operation"] in {OP_CREATE_CUSTOMER, OP_CREATE_WORK_ORDER} else {}
            return self._fail("ambiguous_remote_write_no_retry", proposal_id=proposal_id, retry=False, **extra)
        if proposal["status"] == "executed":
            return self._fail(GATE_REPLAY, proposal_id=proposal_id)
        if self.store.has_ambiguous(proposal["subject_key"]):
            return self._fail("ambiguous_remote_write_no_retry", proposal_id=proposal_id)
        if proposal["operation"] in {OP_WORK_ORDER_NOTES, OP_WORK_ORDER_SCHEDULE, OP_UPDATE_WORK_ORDER_STATUS, OP_WORK_POOL_SCHEDULE} and not self.settings.mapping_verified:
            return self._fail(GATE_MAPPING_UNVERIFIED, proposal_id=proposal_id)
        if proposal["operation"] in {OP_WORK_ORDER_NOTES, OP_WORK_ORDER_SCHEDULE}:
            stale = self._work_order_stale(proposal)
        elif proposal["operation"] == OP_WORK_POOL_SCHEDULE:
            stale = self._work_pool_stale(proposal)
        elif proposal["operation"] == OP_UPDATE_WORK_ORDER_STATUS:
            stale = self._work_order_status_stale(proposal)
        elif proposal["operation"] == OP_LOCATION_NOTES:
            stale = self._location_stale(proposal)
        elif proposal["operation"] == OP_UPDATE_CUSTOMER_PRIMARY_EMAIL:
            stale = self._customer_email_stale(proposal)
        else:
            stale = None
        if stale is not None:
            return stale
        if self.settings.approval_mode == "chatgpt_confirmation":
            # A caller-supplied operator_approval string is not proof in this mode.
            del operator_approval
            if approved is not True or not expected_digest or not hmac.compare_digest(str(expected_digest), rebound):
                return self._fail(GATE_OPERATOR, proposal_id=proposal_id, reason="explicit_confirmation_and_exact_digest_required")
            self._record_chatgpt_confirmation(proposal, rebound, clock)
        elif not self._accept_operator(proposal, operator_approval, clock):
            return self._fail(self._operator_gate(operator_approval, proposal, clock), proposal_id=proposal_id)

        if proposal["operation"] == OP_LOCATION_NOTES:
            return self._execute_location_notes(proposal, clock)
        if proposal["operation"] == OP_WORK_ORDER_NOTES:
            return self._execute_work_order(proposal, clock, [key for key in NOTE_TEXT_FIELDS if key in proposal["payload"]])
        if proposal["operation"] == OP_WORK_ORDER_SCHEDULE:
            return self._execute_work_order(proposal, clock, list(SCHEDULE_WRITE_FIELDS))
        if proposal["operation"] == OP_WORK_POOL_SCHEDULE:
            return self._refuse_work_pool_live_execution(proposal)
        if proposal["operation"] == OP_UPDATE_CUSTOMER_PRIMARY_EMAIL:
            return self._execute_customer_email(proposal, clock)
        if proposal["operation"] == OP_UPDATE_WORK_ORDER_STATUS:
            return self._execute_work_order_status(proposal, clock)
        if proposal["operation"] == OP_ADD_CUSTOMER_CONTACT:
            return self._execute_contact(proposal, clock)
        if proposal["operation"] in {OP_CREATE_WORK_ORDER, OP_CREATE_CUSTOMER}:
            return self._execute_create(proposal, clock)
        return self._fail(GATE_UNKNOWN_OP, proposal_id=proposal_id)

    def _bound_digest(self, proposal: dict[str, Any]) -> str:
        return proposal_digest(
            proposal_id=proposal["proposal_id"],
            operation=proposal["operation"],
            identity=proposal["identity"],
            target=proposal["subject_key"],
            before=proposal["before"],
            after=proposal["after"],
            payload=proposal["payload"],
            created_at=proposal["created_at"],
            expires_at=proposal["expires_at"],
        )

    def _record_chatgpt_confirmation(self, proposal: dict[str, Any], digest: str, clock: datetime) -> None:
        fingerprint = token_fingerprint(f"chatgpt:{proposal['proposal_id']}:{digest}")
        existing = self.store.get_approval(fingerprint)
        if existing is None:
            self.store.record_approval(fingerprint, proposal["proposal_id"], digest, _iso(clock), proposal["expires_at"])
        self.store.mark_approval_used(fingerprint, _iso(clock))

    def _operator_gate(self, token: str, proposal: dict[str, Any], clock: datetime) -> str:
        if not token:
            return GATE_OPERATOR
        fingerprint = token_fingerprint(token)
        existing = self.store.get_approval(fingerprint)
        if existing is None:
            # token may be freshly minted offline with embedded exp in verify path
            return GATE_OPERATOR
        if existing["proposal_id"] != proposal["proposal_id"] or existing["digest"] != proposal["digest"]:
            return GATE_OPERATOR
        if existing["used_at"]:
            return GATE_REPLAY
        if _parse_iso(existing["expires_at"]) <= clock:
            return GATE_EXPIRED
        return GATE_OPERATOR

    def _accept_operator(self, proposal: dict[str, Any], token: str, clock: datetime) -> bool:
        if not token or not self.settings.operator_key:
            return False
        fingerprint = token_fingerprint(token)
        existing = self.store.get_approval(fingerprint)
        if existing is None:
            return False
        if existing["used_at"]:
            return False
        if existing["proposal_id"] != proposal["proposal_id"] or existing["digest"] != proposal["digest"]:
            return False
        if _parse_iso(existing["expires_at"]) <= clock:
            return False
        if not verify_operator_token(
            self.settings.operator_key, token, proposal["proposal_id"], proposal["digest"], existing["expires_at"]
        ):
            return False
        return self.store.mark_approval_used(fingerprint, _iso(clock))

    def _location_stale(self, proposal: dict[str, Any]) -> dict[str, Any] | None:
        payload = proposal["payload"]
        try:
            customer = self.client.get_customer(str(payload["customer_id"]))
            self.client.reject_if_lead(customer)
            location = self.client.get_location(str(payload["customer_id"]), str(payload["location_id"]))
            self.client.assert_location_identity(str(payload["customer_id"]), str(payload["location_id"]), customer, location)
        except GateError as exc:
            return self._fail(exc.gate, proposal_id=proposal["proposal_id"], **exc.detail)
        current = location_snapshot(customer, location)
        if snapshot_hash(current) != snapshot_hash(proposal["before"]):
            self.store.release_open_guard(proposal["subject_key"], proposal["proposal_id"])
            self.store.set_status(proposal["proposal_id"], "stale")
            return self._fail(GATE_STALE, proposal_id=proposal["proposal_id"])
        return None

    def _creation_partial(self, proposal: dict[str, Any]) -> dict[str, Any]:
        from .creation_flow import journal_partial

        partial = journal_partial(self.store.creation_journal(proposal["proposal_id"]))
        return {"partial": partial, "failed_step": partial.get("failed_step"), "recovery": "new_exact_approved_proposal"}

    def _execute_create(self, proposal: dict[str, Any], clock: datetime) -> dict[str, Any]:
        from .creation_flow import post_customer_steps, post_work_order, stop_creation

        if any(row["outcome"] in {"intended", "ambiguous"} for row in self.store.creation_journal(proposal["proposal_id"])):
            self.store.set_status(proposal["proposal_id"], "ambiguous")
            return self._fail("ambiguous_remote_write_no_retry", proposal_id=proposal["proposal_id"], retry=False, **self._creation_partial(proposal))
        try:
            attempt_id = self.store.begin_attempt(proposal["proposal_id"], proposal["subject_key"], _iso(clock))
        except GateError as exc:
            return self._fail(exc.gate, proposal_id=proposal["proposal_id"], **exc.detail)
        try:
            if proposal["operation"] == OP_CREATE_CUSTOMER:
                result = post_customer_steps(self, proposal, attempt_id)
            else:
                result = post_work_order(self, proposal, attempt_id)
        except AmbiguousWriteError:
            stopped = stop_creation(self.store, proposal, attempt_id)
            return self._fail(stopped["gate"], proposal_id=proposal["proposal_id"], **{key: stopped[key] for key in ("partial", "failed_step", "retry", "recovery")})
        except GateError as exc:
            if any(row["outcome"] == "succeeded" for row in self.store.creation_journal(proposal["proposal_id"])):
                step_id = self.store.begin_creation_step(proposal["proposal_id"], "readback", {"gate": exc.gate})
                self.store.finish_creation_step(step_id, "failed", {"gate": exc.gate})
                stopped = stop_creation(self.store, proposal, attempt_id)
                return self._fail(GATE_PARTIAL, proposal_id=proposal["proposal_id"], reason=exc.gate, **{key: stopped[key] for key in ("partial", "failed_step", "retry", "recovery")})
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "failed_no_write")
            return self._fail(exc.gate, proposal_id=proposal["proposal_id"], **exc.detail)
        except Exception:
            stopped = stop_creation(self.store, proposal, attempt_id)
            return self._fail(stopped["gate"], proposal_id=proposal["proposal_id"], retry=False, **{key: stopped[key] for key in ("partial", "failed_step", "recovery")})
        if not result.get("ok"):
            extra = {key: result.get(key) for key in ("partial", "failed_step", "retry", "recovery")}
            if result.get("reason"):
                extra["reason"] = result["reason"]
            return self._fail(result.get("gate") or GATE_PARTIAL, proposal_id=proposal["proposal_id"], **extra)
        self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "success")
        body = {
            "ok": True,
            "proposal_id": proposal["proposal_id"],
            "operation": proposal["operation"],
            "created_id": result.get("created_id"),
            "reconciled": bool(result.get("reconciled")),
            "readback": result.get("readback"),
            "schema_ready": True,
            "live_tested": False,
            "gates": self.gates(),
        }
        if result.get("readback_attempts"):
            body["readback_attempts"] = result["readback_attempts"]
        return body

    def _execute_location_notes(self, proposal: dict[str, Any], clock: datetime) -> dict[str, Any]:
        payload = proposal["payload"]
        customer_id = str(payload["customer_id"])
        location_id = str(payload["location_id"])
        try:
            attempt_id = self.store.begin_attempt(proposal["proposal_id"], proposal["subject_key"], _iso(clock))
        except GateError as exc:
            return self._fail(exc.gate, proposal_id=proposal["proposal_id"], **exc.detail)
        stale = self._location_stale(proposal)
        if stale is not None:
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "failed_no_write")
            return stale
        ambiguous = False
        try:
            self.client.patch_location_notes(proposal["before"], str(payload["notes"]))
        except AmbiguousWriteError:
            ambiguous = True
        except GateError as exc:
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "failed_no_write")
            return self._fail(exc.gate, proposal_id=proposal["proposal_id"], retry=False, **exc.detail)
        except Exception:
            ambiguous = True
        return self._finish_location_notes(proposal, attempt_id, customer_id, location_id, ambiguous=ambiguous)

    def _finish_location_notes(self, proposal: dict[str, Any], attempt_id: str, customer_id: str, location_id: str, *, ambiguous: bool) -> dict[str, Any]:
        try:
            readback_customer = self.client.get_customer(customer_id)
            readback_location = self.client.get_location(customer_id, location_id)
            readback = location_snapshot(readback_customer, readback_location)
        except Exception:
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "ambiguous")
            gate = "ambiguous_remote_write_no_retry" if ambiguous else GATE_READBACK
            return self._fail(gate, proposal_id=proposal["proposal_id"], retry=False)
        if snapshot_hash(readback) != snapshot_hash(proposal["after"]):
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "ambiguous")
            gate = "ambiguous_remote_write_no_retry" if ambiguous else GATE_READBACK
            return self._fail(gate, proposal_id=proposal["proposal_id"], retry=False, readback=readback)
        self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "success")
        body = {
            "ok": True,
            "proposal_id": proposal["proposal_id"],
            "operation": OP_LOCATION_NOTES,
            "readback": readback,
            "gates": self.gates(),
        }
        if ambiguous:
            body["ambiguity_reconciled"] = True
            body["retry"] = False
        return body

    def _work_pool_stale(self, proposal: dict[str, Any]) -> dict[str, Any] | None:
        before = proposal["before"]
        try:
            row = self.client.get_work_order(str(before["work_order_id"]))
            if str(row.get("id")) != str(before["work_order_id"]) or str(row.get("service_appointment_id")) != str(before["service_appointment_id"]):
                return self._fail(GATE_IDENTITY, proposal_id=proposal["proposal_id"], write_sent=False)
            if str(row.get("customer_id")) != str(before["customer_id"]) or str(row.get("service_location_id") or row.get("location_id")) != str(before["location_id"]):
                return self._fail(GATE_IDENTITY, proposal_id=proposal["proposal_id"], write_sent=False)
            self._reject_series(row)
            current = self._work_pool_snapshot(row)
        except GateError as exc:
            return self._fail(exc.gate, proposal_id=proposal["proposal_id"], write_sent=False, **exc.detail)
        if snapshot_hash(current) != snapshot_hash(before):
            self.store.release_open_guard(proposal["subject_key"], proposal["proposal_id"])
            self.store.set_status(proposal["proposal_id"], "stale")
            changed = [key for key in before if current.get(key) != before.get(key)]
            return self._fail(GATE_STALE, proposal_id=proposal["proposal_id"], write_sent=False, changed_fields=changed)
        return None

    def _refuse_work_pool_live_execution(self, proposal: dict[str, Any]) -> dict[str, Any]:
        """Approval is already consumed. The public PATCH contract is still unverified, so nothing is sent."""
        if WORK_POOL_PUBLIC_API_VERIFIED or proposal["after"].get("live_execution_available") is True:
            return self._fail(GATE_WORK_POOL_API, proposal_id=proposal["proposal_id"], retry=False, write_sent=False, reason="verified_flag_without_send_path")
        return self._fail(
            GATE_WORK_POOL_API,
            proposal_id=proposal["proposal_id"],
            retry=False,
            write_sent=False,
            live_execution_available=False,
            remaining_check=WORK_POOL_REMAINING_CHECK,
        )

    def _work_order_stale(self, proposal: dict[str, Any]) -> dict[str, Any] | None:
        before = proposal["before"]
        try:
            row = self.client.get_work_order(str(before["work_order_id"]))
            self._reject_series(row)
            current = self._occurrence_snapshot(row)
        except GateError as exc:
            return self._fail(exc.gate, proposal_id=proposal["proposal_id"], **exc.detail)
        if snapshot_hash(current) != snapshot_hash(before):
            self.store.release_open_guard(proposal["subject_key"], proposal["proposal_id"])
            self.store.set_status(proposal["proposal_id"], "stale")
            return self._fail(GATE_STALE, proposal_id=proposal["proposal_id"])
        return None

    def _execute_work_order(self, proposal: dict[str, Any], clock: datetime, fields: list[str]) -> dict[str, Any]:
        try:
            attempt_id = self.store.begin_attempt(proposal["proposal_id"], proposal["subject_key"], _iso(clock))
        except GateError as exc:
            return self._fail(exc.gate, proposal_id=proposal["proposal_id"], **exc.detail)
        stale = self._work_order_stale(proposal)
        if stale is not None:
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "failed_no_write")
            return stale
        ambiguous_response = False
        try:
            self.client.patch_work_order_fields(proposal["before"], proposal["after"], fields)
        except AmbiguousWriteError:
            ambiguous_response = True
        except GateError as exc:
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "failed_no_write")
            return self._fail(exc.gate, proposal_id=proposal["proposal_id"], **exc.detail)
        except Exception:
            ambiguous_response = True
        if ambiguous_response:
            return self._reconcile_after_ambiguous_patch(proposal, attempt_id, fields)
        return self._verify_work_order_readback(proposal, attempt_id, fields, ambiguous_response=False)

    def _expected_schedule(self, proposal: dict[str, Any]) -> dict[str, Any] | None:
        from .schedule import SCHEDULE_MODEL, predict_fixed_shift

        if proposal["operation"] != OP_WORK_ORDER_SCHEDULE:
            return proposal["after"]
        if proposal["after"].get("schedule_model") == SCHEDULE_MODEL:
            return proposal["after"]
        payload = proposal["payload"]
        predicted, self._schedule_reason = predict_fixed_shift(
            proposal["before"],
            str(payload.get("starts_at")),
            int(payload.get("duration")),
            list(payload.get("service_route_ids") or []),
            self.window_evidence,
            _utc(self._now()),
        )
        if predicted is None:
            return None
        predicted["legacy_stored_after_not_authoritative"] = True
        return predicted

    def _verify_work_order_readback(self, proposal: dict[str, Any], attempt_id: str, fields: list[str], *, ambiguous_response: bool) -> dict[str, Any]:
        try:
            row = self.client.get_work_order(str(proposal["before"]["work_order_id"]))
            readback = self._occurrence_snapshot(row)
            if proposal["operation"] == OP_WORK_ORDER_SCHEDULE:
                readback["ends_at"] = row.get("ends_at")
                readback["finished_at"] = row.get("finished_at")
        except Exception:
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "ambiguous")
            return self._fail("readback_unresolved", proposal_id=proposal["proposal_id"], retry=False, readback=None)
        if proposal["operation"] == OP_WORK_ORDER_SCHEDULE:
            from .schedule import compare_schedule

            expected = self._expected_schedule(proposal)
            if expected is None:
                self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "ambiguous")
                return self._fail("schedule_coupling_unverified", proposal_id=proposal["proposal_id"], retry=False, reason=getattr(self, "_schedule_reason", "arrival_window_mode_unverified"))
            mismatches = compare_schedule(expected, readback, proposal["before"])
            if mismatches:
                self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "ambiguous")
                return self._fail("readback_unresolved", proposal_id=proposal["proposal_id"], retry=False, mismatches=mismatches, readback=readback)
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "success")
            body = {"ok": True, "proposal_id": proposal["proposal_id"], "operation": proposal["operation"], "readback": readback, "patch_fields": fields, "gates": self.gates()}
            if ambiguous_response:
                body["ambiguity_reconciled"] = True
                body["reconciliation"] = expected.get("evidence")
                body["general_rule"] = False
            return body
        if snapshot_hash(readback) != snapshot_hash(proposal["after"]):
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "ambiguous")
            return self._fail(GATE_READBACK, proposal_id=proposal["proposal_id"])
        self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "success")
        return {"ok": True, "proposal_id": proposal["proposal_id"], "operation": proposal["operation"], "readback": readback, "patch_fields": fields, "gates": self.gates()}

    def _reconcile_after_ambiguous_patch(self, proposal: dict[str, Any], attempt_id: str, fields: list[str]) -> dict[str, Any]:
        return self._verify_work_order_readback(proposal, attempt_id, fields, ambiguous_response=True)

    def reconcile_ambiguous(self, proposal_id: str, identity: dict[str, str] | None) -> dict[str, Any]:
        """Read the live occurrence for an ambiguous write. Does not PATCH or edit the stored payload."""
        self.readiness()
        ident = self._identity_or_reject(identity)
        if "ok" in ident and ident.get("ok") is False:
            return ident
        proposal = self.store.get_proposal(proposal_id)
        if proposal is None:
            return self._fail("unknown_operation", proposal_id=proposal_id)
        if proposal["identity"] != ident:
            return self._fail(GATE_IDENTITY, proposal_id=proposal_id)
        if proposal["status"] != "ambiguous":
            return self._fail("not_ambiguous", proposal_id=proposal_id)
        before_payload = dict(proposal["payload"])
        before_digest = proposal["digest"]
        before_after = dict(proposal["after"])
        try:
            row = self.client.get_work_order(str(proposal["before"]["work_order_id"]))
            readback = self._occurrence_snapshot(row)
            readback["ends_at"] = row.get("ends_at")
            readback["finished_at"] = row.get("finished_at")
        except Exception:
            self.store.append_audit(proposal_id, "reconcile_get_failed", {"retry": False})
            return self._fail("readback_unresolved", proposal_id=proposal_id, retry=False)
        from .schedule import compare_schedule

        expected = self._expected_schedule(proposal)
        if expected is None:
            reason = getattr(self, "_schedule_reason", "arrival_window_mode_unverified")
            self.store.append_audit(proposal_id, "reconcile_unsupported", {"retry": False, "reason": reason})
            return self._fail("schedule_coupling_unverified", proposal_id=proposal_id, retry=False, reason=reason)
        mismatches = compare_schedule(expected, readback, proposal["before"])
        stored = self.store.get_proposal(proposal_id)
        if stored["payload"] != before_payload or stored["digest"] != before_digest or stored["after"] != before_after:
            return self._fail("immutable_proposal_changed", proposal_id=proposal_id)
        if mismatches:
            self.store.append_audit(proposal_id, "reconcile_mismatch", {"mismatches": mismatches, "retry": False})
            return self._fail("readback_unresolved", proposal_id=proposal_id, retry=False, mismatches=mismatches, readback=readback)
        self.store.append_audit(proposal_id, "reconcile_verified", {"schedule_model": expected.get("schedule_model"), "legacy_stored_after_not_authoritative": expected.get("legacy_stored_after_not_authoritative", False)})
        self.store.set_status(proposal_id, "executed")
        self.store.release_ambiguous_guard(proposal["subject_key"], proposal_id)
        unchanged = self.store.get_proposal(proposal_id)
        return {
            "ok": True,
            "proposal_id": proposal_id,
            "status": unchanged["status"],
            "readback": readback,
            "patched": False,
            "immutable_payload_unchanged": unchanged["payload"] == before_payload and unchanged["digest"] == before_digest and unchanged["after"] == before_after,
            "legacy_stored_after_not_authoritative": expected.get("legacy_stored_after_not_authoritative", False),
            "evidence": expected.get("evidence"),
            "general_rule": False,
        }

    def inspect(self, proposal_id: str, identity: dict[str, str] | None) -> dict[str, Any]:
        self.readiness()
        ident = self._identity_or_reject(identity)
        if "ok" in ident and ident.get("ok") is False:
            return ident
        proposal = self.store.get_proposal(proposal_id)
        if proposal is None:
            return self._fail("unknown_operation", proposal_id=proposal_id)
        if proposal["identity"] != ident:
            return self._fail(GATE_IDENTITY, proposal_id=proposal_id)
        return {"ok": True, **redact(proposal), "gates": self.gates()}
