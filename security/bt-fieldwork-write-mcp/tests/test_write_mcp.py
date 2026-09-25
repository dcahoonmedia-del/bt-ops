"""Focused offline gates. No live Fieldwork, GCP, or IAM."""

from __future__ import annotations

import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bt_fieldwork_write_mcp.allowlist import (
    GATE_ARRIVAL_WINDOW,
    GATE_AUTH,
    GATE_DUPLICATE,
    GATE_EXPIRED,
    GATE_IDENTITY,
    GATE_LEAD_STATUS,
    GATE_LIVE_PATCH_UNTESTED,
    GATE_READONLY,
    GATE_OPERATOR,
    GATE_READBACK,
    GATE_REPLAY,
    GATE_CREATE_RESPONSE,
    GATE_RECURRING,
    GATE_STALE,
    GATE_STARTS_AT_DATETIME,
    GATE_TAXABLE,
    GATE_UNKNOWN_FIELD,
    GATE_UNKNOWN_OP,
    GATE_WRITES_DISABLED,
    OP_CREATE_CUSTOMER,
    OP_CREATE_WORK_ORDER,
    OP_LOCATION_NOTES,
    OP_WORK_ORDER_NOTES,
)
from bt_fieldwork_write_mcp.config import Settings
from bt_fieldwork_write_mcp.errors import GateError
from bt_fieldwork_write_mcp.fieldwork import FakeTransport, TypedFieldworkClient, _assert_typed_path
from bt_fieldwork_write_mcp.secrets import InMemoryApiKey
from bt_fieldwork_write_mcp.server import build_mcp
from bt_fieldwork_write_mcp.oauth_rs import JwtTokenVerifier
from bt_fieldwork_write_mcp.service import WriteService
from bt_fieldwork_write_mcp.store import WriteStore


def _settings(path: Path, **overrides: object) -> Settings:
    values = dict(
        writes_enabled=False,
        mapping_verified=False,
        store_path=path,
        api_base="https://api3.fieldworkhq.com/v3.1",
        oauth_issuer="https://issuer.example.test",
        oauth_audience="bt-fieldwork-write",
        oauth_resource="https://write.example.test/mcp",
        oauth_jwks_url="",
        hs256_secret="hs256-test-secret-32bytes-min-ok",
        required_scopes=("fieldwork.write",),
        permitted_users=("daniel@btpestcontrol.com",),
        operator_key="operator-test-key",
        api_role="readonly",
        proposal_ttl_seconds=1800,
        approval_ttl_seconds=900,
        pestguard_initial_template_id="8835901",
        pestguard_initial_service_id="38814",
        residential_location_type_id="8736",
    )
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


IDENTITY = {"sub": "user-1", "email": "daniel@btpestcontrol.com"}
OTHER = {"sub": "user-2", "email": "other@example.com"}


def _customer(status: str = "Active") -> dict:
    return {"id": 41, "customer_status": status, "name": "Existing"}


def _location(notes: str = "old note") -> dict:
    return {
        "id": 77,
        "name": "House",
        "tax_rate_id": 3,
        "address": {"id": 900, "notes": notes},
    }


