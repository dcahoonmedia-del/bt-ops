"""Propose / independently approve / execute. Writes stay disabled by default."""

from __future__ import annotations

import hmac
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .allowlist import (
    GATE_ARRIVAL_WINDOW,
    GATE_AUTH,
    GATE_CREATE_RESPONSE,
    GATE_EXPIRED,
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
    OP_CREATE_CUSTOMER,
    OP_CREATE_WORK_ORDER,
    OP_LOCATION_NOTES,
    OP_WORK_ORDER_NOTES,
    OP_WORK_ORDER_SCHEDULE,
    SCHEDULE_WRITE_FIELDS,
    WORK_ORDER_NOTE_FIELDS,
    WORK_ORDER_SCHEDULE_FIELDS,
    UnknownFieldError,
    assert_only,
    current_gates,
    require_op,
)
from .approval import mint_operator_token, token_fingerprint, verify_operator_token
from .config import Settings
from .digest import canonical, proposal_digest, sha256_hex
from .errors import AmbiguousWriteError, GateError
from .fieldwork import TypedFieldworkClient, location_snapshot, snapshot_hash


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
            if operation == OP_CREATE_WORK_ORDER:
                return self._propose_create(payload, identity)
            if operation == OP_CREATE_CUSTOMER:
                return self._propose_customer(payload, identity)
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

    def _propose_create(self, payload: dict[str, Any], identity: dict[str, str]) -> dict[str, Any]:
        from .create_contract import work_order_request
        from .creation_flow import apply_catalog, load_catalog, route_staff, schedule_view

        caller = work_order_request(payload)
        self._require_active_location(payload)
        catalog = load_catalog(
            self.client,
            caller.get("template_id"),
            configured_template_id=self.settings.pestguard_initial_template_id,
            configured_service_id=self.settings.pestguard_initial_service_id,
        )
        applied = apply_catalog(caller["service_appointment"], catalog)
        documented = {"service_appointment": applied["service_appointment"]}
        occurrence = documented["service_appointment"]["appointment_occurrences_attributes"][0]
        starts = applied.get("starts") or {}
        staff = route_staff(self.client, list(occurrence["service_route_ids"]))
        schedule_at = str(applied.get("schedule_starts_at") or occurrence["starts_at"])
        schedule = schedule_view(self.client, schedule_at, list(occurrence["service_route_ids"]))
        template = catalog["template"]
        after = {
            "exists": False,
            "caller_appointment": caller["service_appointment"],
            "template_id": template.get("id"),
            "documented_request": documented,
            "association": {"customer_id": documented["service_appointment"]["customer_id"], "service_location_id": documented["service_appointment"]["service_location_id"]},
            "catalog": {"template_id": template.get("id"), "template_name": template.get("name"), "repeat_type": template.get("repeat_type"), "repeat_period": template.get("repeat_period"), "line": catalog["line"], "observed_line": catalog["observed_line"], "service": catalog["service"], "work_order_defaults": catalog["defaults"], "service_list_complete": catalog.get("service_list_complete"), "service_list_caveat": catalog.get("service_list_caveat")},
            "route_staff": staff,
            "schedule": schedule,
            "duration": occurrence.get("duration"),
            "instructions": occurrence.get("instructions"),
            "production_value": occurrence.get("production_value"),
            "line_total": applied.get("line_total"),
            "price": applied.get("price"),
            "standard_price": applied.get("standard_price"),
            "price_source": applied.get("price_source"),
            "service_pricing": {"name": catalog["line"].get("name"), "price": applied.get("price"), "standard_price": applied.get("standard_price"), "price_source": applied.get("price_source"), "quantity": catalog["line"].get("quantity"), "payable_id": catalog["line"].get("payable_id"), "payable_type": catalog["line"].get("payable_type"), "taxable": catalog["line"].get("taxable"), "total": applied.get("line_total"), "production_value": occurrence.get("production_value")},
            "auto_generates_invoice": catalog.get("auto_generates_invoice"),
            "invoice_generation_disclosed": catalog["invoice_generation_disclosed"],
            "invoice_generation_reason": catalog["invoice_generation_reason"],
            "billing_frequency_0_means_normal_invoice_generation": True,
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
            "initial_treatment_only": True,
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
        search = duplicate_search(self.client, payload)
        plan["duplicate_resolution"] = resolve_duplicates(search, confirmed_new=bool(plan.get("confirmed_new")), existing_customer_id=plan.get("existing_customer_id"))
        after = {
            "exists": False,
            "documented_request": plan,
            "duplicate_search": {"complete": True, "candidate_ids": plan["duplicate_resolution"]["candidate_ids"]},
            "contact_requested": plan.get("contact"),
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
        if proposal["operation"] in {OP_WORK_ORDER_NOTES, OP_WORK_ORDER_SCHEDULE} and not self.settings.mapping_verified:
            return self._fail(GATE_MAPPING_UNVERIFIED, proposal_id=proposal_id)
        if proposal["operation"] in {OP_WORK_ORDER_NOTES, OP_WORK_ORDER_SCHEDULE}:
            stale = self._work_order_stale(proposal)
        elif proposal["operation"] == OP_LOCATION_NOTES:
            stale = self._location_stale(proposal)
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
            return self._fail(result.get("gate") or GATE_PARTIAL, proposal_id=proposal["proposal_id"], **{key: result.get(key) for key in ("partial", "failed_step", "retry", "recovery")})
        self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "success")
        return {
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
        try:
            self.client.patch_location_notes(proposal["before"], str(payload["notes"]))
        except AmbiguousWriteError:
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "ambiguous")
            return self._fail("ambiguous_remote_write_no_retry", proposal_id=proposal["proposal_id"])
        except GateError as exc:
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "failed_no_write")
            return self._fail(exc.gate, proposal_id=proposal["proposal_id"], **exc.detail)
        except Exception:
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "ambiguous")
            return self._fail("ambiguous_remote_write_no_retry", proposal_id=proposal["proposal_id"])
        try:
            readback_customer = self.client.get_customer(customer_id)
            readback_location = self.client.get_location(customer_id, location_id)
            readback = location_snapshot(readback_customer, readback_location)
        except Exception:
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "ambiguous")
            return self._fail(GATE_READBACK, proposal_id=proposal["proposal_id"])
        if snapshot_hash(readback) != snapshot_hash(proposal["after"]):
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "ambiguous")
            return self._fail(GATE_READBACK, proposal_id=proposal["proposal_id"])
        self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "success")
        return {
            "ok": True,
            "proposal_id": proposal["proposal_id"],
            "operation": OP_LOCATION_NOTES,
            "readback": readback,
            "gates": self.gates(),
        }

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
