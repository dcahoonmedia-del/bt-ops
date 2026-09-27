"""Readback reconciliation, work-order status writes, and invoice-email PATCH. Offline only."""

from __future__ import annotations

import asyncio
import unittest
from dataclasses import replace

from bt_fieldwork_write_mcp.allowlist import (
    GATE_IDENTITY,
    GATE_PARTIAL,
    GATE_READBACK,
    GATE_REPLAY,
    GATE_STALE,
    GATE_STATUS_FAILED,
    GATE_UNKNOWN_OP,
)
from bt_fieldwork_write_mcp.fieldwork import _flatten
from bt_fieldwork_write_mcp.creation_flow import _same_instant, calendar_day
from bt_fieldwork_write_mcp.errors import AmbiguousWriteError, GateError
from bt_fieldwork_write_mcp.oauth_rs import JwtTokenVerifier
from bt_fieldwork_write_mcp.server import PROPOSE_DESCRIPTION, build_mcp
from tests.test_write_mcp import IDENTITY, OTHER, Harness


def _order(**occurrence: object) -> dict:
    item = {"service_route_ids": [1], "starts_at": "2026-10-02"}
    item.update(occurrence)
    return {
        "customer_id": 41,
        "service_location_id": 77,
        "repeat_type": "none",
        "repeat_period": 1,
        "occurrences": [item],
    }


