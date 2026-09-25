"""Propose / independently approve / execute. Writes stay disabled by default."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .allowlist import (
    CREATE_FIELDS,
    GATE_ARRIVAL_WINDOW,
    GATE_AUTH,
    GATE_EXPIRED,
    GATE_IDENTITY,
    GATE_LIVE_PATCH_UNTESTED,
    GATE_READONLY,
    GATE_RECURRING,
    GATE_OPERATOR,
    GATE_READBACK,
    GATE_REPLAY,
    GATE_SCHEMA_UNVERIFIED,
    GATE_STALE,
    GATE_UNKNOWN_OP,
    GATE_WRITES_DISABLED,
    LINE_ITEM_FIELDS,
    LOCATION_NOTE_FIELDS,
    OCCURRENCE_FIELDS,
    ARRIVAL_FIELDS,
    NOTE_TEXT_FIELDS,
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
from .digest import proposal_digest
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

    def gates(self) -> dict[str, Any]:
        key_ready = False
        key = getattr(self.client, "api_key_present", None)
        if callable(key):
            key_ready = bool(key())
        return current_gates(
            writes_enabled=self.settings.writes_enabled,
            mapping_verified=self.settings.mapping_verified,
            api_role=self.settings.api_role,
            credential_ready=key_ready,
            oauth_ready=self.settings.oauth_ready(),
        )

    def _fail(self, gate: str, **detail: Any) -> dict[str, Any]:
        payload = {"ok": False, "gate": gate, "gates": self.gates()}
        payload.update(redact(detail))
        return payload

    def _identity_or_reject(self, identity: dict[str, str] | None) -> dict[str, str] | dict[str, Any]:
        if not identity or not identity.get("sub") or not identity.get("email"):
            return self._fail(GATE_AUTH)
        return {"sub": str(identity["sub"]), "email": str(identity["email"]).lower()}

    def propose(self, operation: str, payload: dict[str, Any], identity: dict[str, str] | None) -> dict[str, Any]:
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
                return self._propose_work_order_notes(payload, identity)
            if operation == OP_WORK_ORDER_SCHEDULE:
                return self._propose_work_order_schedule(payload, identity)
            if operation == OP_CREATE_WORK_ORDER:
                return self._propose_create(payload, identity)
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
            "starts_at": row.get("starts_at"),
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
        after = dict(before)
        after["starts_at"] = starts_at
        after["duration"] = duration
        after["service_route_ids"] = list(routes)
        for key in ARRIVAL_FIELDS:
            after[key] = before[key]
        result = self._persist_proposal(OP_WORK_ORDER_SCHEDULE, payload, identity, f"work_order:{work_order_id}", before, after)
        result["patch_fields"] = list(SCHEDULE_WRITE_FIELDS)
        return result

    def _propose_create(self, payload: dict[str, Any], identity: dict[str, str]) -> dict[str, Any]:
        assert_only(payload, CREATE_FIELDS, label="create")
        for item in payload.get("line_items") or []:
            if not isinstance(item, dict):
                return self._fail("unknown_field", fields=["line_items"])
            assert_only(item, LINE_ITEM_FIELDS, label="line_item")
        for occ in payload.get("occurrences") or []:
            if not isinstance(occ, dict):
                return self._fail("unknown_field", fields=["occurrences"])
            assert_only(occ, OCCURRENCE_FIELDS, label="occurrence")
            if "use_time_window" in occ:
                return self._fail(GATE_ARRIVAL_WINDOW)
        required = ("customer_id", "service_location_id", "repeat_type", "repeat_period")
        missing = [key for key in required if payload.get(key) in (None, "")]
        if missing:
            return self._fail("unknown_field", fields=missing)
        duplicates = self.client.search_work_orders()
        subject = f"create:{payload['customer_id']}:{payload['service_location_id']}:{payload.get('occurrences')}"
        before = {"existing_work_orders": [item.get("id") for item in duplicates], "schema": "unverified"}
        after = {"created": "not_executed", "payload": payload}
        result = self._persist_proposal(OP_CREATE_WORK_ORDER, payload, identity, subject, before, after)
        result["gates"] = self.gates()
        result["execute_blocked"] = [GATE_SCHEMA_UNVERIFIED, GATE_ARRIVAL_WINDOW, GATE_LIVE_PATCH_UNTESTED]
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
        digest = proposal_digest(
            operation=operation,
            identity=identity,
            subject_key=subject_key,
            before=before,
            after=after,
            payload=payload,
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
            "created_at": _iso(clock),
            "expires_at": _iso(clock + timedelta(seconds=self.settings.proposal_ttl_seconds)),
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
    ) -> dict[str, Any]:
        del approved  # model-supplied approved=true is not a gate
        ident = self._identity_or_reject(identity)
        if "ok" in ident and ident.get("ok") is False:
            return ident
        identity = ident  # type: ignore[assignment]
        if self._live_api_role() in {"", "readonly", "read_only"}:
            return self._fail(GATE_READONLY, proposal_id=proposal_id)
        proposal = self.store.get_proposal(proposal_id)
        if proposal is None:
            return self._fail("unknown_operation", proposal_id=proposal_id)
        clock = _utc(self._now())
        if proposal["identity"] != identity:
            return self._fail(GATE_IDENTITY, proposal_id=proposal_id)
        if _parse_iso(proposal["expires_at"]) <= clock:
            self.store.release_open_guard(proposal["subject_key"], proposal_id)
            self.store.set_status(proposal_id, "expired")
            return self._fail(GATE_EXPIRED, proposal_id=proposal_id)
        if proposal["status"] == "ambiguous":
            return self._fail("ambiguous_remote_write_no_retry", proposal_id=proposal_id)
        if proposal["status"] == "executed":
            return self._fail(GATE_REPLAY, proposal_id=proposal_id)
        if self.store.has_ambiguous(proposal["subject_key"]):
            return self._fail("ambiguous_remote_write_no_retry", proposal_id=proposal_id)
        if operator_approval:
            existing = self.store.get_approval(token_fingerprint(operator_approval))
            if existing and existing["used_at"]:
                return self._fail(GATE_REPLAY, proposal_id=proposal_id)
        if proposal["operation"] == OP_CREATE_WORK_ORDER:
            return self._fail(GATE_SCHEMA_UNVERIFIED, proposal_id=proposal_id)
        if proposal["operation"] in {OP_WORK_ORDER_NOTES, OP_WORK_ORDER_SCHEDULE}:
            stale = self._work_order_stale(proposal)
        else:
            stale = self._location_stale(proposal) if proposal["operation"] == OP_LOCATION_NOTES else None
        if stale is not None:
            return stale
        if not self._accept_operator(proposal, operator_approval, clock):
            return self._fail(self._operator_gate(operator_approval, proposal, clock), proposal_id=proposal_id)

        if proposal["operation"] == OP_LOCATION_NOTES:
            return self._execute_location_notes(proposal, clock)
        if proposal["operation"] == OP_WORK_ORDER_NOTES:
            return self._execute_work_order(proposal, clock, [key for key in NOTE_TEXT_FIELDS if key in proposal["payload"]])
        if proposal["operation"] == OP_WORK_ORDER_SCHEDULE:
            return self._execute_work_order(proposal, clock, list(SCHEDULE_WRITE_FIELDS))
        if proposal["operation"] == OP_CREATE_WORK_ORDER:
            return self._fail(GATE_SCHEMA_UNVERIFIED, proposal_id=proposal_id)
        return self._fail(GATE_UNKNOWN_OP, proposal_id=proposal_id)

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
        try:
            self.client.patch_work_order_fields(proposal["before"], proposal["after"], fields)
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
            row = self.client.get_work_order(str(proposal["before"]["work_order_id"]))
            readback = self._occurrence_snapshot(row)
        except Exception:
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "ambiguous")
            return self._fail(GATE_READBACK, proposal_id=proposal["proposal_id"])
        if snapshot_hash(readback) != snapshot_hash(proposal["after"]):
            self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "ambiguous")
            return self._fail(GATE_READBACK, proposal_id=proposal["proposal_id"])
        for key in ARRIVAL_FIELDS:
            if readback.get(key) != proposal["before"].get(key):
                self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "ambiguous")
                return self._fail(GATE_ARRIVAL_WINDOW, proposal_id=proposal["proposal_id"])
        self.store.finish_attempt(attempt_id, proposal["proposal_id"], proposal["subject_key"], "success")
        return {"ok": True, "proposal_id": proposal["proposal_id"], "operation": proposal["operation"], "readback": readback, "patch_fields": fields, "gates": self.gates()}

    def inspect(self, proposal_id: str, identity: dict[str, str] | None) -> dict[str, Any]:
        ident = self._identity_or_reject(identity)
        if "ok" in ident and ident.get("ok") is False:
            return ident
        proposal = self.store.get_proposal(proposal_id)
        if proposal is None:
            return self._fail("unknown_operation", proposal_id=proposal_id)
        if proposal["identity"] != ident:
            return self._fail(GATE_IDENTITY, proposal_id=proposal_id)
        return {"ok": True, **redact(proposal), "gates": self.gates()}