class Harness:
    def __init__(self, **overrides: object) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "write.sqlite"
        self.settings = _settings(self.path, **overrides)
        self.store = WriteStore(self.path)
        self.transport = FakeTransport()
        self.transport.api_role = self.settings.api_role
        self.transport.add_customer(_customer(), _location())
        self.client = TypedFieldworkClient(self.transport, mapping_verified=self.settings.mapping_verified)
        self.service = WriteService(self.settings, self.store, self.client)
        self.clock = datetime(2026, 9, 24, 20, 0, tzinfo=timezone.utc)
        self.service._now = lambda: self.clock

    def close(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def propose_notes(self, notes: str = "standing note") -> dict:
        return self.service.propose(
            OP_LOCATION_NOTES,
            {"customer_id": 41, "location_id": 77, "notes": notes},
            IDENTITY,
        )

    def approve(self, proposal_id: str) -> str:
        minted = self.service.mint_approval(proposal_id)
        assert minted.get("ok"), minted
        return minted["operator_approval"]


class WriteMcpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def test_disabled_writes(self) -> None:
        proposed = self.h.propose_notes()
        self.assertTrue(proposed["ok"], proposed)
        token = self.h.approve(proposed["proposal_id"])
        result = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token, approved=True)
        self.assertFalse(result["ok"])
        self.assertEqual(result["gate"], GATE_WRITES_DISABLED)
        self.assertFalse(result["gates"]["writes_enabled"])
        self.assertFalse(any(call["method"] == "PATCH" for call in self.h.transport.calls))

    def test_approved_true_from_model_is_ignored(self) -> None:
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        proposed = self.h.propose_notes()
        result = self.h.service.execute(proposed["proposal_id"], IDENTITY, approved=True)
        self.assertEqual(result["gate"], GATE_OPERATOR)

    def test_identity_mismatch(self) -> None:
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        proposed = self.h.propose_notes()
        token = self.h.approve(proposed["proposal_id"])
        result = self.h.service.execute(proposed["proposal_id"], OTHER, operator_approval=token)
        self.assertEqual(result["gate"], GATE_IDENTITY)

    def test_unknown_fields(self) -> None:
        result = self.h.service.propose(
            OP_LOCATION_NOTES,
            {"customer_id": 41, "location_id": 77, "notes": "x", "extra": "no"},
            IDENTITY,
        )
        self.assertEqual(result["gate"], GATE_UNKNOWN_FIELD)
        self.assertEqual(result["fields"], ["extra"])

    def test_unknown_operation_and_forbidden(self) -> None:
        for op in ("on_our_way", "http", "passthrough", "send_sms"):
            result = self.h.service.propose(op, {}, IDENTITY)
            self.assertEqual(result["gate"], GATE_UNKNOWN_OP, op)

    def test_never_lead_status(self) -> None:
        self.h.transport.add_customer({"id": 42, "customer_status": "Lead", "name": "Lead acct"}, {**_location(), "id": 79})
        result = self.h.service.propose(
            OP_LOCATION_NOTES,
            {"customer_id": 42, "location_id": 79, "notes": "x"},
            IDENTITY,
        )
        self.assertEqual(result["gate"], GATE_LEAD_STATUS)

    def test_stale_state(self) -> None:
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        proposed = self.h.propose_notes()
        token = self.h.approve(proposed["proposal_id"])
        self.h.transport.locations["41:77"]["address"]["notes"] = "changed by office"
        result = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(result["gate"], GATE_STALE)

    def test_expired_proposal(self) -> None:
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        proposed = self.h.propose_notes()
        token = self.h.approve(proposed["proposal_id"])
        self.h.clock = self.h.clock + timedelta(hours=3)
        result = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(result["gate"], GATE_EXPIRED)

    def test_expired_approval(self) -> None:
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer", approval_ttl_seconds=60)
        proposed = self.h.propose_notes()
        token = self.h.approve(proposed["proposal_id"])
        self.h.clock = self.h.clock + timedelta(minutes=2)
        result = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(result["gate"], GATE_EXPIRED)

    def test_replayed_approval(self) -> None:
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        proposed = self.h.propose_notes()
        token = self.h.approve(proposed["proposal_id"])
        first = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertTrue(first["ok"], first)
        again = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(again["gate"], GATE_REPLAY)

    def test_concurrent_duplicates(self) -> None:
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        results: list[dict] = []

        def worker() -> None:
            results.append(self.h.propose_notes())

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(results), 2)
        self.assertTrue(any(item.get("ok") for item in results))
        self.assertTrue(any(item.get("gate") == GATE_DUPLICATE for item in results))

    def test_crash_after_ambiguous_remote_write_no_retry(self) -> None:
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        proposed = self.h.propose_notes()
        token = self.h.approve(proposed["proposal_id"])
        self.h.transport.write_mode = "ambiguous"
        first = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(first["gate"], "ambiguous_remote_write_no_retry")
        self.h.store.close()
        restarted = WriteStore(self.h.path)
        client = TypedFieldworkClient(self.h.transport, mapping_verified=False)
        service = WriteService(self.h.settings, restarted, client)
        service._now = lambda: self.h.clock
        replay = service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(replay["gate"], "ambiguous_remote_write_no_retry")
        again = service.propose(OP_LOCATION_NOTES, {"customer_id": 41, "location_id": 77, "notes": "retry"}, IDENTITY)
        self.assertEqual(again["gate"], "ambiguous_remote_write_no_retry")
        restarted.close()

    def test_in_flight_restart_is_ambiguous(self) -> None:
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        proposed = self.h.propose_notes()
        self.h.store.begin_attempt(proposed["proposal_id"], f"location:41:77", self.h.clock.isoformat())
        self.h.store.close()
        restarted = WriteStore(self.h.path)
        row = restarted.get_proposal(proposed["proposal_id"])
        self.assertEqual(row["status"], "ambiguous")
        restarted.close()

    def test_failed_readback(self) -> None:
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        proposed = self.h.propose_notes("new standing")
        token = self.h.approve(proposed["proposal_id"])
        self.h.transport.readback_notes = "old note"
        result = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(result["gate"], GATE_READBACK)
        retry = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(retry["gate"], "ambiguous_remote_write_no_retry")

    def test_work_order_notes_fail_closed_unverified_mapping(self) -> None:
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer", mapping_verified=True)
        missing = self.h.service.propose(
            OP_WORK_ORDER_NOTES,
            {"work_order_id": "10", "service_appointment_id": "20", "instructions": "gate code"},
            IDENTITY,
        )
        self.assertFalse(missing["ok"])
        self.assertNotIn("before", missing)
        self.h.transport.work_orders["10"] = {"id": 10, "service_appointment_id": 20, "customer_id": 41, "service_location_id": 77, "instructions": "old", "private_notes": "secret"}
        proposed = self.h.service.propose(
            OP_WORK_ORDER_NOTES,
            {"work_order_id": "10", "service_appointment_id": "20", "instructions": "gate code"},
            IDENTITY,
        )
        self.assertTrue(proposed["ok"], proposed)
        self.assertEqual(proposed["before"]["instructions"], "old")
        self.assertEqual(proposed["after"]["instructions"], "gate code")
        token = self.h.approve(proposed["proposal_id"])
        executed = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertTrue(executed["ok"], executed)
        self.assertEqual(executed["readback"]["instructions"], "gate code")
        self.assertTrue(any(call["method"] == "PATCH" and call["path"] == "/work_orders/20" for call in self.h.transport.calls))

    def _work_order_payload(self, **overrides: object) -> dict:
        payload = {
            "customer_id": 41,
            "service_location_id": 77,
            "repeat_type": "none",
            "repeat_period": 0,
            "occurrences": [{"service_route_ids": [1], "starts_at": "2026-10-01"}],
        }
        payload.update(overrides)
        return payload

    def test_create_work_order_documented_contract(self) -> None:
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        unsafe = self.h.service.propose(
            OP_CREATE_WORK_ORDER,
            {
                "customer_id": 41,
                "service_location_id": 77,
                "repeat_type": "never",
                "repeat_period": 0,
                "line_items": [{"name": "Service", "type": "service", "quantity": 1, "price": 99}],
                "occurrences": [{"service_route_ids": [1], "starts_at": "2026-10-01T15:00:00Z", "duration": 60}],
            },
            IDENTITY,
        )
        self.assertFalse(unsafe["ok"])
        self.assertEqual(unsafe["gate"], GATE_UNKNOWN_FIELD)
        self.assertEqual(unsafe["fields"], ["repeat_type"])
        self.assertNotIn("proposal_id", unsafe)
        zulu = self.h.service.propose(OP_CREATE_WORK_ORDER, self._work_order_payload(occurrences=[{"service_route_ids": [1], "starts_at": "2026-10-01T15:00:00Z"}]), IDENTITY)
        self.assertEqual(zulu["gate"], GATE_STARTS_AT_DATETIME)
        weekly = self.h.service.propose(OP_CREATE_WORK_ORDER, self._work_order_payload(repeat_type="weekly"), IDENTITY)
        self.assertEqual(weekly["gate"], GATE_RECURRING)
        taxable = self.h.service.propose(
            OP_CREATE_WORK_ORDER,
            self._work_order_payload(line_items=[{"name": "Service", "type": "other", "quantity": 1, "price": 10, "taxable": True}]),
            IDENTITY,
        )
        self.assertEqual(taxable["gate"], GATE_TAXABLE)
        taxed = self.h.service.propose(OP_CREATE_WORK_ORDER, {**self._work_order_payload(), "tax_rate_id": 3}, IDENTITY)
        self.assertEqual(taxed["gate"], GATE_UNKNOWN_FIELD)
        self.assertIn("tax_rate_id", taxed["fields"])
        missing_payable = self.h.service.propose(
            OP_CREATE_WORK_ORDER,
            self._work_order_payload(line_items=[{"name": "Service", "type": "service", "quantity": 1, "price": 99}]),
            IDENTITY,
        )
        self.assertEqual(missing_payable["gate"], GATE_UNKNOWN_FIELD)
        self.assertIn("payable_id", missing_payable["fields"])
        fee = self.h.service.propose(
            OP_CREATE_WORK_ORDER,
            self._work_order_payload(line_items=[{"name": "Trip", "type": "fee", "quantity": 1, "price": 15}]),
            IDENTITY,
        )
        self.assertEqual(fee["gate"], "catalog_disagreement")
        self.assertFalse(any(call["method"] == "POST" for call in self.h.transport.calls))
        self.h.transport.customers["41"]["customer_status"] = "Lead"
        lead_order = self.h.service.propose(OP_CREATE_WORK_ORDER, self._work_order_payload(), IDENTITY)
        self.assertEqual(lead_order["gate"], GATE_LEAD_STATUS)
        self.h.transport.customers["41"]["customer_status"] = "Active"
        self.h.transport.users = [{"id": 10, "first_name": "Sam", "last_name": "Lee", "service_route_id": 1, "service_route_name": "North", "is_technician": True, "branches": []}]
        proposed = self.h.service.propose(OP_CREATE_WORK_ORDER, self._work_order_payload(), IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        self.assertTrue(proposed["starts_at_datetime_format_unverified"])
        self.assertFalse(proposed["response_schema_verified"])
        request = proposed["after"]["documented_request"]["service_appointment"]
        self.assertEqual(request["repeat_type"], "none")
        self.assertEqual(request["repeat_period"], 0)
        self.assertEqual(request["appointment_occurrences_attributes"][0]["starts_at"], "2026-10-01")
        self.assertNotIn("use_time_window", request["appointment_occurrences_attributes"][0])
        self.assertEqual(request["line_items_attributes"][0]["payable_type"], "Service")
        self.assertEqual(request["line_items_attributes"][0]["price"], proposed["after"]["service_pricing"]["price"])
        self.assertIsNone(proposed["after"]["route_staff"][0]["assignee"])
        self.assertFalse(proposed["promised_window_enforced"])
        self.assertFalse(proposed["live_tested"])
        token = self.h.approve(proposed["proposal_id"])
        executed = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertTrue(executed["ok"], executed)
        self.assertEqual(executed["readback"]["response_schema"], "fake_test_double_not_live_schema")
        self.assertFalse(executed["readback"]["response_schema_verified"])
        self.assertNotEqual(executed["readback"]["occurrence_id"], executed["readback"]["service_appointment_id"])
        self.assertFalse(executed["live_tested"])
        posts = [call for call in self.h.transport.calls if call["method"] == "POST"]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["path"], "/work_orders")
        self.assertEqual(posts[0]["body"], proposed["after"]["documented_request"])
        self.assertFalse(any(call["method"] == "PATCH" for call in self.h.transport.calls))
        self.h.transport.return_create_id = False
        unverified = self.h.service.propose(OP_CREATE_WORK_ORDER, self._work_order_payload(repeat_period=1), IDENTITY)
        token = self.h.approve(unverified["proposal_id"])
        failed = self.h.service.execute(unverified["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(failed["gate"], GATE_CREATE_RESPONSE)
        self.assertFalse(failed["retry"])
        again = self.h.service.execute(unverified["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(again["gate"], "ambiguous_remote_write_no_retry")
        self.assertEqual(len([call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/work_orders"]), 2)

    def test_arrival_window_rejected(self) -> None:
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        result = self.h.service.propose(
            OP_CREATE_WORK_ORDER,
            {
                "customer_id": 41,
                "service_location_id": 77,
                "repeat_type": "never",
                "repeat_period": 0,
                "line_items": [{"name": "Service", "type": "service", "quantity": 1, "price": 99}],
                "occurrences": [
                    {
                        "service_route_ids": [1],
                        "starts_at": "2026-10-01T15:00:00Z",
                        "use_time_window": True,
                    }
                ],
            },
            IDENTITY,
        )
        self.assertEqual(result["gate"], GATE_UNKNOWN_FIELD)
        self.assertEqual(result["fields"], ["use_time_window"])
        self.assertNotIn("proposal_id", result)
        self.assertFalse(any(call["method"] == "POST" for call in self.h.transport.calls))

    def test_create_customer_documented_contract(self) -> None:
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        residential = {
            "customer_type": "Residential",
            "last_name": "Ng",
            "billing_phone_kind": "Mobile",
            "note": "side door",
            "service_locations": [{"name": "Home", "same_as_billing_address": True}],
        }
        proposed = self.h.service.propose(OP_CREATE_CUSTOMER, residential, IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        body = proposed["after"]["documented_request"]["customer"]
        self.assertEqual(body["status"], "active")
        self.assertEqual(body["service_locations_attributes"], [{"name": "Home", "same_as_billing_address": True}])
        self.assertNotIn("tax_rate_id", body["service_locations_attributes"][0])
        self.assertNotIn("address_attributes", body["service_locations_attributes"][0])
        self.assertFalse(proposed["response_schema_verified"])
        token = self.h.approve(proposed["proposal_id"])
        executed = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertTrue(executed["ok"], executed)
        self.assertEqual(executed["readback"]["response_schema"], "fake_test_double_not_live_schema")
        posts = [call for call in self.h.transport.calls if call["method"] == "POST"]
        self.assertEqual(posts, [{"method": "POST", "path": "/customers", "body": {"customer": proposed["after"]["documented_request"]["customer"]}, "query": None}])
        commercial = self.h.service.propose(OP_CREATE_CUSTOMER, {"customer_type": "Commercial", "service_locations": [{"name": "Shop", "same_as_billing_address": False}]}, IDENTITY)
        self.assertEqual(commercial["gate"], GATE_UNKNOWN_FIELD)
        self.assertEqual(commercial["fields"], ["name"])
        lead = self.h.service.propose(OP_CREATE_CUSTOMER, {**residential, "status": "lead"}, IDENTITY)
        self.assertEqual(lead["gate"], GATE_LEAD_STATUS)
        nested = self.h.service.propose(
            OP_CREATE_CUSTOMER,
            {**residential, "service_locations": [{"name": "Home", "same_as_billing_address": True, "tax_rate_id": 3, "address_attributes": {"street": "1 Main"}}]},
            IDENTITY,
        )
        self.assertEqual(nested["gate"], GATE_UNKNOWN_FIELD)
        self.assertEqual(nested["fields"], ["address_attributes", "tax_rate_id"])
        invoicing = self.h.service.propose(OP_CREATE_CUSTOMER, {**residential, "invoicing_configuration": {"automation_type": "autopay"}}, IDENTITY)
        self.assertEqual(invoicing["gate"], GATE_UNKNOWN_FIELD)
        self.assertIn("invoicing_configuration", invoicing["fields"])
        first_only = self.h.service.propose(
            OP_CREATE_CUSTOMER,
            {"customer_type": "Residential", "first_name": "Ada", "service_locations": [{"name": "Home", "same_as_billing_address": True}]},
            IDENTITY,
        )
        self.assertEqual(first_only["gate"], GATE_UNKNOWN_FIELD)
        self.assertEqual(first_only["fields"], ["last_name"])
        self.assertIsNone(_assert_typed_path("POST", "/customers/41/service_locations"))

    def test_location_notes_success_path_offline(self) -> None:
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        proposed = self.h.propose_notes("leave on porch")
        token = self.h.approve(proposed["proposal_id"])
        result = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["readback"]["notes"], "leave on porch")
        self.assertEqual(result["readback"]["name"], "House")
        self.assertEqual(result["readback"]["tax_rate_id"], 3)
        self.assertEqual(result["readback"]["address_id"], 900)

    def test_secret_never_returned(self) -> None:
        key = InMemoryApiKey("super-secret-fieldwork-key")
        self.assertNotIn("super-secret", repr(key))
        self.assertNotIn("super-secret", str(key))
        proposed = self.h.propose_notes()
        dumped = str(proposed)
        self.assertNotIn("operator-test-key", dumped)
        self.assertFalse(any("token token=" in str(item).lower() for item in self.h.store.audit_events()))

    def test_missing_identity_is_auth_reject(self) -> None:
        result = self.h.service.propose(OP_LOCATION_NOTES, {"customer_id": 41, "location_id": 77, "notes": "x"}, None)
        self.assertEqual(result["gate"], GATE_AUTH)

    def test_readonly_blocks_even_when_writes_flag_on(self) -> None:
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="readonly")
        proposed = self.h.propose_notes()
        token = self.h.approve(proposed["proposal_id"])
        result = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(result["gate"], GATE_READONLY)
        self.assertFalse(any(call["method"] == "PATCH" for call in self.h.transport.calls))

    def test_gates_do_not_claim_live_readiness(self) -> None:
        gates = self.h.service.gates()
        self.assertFalse(gates["writes_enabled"])
        self.assertTrue(gates["fieldwork_get_protocol_historically_verified"])
        self.assertTrue(gates["fieldwork_get_auth_verified"])
        self.assertFalse(gates["credential_ready"])
        self.assertFalse(gates["live_ready"])
        self.assertEqual(gates["auth_query_parameter"], "api_key")
        self.assertFalse(gates["live_patch_tested"])
        self.assertFalse(gates["arrival_window_write_verified"])
        self.assertTrue(gates["check_connection_is_not_auth_proof"])
        self.assertEqual(gates["rollout_safeguard"], "readonly_api_role")
        self.assertIn("writes_disabled", gates["operations"]["update_service_location_notes"]["execute_blocked_by"])
        self.assertIn("readonly_api_role", gates["operations"]["update_service_location_notes"]["execute_blocked_by"])
        self.assertFalse(gates["work_order_id_mapping_verified"])
        self.assertTrue(gates["customer_create"])
        self.assertTrue(gates["operations"]["create_work_order"]["propose"])
        self.assertTrue(gates["operations"]["create_customer"]["propose"])
        self.assertTrue(gates["creation_schema_ready"])
        self.assertFalse(gates["creation_live_tested"])
        self.assertTrue(gates["operations"]["create_work_order"]["schema_ready"])
        self.assertFalse(gates["operations"]["create_work_order"]["live_tested"])
        self.assertFalse(gates["operations"]["create_work_order"]["response_schema_verified"])
        self.assertTrue(gates["operations"]["create_work_order"]["starts_at_datetime_format_unverified"])
        self.assertFalse(gates["create_response_schema_verified"])
        self.assertNotIn("work_order_schema_unverified", gates["closed_contracts"])
        self.assertIn("arrival_window_unverified", gates["closed_contracts"])
        self.assertNotIn("live_patch_untested", gates["closed_contracts"])
        self.assertIn("arrival_window_unverified", gates["closed_contracts"])

    def test_mcp_server_has_no_forbidden_tools(self) -> None:
        verifier = JwtTokenVerifier(self.h.settings)
        server = build_mcp(self.h.service, self.h.settings, verifier)
        names = {tool.name for tool in server._tool_manager.list_tools()}
        self.assertTrue({"report_gates", "propose_write", "execute_approved_write", "inspect_proposal", "search_customers", "get_customer", "get_service_location", "list_service_locations", "get_work_order", "list_work_orders", "list_schedule", "list_service_routes", "list_users"} <= names)
        for forbidden in ("create_customer", "on_our_way", "http", "passthrough", "send_message"):
            self.assertNotIn(forbidden, names)