class ReadbackStatusEmailTests(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness(writes_enabled=True, api_role="writer", mapping_verified=True)
        self.h.transport.users = [{
            "id": 10, "first_name": "Sam", "last_name": "Lee", "email": "sam@example.test",
            "service_route_id": 1, "service_route_name": "North", "is_technician": True, "branches": [],
        }]

    def tearDown(self) -> None:
        self.h.close()

    def _posts(self) -> list:
        return [call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/work_orders"]

    def _patches(self) -> list:
        return [call for call in self.h.transport.calls if call["method"] == "PATCH" and str(call["path"]).startswith("/work_orders/")]

    def _customer_patches(self) -> list:
        return [
            call for call in self.h.transport.calls
            if call["method"] == "PATCH" and call["path"] == "/customers/41"
        ]

    def _execute(self, proposed: dict) -> dict:
        return self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=self.h.approve(proposed["proposal_id"]))

    def test_timezone_equivalent_clocks_match_and_date_only_does_not_prove_an_offset(self) -> None:
        self.assertTrue(_same_instant("2026-09-28T11:30:00-04:00", "2026-09-28T15:30:00+00:00"))
        self.assertTrue(_same_instant("2026-09-28T11:30:00-04:00", "2026-09-28T11:30:00.000000-04:00"))
        self.assertFalse(_same_instant("2026-09-28T11:30:00-04:00", "2026-09-28"))
        self.assertEqual(calendar_day("2026-09-28T01:30:00+00:00"), "2026-09-27")
        self.assertEqual(calendar_day("2026-10-02"), "2026-10-02")

    def test_missing_schedule_read_then_exact_reconciliation(self) -> None:
        proposed = self.h.service.propose("create_work_order", _order(), IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        original = self.h.transport.request
        lists = {"n": 0}

        def request(method, path, body=None, query=None):
            if method == "GET" and path == "/work_orders":
                lists["n"] += 1
                if lists["n"] == 2:
                    return 200, []
            return original(method, path, body, query)

        self.h.transport.request = request
        done = self._execute(proposed)
        self.assertTrue(done["ok"], done)
        self.assertEqual(done["readback_attempts"], 2)
        self.assertFalse(done["live_tested"])
        self.assertEqual(len(self._posts()), 1)
        self.assertEqual(self._patches(), [])
        again = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(again["gate"], GATE_REPLAY)
        self.assertEqual(len(self._posts()), 1)

    def test_equivalent_readback_shape_verifies_without_another_write(self) -> None:
        timed = "2026-10-02T10:00:00-04:00"
        proposed = self.h.service.propose("create_work_order", _order(starts_at=timed, duration=60), IDENTITY)
        original = self.h.transport.request
        gets = {"n": 0}

        def request(method, path, body=None, query=None):
            status, payload = original(method, path, body, query)
            if method == "GET" and path.startswith("/work_orders/") and path.count("/") == 2 and isinstance(payload, dict):
                gets["n"] += 1
                if gets["n"] >= 2 and isinstance(payload.get("appointment_occurrence"), dict):
                    occ = dict(payload["appointment_occurrence"])
                    occ["starts_at"] = "2026-10-02T14:00:00+00:00"
                    occ["duration"] = "60"
                    occ["service_route_ids"] = ["1"]
                    occ["instructions"] = None
                    payload = {"appointment_occurrence": occ}
            return status, payload

        self.h.transport.request = request
        done = self._execute(proposed)
        self.assertTrue(done["ok"], done)
        self.assertEqual(done["readback_attempts"], 1)
        self.assertEqual(len(self._posts()), 1)
        self.assertEqual(len(self._patches()), 1)
        again = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(again["gate"], GATE_REPLAY)
        self.assertEqual(len(self._posts()), 1)
        self.assertEqual(len(self._patches()), 1)

    def test_exhausted_schedule_and_field_mismatches_stay_unresolved(self) -> None:
        proposed = self.h.service.propose("create_work_order", _order(starts_at="2026-10-03"), IDENTITY)
        original = self.h.transport.request

        def request(method, path, body=None, query=None):
            if method == "GET" and path == "/work_orders":
                request.lists += 1
                if request.lists >= 2:
                    return 200, []
            return original(method, path, body, query)

        request.lists = 0
        self.h.transport.request = request
        failed = self._execute(proposed)
        self.assertEqual(failed["gate"], GATE_PARTIAL)
        self.assertEqual(failed["reason"], GATE_READBACK)
        self.assertEqual(failed["partial"]["reason"], "occurrence_not_on_schedule")
        self.assertIsNotNone(failed["partial"]["occurrence_id"])
        self.assertIsNotNone(failed["partial"]["service_appointment_id"])
        self.assertNotEqual(failed["partial"]["occurrence_id"], failed["partial"]["service_appointment_id"])
        self.assertEqual(failed["retry"], False)
        self.assertEqual(len(self._posts()), 1)
        again = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(again["gate"], "ambiguous_remote_write_no_retry")
        self.assertEqual(len(self._posts()), 1)

        self.h.transport.request = original
        self.h.transport.readback_line_price = 1
        priced = self.h.service.propose("create_work_order", _order(starts_at="2026-10-04"), IDENTITY)
        price_failed = self._execute(priced)
        self.assertEqual(price_failed["reason"], GATE_READBACK)
        self.assertEqual(price_failed["partial"]["reason"], "field_mismatch")
        self.assertEqual(price_failed["partial"]["field"], "price")
        self.assertEqual(len(self._posts()), 2)
        self.h.service.execute(priced["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(len(self._posts()), 2)
        self.h.transport.readback_line_price = None

    def test_time_route_recurrence_and_identity_mismatches_do_not_replay(self) -> None:
        cases = {
            "starts_at": lambda occ: occ.update(starts_at="2026-10-08T15:00:00-04:00"),
            "service_route_ids": lambda occ: occ.update(service_route_ids=[9]),
            "repeat_type": lambda occ: occ.update(repeat_type="weekly"),
            "customer_id": lambda occ: occ.update(customer_id=999),
        }
        for index, (field, mutate) in enumerate(cases.items()):
            day = 8 + index
            proposed = self.h.service.propose(
                "create_work_order",
                _order(starts_at=f"2026-10-{day:02d}T10:00:00-04:00", duration=60),
                IDENTITY,
            )
            original = self.h.transport.request
            gets = {"n": 0}

            def request(method, path, body=None, query=None, mutate=mutate, original=original, gets=gets):
                status, payload = original(method, path, body, query)
                if method == "GET" and path.startswith("/work_orders/") and path.count("/") == 2 and isinstance(payload, dict):
                    gets["n"] += 1
                    if gets["n"] >= 2 and isinstance(payload.get("appointment_occurrence"), dict):
                        occ = dict(payload["appointment_occurrence"])
                        mutate(occ)
                        payload = {"appointment_occurrence": occ}
                return status, payload

            self.h.transport.request = request
            before_posts = len(self._posts())
            before_patches = len(self._patches())
            failed = self._execute(proposed)
            self.assertEqual(failed["gate"], GATE_PARTIAL, field)
            self.assertEqual(failed["reason"], GATE_READBACK, field)
            self.assertEqual(failed["partial"]["field"], field if field != "repeat_type" else "repeat_type", field)
            if field == "repeat_type":
                self.assertEqual(failed["partial"]["reason"], "recurrence_mismatch", field)
            else:
                self.assertEqual(failed["partial"]["reason"], "field_mismatch", field)
            self.assertEqual(len(self._posts()), before_posts + 1, field)
            self.assertEqual(len(self._patches()), before_patches + 1, field)
            self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval="unused")
            self.assertEqual(len(self._posts()), before_posts + 1, field)
            self.assertEqual(len(self._patches()), before_patches + 1, field)
            self.h.transport.request = original

    def test_date_only_get_does_not_verify_an_approved_offset(self) -> None:
        proposed = self.h.service.propose("create_work_order", _order(starts_at="2026-10-12T11:30:00-04:00", duration=60), IDENTITY)
        original = self.h.transport.request
        gets = {"n": 0}

        def request(method, path, body=None, query=None):
            status, payload = original(method, path, body, query)
            if method == "GET" and path.startswith("/work_orders/") and path.count("/") == 2 and isinstance(payload, dict):
                gets["n"] += 1
                if gets["n"] >= 2 and isinstance(payload.get("appointment_occurrence"), dict):
                    occ = dict(payload["appointment_occurrence"])
                    occ["starts_at"] = "2026-10-12"
                    occ["starts_at_date"] = "2026-10-12"
                    payload = {"appointment_occurrence": occ}
            return status, payload

        self.h.transport.request = request
        failed = self._execute(proposed)
        self.assertEqual(failed["partial"]["field"], "starts_at")
        self.assertEqual(len(self._patches()), 1)
        self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(len(self._posts()), 1)
        self.assertEqual(len(self._patches()), 1)

    def test_readback_rejects_a_substituted_appointment_pair(self) -> None:
        proposed = self.h.service.propose("create_work_order", _order(starts_at="2026-10-20T11:30:00-04:00", duration=60), IDENTITY)
        original = self.h.transport.request
        gets = {"n": 0}
        lists = {"n": 0}

        def request(method, path, body=None, query=None):
            status, payload = original(method, path, body, query)
            if method == "GET" and path == "/work_orders" and isinstance(payload, list):
                lists["n"] += 1
                if lists["n"] >= 2:
                    payload = [dict(row, service_appointment_id=999999) for row in payload]
            if method == "GET" and path.startswith("/work_orders/") and path.count("/") == 2 and isinstance(payload, dict):
                gets["n"] += 1
                if gets["n"] >= 2 and isinstance(payload.get("appointment_occurrence"), dict):
                    occ = dict(payload["appointment_occurrence"])
                    occ["service_appointment_id"] = 999999
                    payload = {"appointment_occurrence": occ}
            return status, payload

        self.h.transport.request = request
        failed = self._execute(proposed)
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["gate"], GATE_PARTIAL)
        self.assertEqual(failed["reason"], GATE_READBACK)
        self.assertEqual(failed["partial"]["occurrence_id"], 900001)
        self.assertEqual(failed["partial"]["service_appointment_id"], 900002)
        self.assertEqual(failed["partial"]["field"], "service_appointment_id")
        self.assertEqual(failed["partial"]["reason"], "field_mismatch")
        self.assertEqual(failed["retry"], False)
        self.assertEqual(len(self._posts()), 1)
        self.assertEqual(len(self._patches()), 1)
        self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(len(self._posts()), 1)
        self.assertEqual(len(self._patches()), 1)

    def test_transient_read_errors_recover_or_keep_the_pair(self) -> None:
        original = self.h.transport.request

        def run(day: str, gate: str, *, exhaust: bool) -> dict:
            proposed = self.h.service.propose(
                "create_work_order",
                _order(starts_at=f"2026-10-{day}T11:30:00-04:00", duration=60),
                IDENTITY,
            )
            gets = {"n": 0}

            def request(method, path, body=None, query=None):
                if method == "GET" and path.startswith("/work_orders/") and path.count("/") == 2:
                    gets["n"] += 1
                    if gets["n"] >= 2 and (exhaust or gets["n"] == 2):
                        raise GateError(gate)
                return original(method, path, body, query)

            self.h.transport.request = request
            return self._execute(proposed)

        recovered = run("21", "transport_error", exhaust=False)
        self.assertTrue(recovered["ok"], recovered)
        self.assertEqual(recovered["readback_attempts"], 2)
        self.assertEqual(recovered["readback"]["occurrence_id"], 900001)
        self.assertEqual(recovered["readback"]["service_appointment_id"], 900002)
        self.assertEqual(len(self._posts()), 1)
        self.assertEqual(len(self._patches()), 1)

        unread = run("22", "unreadable_response", exhaust=False)
        self.assertTrue(unread["ok"], unread)
        self.assertEqual(unread["readback_attempts"], 2)
        self.assertEqual(len(self._posts()), 2)
        self.assertEqual(len(self._patches()), 2)

        posts = len(self._posts())
        patches = len(self._patches())
        exhausted = run("23", "transport_error", exhaust=True)
        self.assertEqual(exhausted["gate"], GATE_PARTIAL)
        self.assertEqual(exhausted["reason"], GATE_READBACK)
        self.assertEqual(exhausted["partial"]["reason"], "transport_error")
        self.assertEqual(exhausted["partial"]["occurrence_id"], 900005)
        self.assertEqual(exhausted["partial"]["service_appointment_id"], 900006)
        self.assertEqual(exhausted["retry"], False)
        self.assertEqual(len(self._posts()), posts + 1)
        self.assertEqual(len(self._patches()), patches + 1)
        again = self.h.service.execute(exhausted["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(again["gate"], "ambiguous_remote_write_no_retry")
        self.assertEqual(len(self._posts()), posts + 1)
        self.assertEqual(len(self._patches()), patches + 1)

        unread_exhausted = run("24", "unreadable_response", exhaust=True)
        self.assertEqual(unread_exhausted["gate"], GATE_PARTIAL)
        self.assertEqual(unread_exhausted["partial"]["reason"], "unreadable_response")
        self.assertEqual(unread_exhausted["partial"]["occurrence_id"], 900007)
        self.assertEqual(unread_exhausted["partial"]["service_appointment_id"], 900008)
        self.assertEqual(len(self._posts()), posts + 2)
        self.assertEqual(len(self._patches()), patches + 2)
        self.h.service.execute(unread_exhausted["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(len(self._posts()), posts + 2)
        self.assertEqual(len(self._patches()), patches + 2)

    def _status_row(self) -> None:
        self.h.transport.work_orders["8210"] = {
            "id": 8210,
            "service_appointment_id": 1501,
            "customer_id": 41,
            "service_location_id": 77,
            "starts_at": "2026-09-28T11:30:00-04:00",
            "duration": 60,
            "service_route_ids": [2557],
            "service_routes": [{"id": 2557, "name": "Route #3"}],
            "status": "Scheduled",
            "instructions": "gate",
            "private_notes": "keep",
            "repeat_type": "none",
            "production_value": "150.0",
            "line_items": [{"name": "PestGuard - Set-up", "price": "150.0", "quantity": 1, "payable_id": 38814, "payable_type": "Service"}],
            "arrival_time_window_str": "11:30 AM-12:30 PM",
        }

    def _drop(self, proposed: dict) -> None:
        stored = self.h.store.get_proposal(proposed["proposal_id"])
        self.h.store.release_open_guard(stored["subject_key"], proposed["proposal_id"])
        self.h.store.set_status(proposed["proposal_id"], "expired")

    def _status_patches(self) -> list:
        return [call for call in self.h.transport.calls if call["method"] == "PATCH" and call["path"] == "/work_orders/1501"]

    def test_known_status_resolves_and_unknown_or_mismatched_ids_do_not_write(self) -> None:
        self._status_row()
        proposed = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8210, "service_appointment_id": 1501, "status": "Today - Anytime"},
            IDENTITY,
        )
        self.assertTrue(proposed["ok"], proposed)
        self.assertEqual(proposed["changed_fields"], ["status"])
        self.assertFalse(proposed["live_tested"])
        self.assertEqual(proposed["other_fields"], "not_sent")
        self.assertEqual(proposed["before"]["customer_name"], "Existing")
        self.assertEqual(proposed["before"]["location"], "House")
        self.assertEqual(proposed["before"]["work_order_id"], "8210")
        self.assertEqual(proposed["before"]["service_appointment_id"], "1501")
        self.assertEqual(proposed["before"]["status"], "Scheduled")
        self.assertEqual(proposed["before"]["starts_at"], "2026-09-28T11:30:00-04:00")
        self.assertEqual(proposed["before"]["route"], [{"id": 2557, "name": "Route #3"}])
        self.assertEqual(proposed["after"]["status"], "Today - Anytime")
        self.assertEqual(proposed["after"]["status_write"], "Today - Anytime")
        self.assertEqual(proposed["after"]["only_change"], "status")
        self.assertNotIn("starts_at", proposed["after"])
        self.assertNotIn("instructions", proposed["after"])
        catalog = [call for call in self.h.transport.calls if call["path"] == "/statuses/i18n_statuses"]
        self.assertEqual(catalog[-1]["query"], {"entity_type": "appointment_occurrence"})
        self.assertEqual(self._status_patches(), [])
        self._drop(proposed)

        missed = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8210, "service_appointment_id": 1501, "status": "Missed"},
            IDENTITY,
        )
        self.assertTrue(missed["ok"], missed)
        self.assertEqual(missed["after"]["status"], "Missed")
        self.assertEqual(missed["after"]["status_write"], "Missed Appointment")
        self._drop(missed)

        flagged = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8210, "service_appointment_id": 1501, "status": "Left Message with Customer"},
            IDENTITY,
        )
        self.assertEqual(flagged["after"]["status_write"], "Left Message with Customer")
        self._drop(flagged)

        self.h.transport.work_order_statuses = ["Scheduled", "Flagged", "Today - Anytime"]
        strings = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8210, "service_appointment_id": 1501, "status": "Flagged"},
            IDENTITY,
        )
        self.assertEqual(strings["after"]["status_write"], "Flagged")
        self._drop(strings)

        unknown = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8210, "service_appointment_id": 1501, "status": "Mystery"},
            IDENTITY,
        )
        self.assertEqual(unknown["gate"], "unknown_status")
        self.assertNotIn("proposal_id", unknown)
        wrong = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8210, "service_appointment_id": 999, "status": "Today - Anytime"},
            IDENTITY,
        )
        self.assertEqual(wrong["gate"], GATE_IDENTITY)
        extra = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8210, "service_appointment_id": 1501, "status": "Today - Anytime", "starts_at": "2026-09-28T11:30:00-04:00"},
            IDENTITY,
        )
        self.assertEqual(extra["gate"], "unknown_field")
        self.assertEqual(extra["fields"], ["starts_at"])
        self.h.transport.work_order_statuses = {"scheduled": "Scheduled"}
        unverified = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8210, "service_appointment_id": 1501, "status": "Scheduled"},
            IDENTITY,
        )
        self.assertEqual(unverified["gate"], "work_order_status_catalog_unverified")
        self.assertEqual(self._status_patches(), [])
        created = self.h.service.propose(
            "create_work_order",
            {"customer_id": 41, "service_location_id": 77, "repeat_type": "none", "occurrences": [{"starts_at": "2026-10-02", "service_route_ids": [1], "status": "Scheduled"}]},
            IDENTITY,
        )
        self.assertEqual(created["gate"], "unknown_field")
        self.assertIn("status", created["fields"])
        phone = self.h.service.propose("update_customer_phone", {"customer_id": 41, "billing_phone": "7165550100"}, IDENTITY)
        self.assertEqual(phone["gate"], GATE_UNKNOWN_OP)

    def test_status_write_is_one_approved_patch_and_readback_preserves_other_fields(self) -> None:
        self._status_row()
        proposed = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8210, "service_appointment_id": 1501, "status": "Today - Anytime"},
            IDENTITY,
        )
        missing = self.h.service.execute(proposed["proposal_id"], IDENTITY)
        self.assertEqual(missing["gate"], "operator_approval_required")
        self.assertEqual(self._status_patches(), [])
        token = self.h.approve(proposed["proposal_id"])
        self.h.store._conn.execute("UPDATE proposals SET payload_json = '{}' WHERE proposal_id = ?", (proposed["proposal_id"],))
        altered = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(altered["gate"], "operator_approval_required")
        self.assertEqual(altered["reason"], "stored_proposal_digest_mismatch")
        self.assertEqual(self._status_patches(), [])
        stored = self.h.store.get_proposal(proposed["proposal_id"])
        self.h.store.release_open_guard(stored["subject_key"], proposed["proposal_id"])
        self.h.store.set_status(proposed["proposal_id"], "expired")

        fresh = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8210, "service_appointment_id": 1501, "status": "Today - Anytime"},
            IDENTITY,
        )
        self.h.transport.work_orders["8210"]["starts_at"] = "2026-09-28T12:00:00-04:00"
        stale = self._execute(fresh)
        self.assertEqual(stale["gate"], GATE_STALE)
        self.assertEqual(self._status_patches(), [])
        self.h.transport.work_orders["8210"]["starts_at"] = "2026-09-28T11:30:00-04:00"

        done = self._execute(self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8210, "service_appointment_id": 1501, "status": "Today - Anytime"},
            IDENTITY,
        ))
        self.assertTrue(done["ok"], done)
        self.assertEqual(done["readback"]["status"], "Today - Anytime")
        self.assertFalse(done["live_tested"])
        self.assertEqual(len(self._status_patches()), 1)
        body = self._status_patches()[0]["body"]
        occurrence = body["service_appointment"]["appointment_occurrences_attributes"][0]
        self.assertEqual(set(body), {"service_appointment"})
        self.assertEqual(set(occurrence), {"id", "status"})
        self.assertEqual(occurrence["id"], "8210")
        self.assertEqual(occurrence["status"], "Today - Anytime")
        self.assertEqual(
            _flatten(body),
            [
                ("service_appointment[appointment_occurrences_attributes][][id]", "8210"),
                ("service_appointment[appointment_occurrences_attributes][][status]", "Today - Anytime"),
            ],
        )
        row = self.h.transport.work_orders["8210"]
        self.assertEqual(row["instructions"], "gate")
        self.assertEqual(row["private_notes"], "keep")
        self.assertEqual(row["starts_at"], "2026-09-28T11:30:00-04:00")
        self.assertEqual(row["duration"], 60)
        self.assertEqual(row["service_route_ids"], [2557])
        self.assertEqual(row["arrival_time_window_str"], "11:30 AM-12:30 PM")
        self.assertEqual(row["production_value"], "150.0")
        self.assertEqual(row["line_items"][0]["price"], "150.0")
        self.assertEqual(row["repeat_type"], "none")
        replay = self.h.service.execute(done["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(replay["gate"], GATE_REPLAY)
        self.assertEqual(len(self._status_patches()), 1)

        chatgpt = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8210, "service_appointment_id": 1501, "status": "Flagged"},
            IDENTITY,
        )
        self.h.service.settings = replace(self.h.settings, approval_mode="chatgpt_confirmation")
        wrong_digest = self.h.service.execute(chatgpt["proposal_id"], IDENTITY, approved=True, expected_digest="0" * 64)
        self.assertEqual(wrong_digest["gate"], "operator_approval_required")
        self.assertEqual(len(self._status_patches()), 1)
        self.h.service.settings = self.h.settings

    def test_ambiguous_status_reconciles_or_fails_without_a_second_patch(self) -> None:
        self._status_row()
        self.h.transport.write_mode = "timeout_after_apply"
        proposed = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8210, "service_appointment_id": 1501, "status": "Today - Anytime"},
            IDENTITY,
        )
        reconciled = self._execute(proposed)
        self.assertTrue(reconciled["ok"], reconciled)
        self.assertTrue(reconciled["ambiguity_reconciled"])
        self.assertEqual(reconciled["retry"], False)
        self.assertEqual(reconciled["readback"]["status"], "Today - Anytime")
        self.assertEqual(len(self._status_patches()), 1)
        self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(len(self._status_patches()), 1)

        self.h.transport.work_orders["8210"]["status"] = "Scheduled"
        self.h.transport.write_mode = "ambiguous"
        unchanged = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8210, "service_appointment_id": 1501, "status": "Flagged"},
            IDENTITY,
        )
        failed = self._execute(unchanged)
        self.assertEqual(failed["gate"], "ambiguous_remote_write_no_retry")
        self.assertEqual(failed["retry"], False)
        self.assertEqual(failed["readback_attempts"], 3)
        self.assertEqual(self.h.transport.work_orders["8210"]["status"], "Scheduled")
        stored = self.h.store.get_proposal(unchanged["proposal_id"])
        self.assertEqual(stored["status"], "ambiguous")
        self.assertTrue(self.h.store.has_ambiguous(stored["subject_key"]))
        patches = len(self._status_patches())
        self.h.service.execute(unchanged["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(len(self._status_patches()), patches)
        blocked = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8210, "service_appointment_id": 1501, "status": "Flagged"},
            IDENTITY,
        )
        self.assertEqual(blocked["gate"], "ambiguous_remote_write_no_retry")
        self.assertEqual(len(self._status_patches()), patches)

        self.h.transport.work_orders["8211"] = dict(self.h.transport.work_orders["8210"])
        self.h.transport.work_orders["8211"]["id"] = 8211
        self.h.transport.work_orders["8211"]["service_appointment_id"] = 1502
        self.h.transport.work_orders["8211"]["status"] = "Scheduled"
        original = self.h.transport.request

        seen = {"patch": False}

        def hide_readback(method, path, body=None, query=None):
            if method == "PATCH" and path == "/work_orders/1502":
                seen["patch"] = True
            if method == "GET" and path == "/work_orders/8211" and seen["patch"]:
                raise GateError("transport_error")
            return original(method, path, body, query)

        self.h.transport.write_mode = "timeout_after_apply"
        hidden = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8211, "service_appointment_id": 1502, "status": "Today - Anytime"},
            IDENTITY,
        )
        def appointment_patches(path: str) -> list:
            return [call for call in self.h.transport.calls if call["method"] == "PATCH" and call["path"] == path]

        before_patches = len(appointment_patches("/work_orders/1502"))
        self.h.transport.request = hide_readback
        ambiguous = self._execute(hidden)
        self.assertEqual(ambiguous["gate"], "ambiguous_remote_write_no_retry")
        self.assertEqual(ambiguous["retry"], False)
        self.assertEqual(ambiguous["readback_attempts"], 3)
        self.assertEqual(len(appointment_patches("/work_orders/1502")), before_patches + 1)
        self.h.transport.request = original
        self.h.service.execute(hidden["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(len(appointment_patches("/work_orders/1502")), before_patches + 1)

    def test_status_api_rejection_is_not_retried(self) -> None:
        self._status_row()
        original = self.h.transport.request

        def reject(method, path, body=None, query=None):
            if method == "PATCH" and path == "/work_orders/1501":
                self.h.transport.calls.append({"method": method, "path": path, "body": body, "query": query})
                return 422, {"error": "transition_rejected"}
            return original(method, path, body, query)

        self.h.transport.request = reject
        proposed = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8210, "service_appointment_id": 1501, "status": "Today - Anytime"},
            IDENTITY,
        )
        refused = self._execute(proposed)
        self.assertEqual(refused["gate"], "work_order_patch_rejected")
        self.assertEqual(refused["status"], 422)
        self.assertEqual(refused["retry"], False)
        self.assertEqual(self.h.transport.work_orders["8210"]["status"], "Scheduled")
        self.assertEqual(len(self._status_patches()), 1)
        self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(len(self._status_patches()), 1)

    def test_status_204_and_timeout_wait_for_exact_readback_without_another_patch(self) -> None:
        self._status_row()
        original = self.h.transport.request

        def lagging(*, empty=False, errors=0, stale=0, mutate=None):
            state = {"patched": False, "reads": 0}

            def request(method, path, body=None, query=None):
                if method == "PATCH" and path == "/work_orders/1501":
                    state["patched"] = True
                    if empty:
                        status, payload = original(method, path, body, query)
                        return 204, None if status == 200 else (status, payload)
                    return original(method, path, body, query)
                if method == "GET" and path == "/work_orders/8210" and state["patched"]:
                    state["reads"] += 1
                    if state["reads"] <= errors:
                        raise GateError("transport_error")
                    status, payload = original(method, path, body, query)
                    if state["reads"] <= errors + stale and isinstance(payload, dict):
                        occurrence = dict(payload["appointment_occurrence"])
                        occurrence["status"] = "Scheduled"
                        if mutate:
                            mutate(occurrence)
                        return status, {"appointment_occurrence": occurrence}
                    if mutate and isinstance(payload, dict):
                        occurrence = dict(payload["appointment_occurrence"])
                        mutate(occurrence)
                        return status, {"appointment_occurrence": occurrence}
                    return status, payload
                return original(method, path, body, query)

            return request

        self.h.transport.request = lagging(empty=True, stale=2)
        proposed = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8210, "service_appointment_id": 1501, "status": "Today - Anytime"},
            IDENTITY,
        )
        done = self._execute(proposed)
        self.assertTrue(done["ok"], done)
        self.assertNotIn("ambiguity_reconciled", done)
        self.assertEqual(done["readback_attempts"], 3)
        self.assertEqual(done["readback"]["status"], "Today - Anytime")
        self.assertEqual(done["readback"]["work_order_id"], "8210")
        self.assertEqual(done["readback"]["service_appointment_id"], "1501")
        self.assertEqual(len(self._status_patches()), 1)
        self.assertEqual(self.h.transport.work_orders["8210"]["instructions"], "gate")
        self.assertEqual(self.h.transport.work_orders["8210"]["status"], "Today - Anytime")

        self.h.transport.request = original
        self.h.transport.work_orders["8210"]["status"] = "Scheduled"
        self.h.transport.write_mode = "timeout_after_apply"
        self.h.transport.request = lagging(errors=2)
        delayed = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8210, "service_appointment_id": 1501, "status": "Today - Anytime"},
            IDENTITY,
        )
        reconciled = self._execute(delayed)
        self.assertTrue(reconciled["ok"], reconciled)
        self.assertTrue(reconciled["ambiguity_reconciled"])
        self.assertEqual(reconciled["retry"], False)
        self.assertEqual(reconciled["readback_attempts"], 3)
        self.assertEqual(reconciled["readback"]["status"], "Today - Anytime")
        self.assertEqual(len(self._status_patches()), 2)

        self.h.transport.request = original
        self.h.transport.write_mode = "ok"
        self.h.transport.work_orders["8212"] = dict(self.h.transport.work_orders["8210"])
        self.h.transport.work_orders["8212"]["id"] = 8212
        self.h.transport.work_orders["8212"]["service_appointment_id"] = 1503
        self.h.transport.work_orders["8212"]["status"] = "Scheduled"
        self.h.transport.work_orders["8212"]["instructions"] = "gate"

        def stuck_old(method, path, body=None, query=None):
            status, payload = original(method, path, body, query)
            if method == "PATCH" and path == "/work_orders/1503" and status == 200:
                return 204, None
            if method == "GET" and path == "/work_orders/8212" and any(
                call["method"] == "PATCH" and call["path"] == "/work_orders/1503" for call in self.h.transport.calls
            ):
                occurrence = dict(payload["appointment_occurrence"])
                occurrence["status"] = "Scheduled"
                return status, {"appointment_occurrence": occurrence}
            return status, payload

        self.h.transport.request = stuck_old
        held = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8212, "service_appointment_id": 1503, "status": "Today - Anytime"},
            IDENTITY,
        )
        unverified = self._execute(held)
        self.assertEqual(unverified["gate"], "ambiguous_remote_write_no_retry")
        self.assertEqual(unverified["reason"], "readback_unverified")
        self.assertEqual(unverified["retry"], False)
        self.assertEqual(unverified["readback_attempts"], 3)
        self.assertNotEqual(unverified["gate"], GATE_STATUS_FAILED)
        stored = self.h.store.get_proposal(held["proposal_id"])
        self.assertEqual(stored["status"], "ambiguous")
        self.assertTrue(self.h.store.has_ambiguous(stored["subject_key"]))
        self.assertEqual(self.h.transport.work_orders["8212"]["status"], "Today - Anytime")
        patches = [call for call in self.h.transport.calls if call["method"] == "PATCH" and call["path"] == "/work_orders/1503"]
        replay = self.h.service.execute(held["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(replay["gate"], "ambiguous_remote_write_no_retry")
        again = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8212, "service_appointment_id": 1503, "status": "Flagged"},
            IDENTITY,
        )
        self.assertEqual(again["gate"], "ambiguous_remote_write_no_retry")
        self.assertEqual(len([call for call in self.h.transport.calls if call["method"] == "PATCH" and call["path"] == "/work_orders/1503"]), len(patches))

        self.h.transport.request = original
        self.h.transport.work_orders["8213"] = dict(self.h.transport.work_orders["8210"])
        self.h.transport.work_orders["8213"]["id"] = 8213
        self.h.transport.work_orders["8213"]["service_appointment_id"] = 1504
        self.h.transport.work_orders["8213"]["status"] = "Scheduled"

        def wrong_identity(method, path, body=None, query=None):
            status, payload = original(method, path, body, query)
            if method == "PATCH" and path == "/work_orders/1504" and status == 200:
                return 204, None
            if method == "GET" and path == "/work_orders/8213" and isinstance(payload, dict) and payload.get("appointment_occurrence", {}).get("status") == "Today - Anytime":
                occurrence = dict(payload["appointment_occurrence"])
                occurrence["service_appointment_id"] = 9999
                return status, {"appointment_occurrence": occurrence}
            return status, payload

        self.h.transport.request = wrong_identity
        mismatched = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8213, "service_appointment_id": 1504, "status": "Today - Anytime"},
            IDENTITY,
        )
        rejected = self._execute(mismatched)
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["reason"], "identity_mismatch")
        self.assertEqual(rejected["readback_attempts"], 1)
        self.assertTrue(self.h.store.has_ambiguous(self.h.store.get_proposal(mismatched["proposal_id"])["subject_key"]))
        identity_patches = [call for call in self.h.transport.calls if call["method"] == "PATCH" and call["path"] == "/work_orders/1504"]
        self.assertEqual(len(identity_patches), 1)

        self.h.transport.request = original
        self.h.transport.work_orders["8214"] = dict(self.h.transport.work_orders["8210"])
        self.h.transport.work_orders["8214"]["id"] = 8214
        self.h.transport.work_orders["8214"]["service_appointment_id"] = 1505
        self.h.transport.work_orders["8214"]["status"] = "Scheduled"
        self.h.transport.work_orders["8214"]["instructions"] = "gate"

        def changed_instructions(method, path, body=None, query=None):
            status, payload = original(method, path, body, query)
            if method == "PATCH" and path == "/work_orders/1505" and status == 200:
                return 204, None
            if method == "GET" and path == "/work_orders/8214" and isinstance(payload, dict) and payload.get("appointment_occurrence", {}).get("status") == "Today - Anytime":
                occurrence = dict(payload["appointment_occurrence"])
                occurrence["instructions"] = "changed"
                return status, {"appointment_occurrence": occurrence}
            return status, payload

        self.h.transport.request = changed_instructions
        drifted = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8214, "service_appointment_id": 1505, "status": "Today - Anytime"},
            IDENTITY,
        )
        kept = self._execute(drifted)
        self.assertFalse(kept["ok"])
        self.assertEqual(kept["reason"], "protected_field_mismatch")
        self.assertEqual(kept["readback_attempts"], 1)
        self.assertEqual(len([call for call in self.h.transport.calls if call["method"] == "PATCH" and call["path"] == "/work_orders/1505"]), 1)
        self.assertTrue(self.h.store.has_ambiguous(self.h.store.get_proposal(drifted["proposal_id"])["subject_key"]))
        self.assertEqual(self.h.transport.work_orders["8214"]["instructions"], "gate")

    def test_primary_email_patch_is_one_customer_write_and_verified(self) -> None:
        customer = self.h.transport.customers["41"]
        customer["invoice_email"] = "old@example.test"
        customer["name"] = "Existing"
        location = self.h.transport.locations["41:77"]
        location["same_as_billing_address"] = True
        location["email"] = "old@example.test"
        proposed = self.h.service.propose(
            "update_customer_primary_email",
            {"customer_id": 41, "primary_email": "ada@example.test"},
            IDENTITY,
        )
        self.assertTrue(proposed["ok"], proposed)
        self.assertFalse(proposed["live_tested"])
        self.assertEqual(proposed["changed_fields"], ["invoice_email"])
        self.assertEqual(proposed["before"]["invoice_email"], "old@example.test")
        self.assertEqual(proposed["before"]["name"], "Existing")
        self.assertEqual(proposed["after"]["invoice_email"], "ada@example.test")
        self.assertEqual(proposed["after"]["location_email_patch"], "not_sent")
        self.assertEqual(self._customer_patches(), [])
        missing = self.h.service.execute(proposed["proposal_id"], IDENTITY)
        self.assertEqual(missing["gate"], "operator_approval_required")
        self.assertEqual(self._customer_patches(), [])
        token = self.h.approve(proposed["proposal_id"])
        other = self.h.service.execute(proposed["proposal_id"], OTHER, operator_approval=token)
        self.assertEqual(other["gate"], GATE_IDENTITY)
        self.assertEqual(self._customer_patches(), [])
        done = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertTrue(done["ok"], done)
        self.assertEqual(done["readback"]["invoice_email"], "ada@example.test")
        self.assertEqual(done["readback"]["customer_id"], 41)
        self.assertEqual(done["readback"]["location_email_patch"], "not_sent")
        self.assertEqual(done["readback"]["observed_location_emails"][0]["email"], "ada@example.test")
        self.assertFalse(done["live_tested"])
        self.assertEqual(len(self._customer_patches()), 1)
        self.assertEqual(self._customer_patches()[0]["body"], {"customer": {"invoice_email": "ada@example.test"}})
        self.assertFalse(any(call["method"] == "PATCH" and "service_locations" in call["path"] for call in self.h.transport.calls))
        self.assertFalse(any(call["method"] == "POST" and call["path"].endswith("/contacts") for call in self.h.transport.calls))
        replay = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(replay["gate"], GATE_REPLAY)
        self.assertEqual(len(self._customer_patches()), 1)

    def test_email_204_and_ambiguous_reconciliation_do_not_replay(self) -> None:
        self.h.transport.customers["41"]["invoice_email"] = "old@example.test"
        original = self.h.transport.request

        def as_204(method, path, body=None, query=None):
            status, payload = original(method, path, body, query)
            if method == "PATCH" and path == "/customers/41":
                return 204, None
            return status, payload

        self.h.transport.request = as_204
        proposed = self.h.service.propose("update_customer_primary_email", {"customer_id": 41, "primary_email": "ada@example.test"}, IDENTITY)
        done = self._execute(proposed)
        self.assertTrue(done["ok"], done)
        self.assertEqual(done["readback"]["invoice_email"], "ada@example.test")
        self.assertEqual(len(self._customer_patches()), 1)

        self.h.transport.request = original
        self.h.transport.customers["41"]["invoice_email"] = "old@example.test"

        def crash_after(method, path, body=None, query=None):
            status, payload = original(method, path, body, query)
            if method == "PATCH" and path == "/customers/41":
                raise AmbiguousWriteError("timeout_after_apply")
            return status, payload

        self.h.transport.request = crash_after
        second = self.h.service.propose("update_customer_primary_email", {"customer_id": 41, "primary_email": "next@example.test"}, IDENTITY)
        reconciled = self._execute(second)
        self.assertTrue(reconciled["ok"], reconciled)
        self.assertTrue(reconciled["ambiguity_reconciled"])
        self.assertEqual(reconciled["retry"], False)
        self.assertEqual(reconciled["readback"]["invoice_email"], "next@example.test")
        patches = len(self._customer_patches())
        self.h.service.execute(second["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(len(self._customer_patches()), patches)

    def test_email_stale_wrong_digest_expiry_and_unverified_get(self) -> None:
        self.h.transport.customers["41"]["invoice_email"] = "old@example.test"
        proposed = self.h.service.propose("update_customer_primary_email", {"customer_id": 41, "primary_email": "ada@example.test"}, IDENTITY)
        self.h.transport.customers["41"]["invoice_email"] = "changed@example.test"
        stale = self._execute(proposed)
        self.assertEqual(stale["gate"], GATE_STALE)
        self.assertEqual(self._customer_patches(), [])

        fresh = self.h.service.propose("update_customer_primary_email", {"customer_id": 41, "primary_email": "ada@example.test"}, IDENTITY)
        token = self.h.approve(fresh["proposal_id"])
        self.h.store._conn.execute("UPDATE proposals SET payload_json = '{}' WHERE proposal_id = ?", (fresh["proposal_id"],))
        altered = self.h.service.execute(fresh["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(altered["gate"], "operator_approval_required")
        self.assertEqual(altered["reason"], "stored_proposal_digest_mismatch")
        self.assertEqual(self._customer_patches(), [])
        stored = self.h.store.get_proposal(fresh["proposal_id"])
        self.h.store.release_open_guard(stored["subject_key"], fresh["proposal_id"])
        self.h.store.set_status(fresh["proposal_id"], "expired")

        expiring = self.h.service.propose("update_customer_primary_email", {"customer_id": 41, "primary_email": "later@example.test"}, IDENTITY)
        expiring_token = self.h.approve(expiring["proposal_id"])
        from datetime import timedelta

        self.h.clock = self.h.clock + timedelta(hours=3)
        expired = self.h.service.execute(expiring["proposal_id"], IDENTITY, operator_approval=expiring_token)
        self.assertEqual(expired["gate"], "approval_or_proposal_expired")
        self.assertEqual(self._customer_patches(), [])

        self.h.clock = self.h.clock - timedelta(hours=3)
        self.h.transport.customers["41"]["invoice_email"] = "old@example.test"
        unverified = self.h.service.propose("update_customer_primary_email", {"customer_id": 41, "primary_email": "ada@example.test"}, IDENTITY)
        original = self.h.transport.request
        patched = {"n": 0}

        def mismatch_get(method, path, body=None, query=None):
            status, payload = original(method, path, body, query)
            if method == "PATCH" and path == "/customers/41":
                patched["n"] += 1
            if method == "GET" and path == "/customers/41" and patched["n"] and isinstance(payload, dict):
                payload = dict(payload)
                payload["invoice_email"] = "wrong@example.test"
            return status, payload

        self.h.transport.request = mismatch_get
        failed = self._execute(unverified)
        self.assertEqual(failed["gate"], GATE_READBACK)
        self.assertEqual(failed["retry"], False)
        self.assertEqual(len(self._customer_patches()), 1)
        self.h.service.execute(unverified["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(len(self._customer_patches()), 1)

    def test_tools_and_gates_match_readiness(self) -> None:
        gates = self.h.service.gates()["operations"]
        self.assertEqual(gates["create_work_order"]["readback_reconciliation"], "immediate_plus_two_reads_no_replay")
        self.assertFalse(gates["create_work_order"]["live_tested"])
        self.assertFalse(self.h.service.gates()["creation_live_tested"])
        email = gates["update_customer_primary_email"]
        self.assertTrue(email["propose"])
        self.assertFalse(email["live_tested"])
        self.assertEqual(email["sole_field"], "invoice_email")
        self.assertEqual(email["location_email_patch"], "not_sent")
        status = gates["update_work_order_status"]
        self.assertTrue(status["propose"])
        self.assertEqual(status["execute_blocked_by"], [])
        self.assertFalse(status["live_tested"])
        self.assertEqual(status["changed_fields"], ["status"])
        self.assertEqual(status["method"], "PATCH")
        self.assertEqual(status["status_value"], "catalog_string")
        self.assertEqual(status["other_fields"], "not_sent")
        self.assertFalse(status["catalog_response_live_verified"])
        self.assertEqual(status["readback_reconciliation"], "immediate_plus_two_reads_no_replay")
        phone = gates["update_customer_phone"]
        self.assertFalse(phone["implemented"])
        self.assertEqual(phone["reason"], "no_verified_billing_phone_patch_helper")
        server = build_mcp(self.h.service, self.h.settings, JwtTokenVerifier(self.h.settings))
        tools = asyncio.run(server.list_tools())
        self.assertEqual(len(tools), 14)
        propose = next(tool for tool in tools if tool.name == "propose_write")
        self.assertEqual(propose.description, PROPOSE_DESCRIPTION)
        text = propose.description
        self.assertIn("at most two more reads", text)
        self.assertIn("update_customer_primary_email", text)
        self.assertIn("update_work_order_status", text)
        self.assertIn("catalog status string", text)
        self.assertIn("update_customer_phone is not implemented", text)
        self.assertIn("not live-tested", text)
        self.assertIn("one PATCH /v3.1/work_orders/{service_appointment_id}", server.instructions)
        self.assertNotIn("update_work_order_status does not execute", server.instructions)
        self.assertIn("no verified billing-phone PATCH", server.instructions)


if __name__ == "__main__":
    unittest.main()
