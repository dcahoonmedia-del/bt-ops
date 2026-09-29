"""Work Pool scheduling sends one sealed public PATCH and reads it back."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone

from bt_fieldwork_write_mcp.allowlist import (
    GATE_IDENTITY,
    GATE_OPERATOR,
    GATE_RECURRING,
    GATE_REPLAY,
    GATE_STALE,
    GATE_WORK_POOL_PRECONDITION,
    OP_WORK_ORDER_SCHEDULE,
    OP_WORK_POOL_SCHEDULE,
    WORK_POOL_PATCH_KEYS,
    WORK_POOL_PUBLIC_API_VERIFIED,
)
from bt_fieldwork_write_mcp.create_contract import _bind_new_residential_name
from bt_fieldwork_write_mcp.digest import proposal_digest
from bt_fieldwork_write_mcp.errors import GateError
from bt_fieldwork_write_mcp.fieldwork import work_pool_readback_decision, work_pool_schedule_body
from bt_fieldwork_write_mcp.schedule import predict_fixed_shift, same_instant
from tests.test_write_mcp import IDENTITY, OTHER, Harness


EASTERN = "2026-09-29T16:00:00-04:00"
UTC = "2026-09-29T20:00:00+00:00"


def _pool(**overrides):
    row = {
        "id": 50268730,
        "service_appointment_id": 8961994,
        "customer_id": 3675473,
        "service_location_id": 4491834,
        "starts_at": "2026-09-29T12:00:00-04:00",
        "duration": 60,
        "service_route_ids": [2557],
        "status": "Work Pool",
        "specific": False,
        "confirmed": False,
        "instructions": "test account",
        "private_notes": "",
        "production_value": 0.0,
        "line_items": [{"name": "Extra Service / Follow-up", "quantity": 1, "price": 0, "payable_id": 38804, "payable_type": "Service"}],
    }
    row.update(overrides)
    return row


class WorkPoolScheduleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness(writes_enabled=True, api_role="writer", mapping_verified=True)
        self.h.transport.add_customer(
            {"id": 3675473, "customer_status": "Active", "name": "Jim Doe"},
            {"id": 4491834, "name": "House", "tax_rate_id": 3, "address": {"id": 1, "notes": "n"}},
        )
        self.h.transport.work_orders["50268730"] = _pool()

    def tearDown(self) -> None:
        self.h.close()

    def _patches(self):
        return [call for call in self.h.transport.calls if call["method"] == "PATCH"]

    def _propose(self, **overrides):
        payload = {
            "work_order_id": 50268730,
            "service_appointment_id": 8961994,
            "starts_at": EASTERN,
            "duration": 60,
            "service_route_ids": [2557],
        }
        payload.update(overrides)
        return self.h.service.propose(OP_WORK_POOL_SCHEDULE, payload, IDENTITY)

    def test_public_body_pairs_ids_and_keeps_the_allowlist(self) -> None:
        prepared = work_pool_schedule_body(8961994, 50268730, EASTERN, 60, [2557], specific=True)
        entry = prepared["body"]["service_appointment"]["appointment_occurrences_attributes"][0]
        self.assertEqual(prepared["method"], "PATCH")
        self.assertEqual(prepared["path"], "/work_orders/8961994")
        self.assertEqual(entry["id"], "50268730")
        self.assertEqual(tuple(entry), WORK_POOL_PATCH_KEYS)
        self.assertEqual(entry["specific"], True)
        self.assertNotIn("status", entry)
        self.assertNotIn("confirmed", entry)
        self.assertNotIn("instructions", entry)
        self.assertNotIn("private_notes", entry)
        self.assertNotIn("use_time_window", entry)
        self.assertNotIn("time_window_kind", entry)
        self.assertNotIn("frequency", entry)
        self.assertNotIn("startDate", entry)
        with self.assertRaises(GateError) as denied:
            work_pool_schedule_body(8961994, 50268730, EASTERN, 60, [2557], specific=False)
        self.assertEqual(denied.exception.gate, GATE_WORK_POOL_PRECONDITION)
        before = len(self.h.transport.calls)
        with self.assertRaises(GateError) as ordinary:
            self.h.client.patch_work_order_fields(
                {"work_order_id": "50268730", "service_appointment_id": "8961994"},
                {"specific": True, "starts_at": EASTERN},
                ["starts_at", "specific"],
            )
        self.assertEqual(ordinary.exception.gate, "unknown_field")
        self.assertEqual(len(self.h.transport.calls), before)

    def test_specific_true_is_only_the_work_pool_proposal(self) -> None:
        blocked = self.h.service.propose(
            OP_WORK_ORDER_SCHEDULE,
            {"work_order_id": 50268730, "service_appointment_id": 8961994, "starts_at": EASTERN, "duration": 60, "service_route_ids": [2557]},
            IDENTITY,
        )
        self.assertEqual(blocked["gate"], "schedule_coupling_unverified")
        self.assertEqual(self._patches(), [])
        proposed = self._propose()
        self.assertTrue(proposed["ok"], proposed)
        self.assertEqual(proposed["intent"], "work_pool_to_scheduled_time")
        self.assertEqual(proposed["before"]["specific"], False)
        self.assertEqual(proposed["before"]["status"], "Work Pool")
        self.assertFalse(proposed["before"]["repeat_type_present"])
        self.assertFalse(proposed["repeat_type_verified"])
        self.assertEqual(proposed["after"]["specific"], True)
        self.assertFalse(proposed["after"]["status_sent"])
        self.assertEqual(proposed["after"]["browser_observed_status_after"], "Scheduled")
        self.assertEqual(proposed["after"]["public_api_status_equivalence"], "server_computed_not_sent")
        self.assertEqual(proposed["after"]["status_after"], "Scheduled")
        self.assertEqual(proposed["after"]["arrival_window"], "server_computed")
        self.assertEqual(proposed["after"]["arrival_mode"], "unknown")
        self.assertFalse(proposed["after"]["arrival_mode_known"])
        self.assertFalse(proposed["after"]["arrival_window_promised"])
        self.assertTrue(proposed["after"]["live_execution_available"])
        self.assertNotIn("schedule_model", proposed["after"])
        self.assertNotIn("fixed_window_id", proposed["after"])
        entry = proposed["after"]["patch"]["body"]["service_appointment"]["appointment_occurrences_attributes"][0]
        self.assertEqual(entry["specific"], True)
        self.assertEqual(tuple(entry), WORK_POOL_PATCH_KEYS)
        self.assertEqual(self._patches(), [])
        extra = self._propose(specific=True)
        self.assertEqual(extra["gate"], "unknown_field")
        self.assertIn("specific", extra["fields"])

    def test_altered_ids_digest_stale_state_and_missing_approval_do_not_write(self) -> None:
        proposed = self._propose()
        self.assertTrue(proposed["ok"], proposed)
        missing = self.h.service.execute(proposed["proposal_id"], IDENTITY)
        self.assertEqual(missing["gate"], GATE_OPERATOR)
        self.assertEqual(self._patches(), [])
        token = self.h.approve(proposed["proposal_id"])
        self.h.store._conn.execute("UPDATE proposals SET payload_json = '{}' WHERE proposal_id = ?", (proposed["proposal_id"],))
        altered = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(altered["reason"], "stored_proposal_digest_mismatch")
        self.assertEqual(self._patches(), [])
        stored = self.h.store.get_proposal(proposed["proposal_id"])
        self.h.store.release_open_guard(stored["subject_key"], proposed["proposal_id"])
        self.h.store.set_status(proposed["proposal_id"], "expired")

        moved = self._propose()
        self.h.transport.work_orders["50268730"]["service_appointment_id"] = 1
        moved_token = self.h.approve(moved["proposal_id"])
        identity = self.h.service.execute(moved["proposal_id"], IDENTITY, operator_approval=moved_token)
        self.assertEqual(identity["gate"], GATE_IDENTITY)
        self.assertFalse(identity["write_sent"])
        self.assertEqual(self._patches(), [])
        self.h.transport.work_orders["50268730"]["service_appointment_id"] = 8961994
        self.h.store.release_open_guard(f"work_order:50268730", moved["proposal_id"])
        self.h.store.set_status(moved["proposal_id"], "expired")

        stale_specific = self._propose()
        self.h.transport.work_orders["50268730"]["specific"] = True
        specific_token = self.h.approve(stale_specific["proposal_id"])
        specific = self.h.service.execute(stale_specific["proposal_id"], IDENTITY, operator_approval=specific_token)
        self.assertEqual(specific["gate"], GATE_STALE)
        self.assertIn("specific", specific["changed_fields"])
        self.assertEqual(self._patches(), [])
        self.h.transport.work_orders["50268730"]["specific"] = False
        self.h.store.release_open_guard(f"work_order:50268730", stale_specific["proposal_id"])
        self.h.store.set_status(stale_specific["proposal_id"], "expired")

        stale_status = self._propose()
        self.h.transport.work_orders["50268730"]["status"] = "Scheduled"
        status_token = self.h.approve(stale_status["proposal_id"])
        status = self.h.service.execute(stale_status["proposal_id"], IDENTITY, operator_approval=status_token)
        self.assertEqual(status["gate"], GATE_STALE)
        self.assertIn("status", status["changed_fields"])
        self.assertEqual(self._patches(), [])

    def test_utc_and_eastern_are_the_same_approved_instant(self) -> None:
        self.assertTrue(same_instant(UTC, EASTERN))
        eastern = self._propose()
        self.assertTrue(eastern["ok"], eastern)
        self.h.store.release_open_guard(f"work_order:50268730", eastern["proposal_id"])
        self.h.store.set_status(eastern["proposal_id"], "expired")
        utc = self._propose(starts_at=UTC)
        self.assertTrue(utc["ok"], utc)
        self.assertTrue(same_instant(eastern["after"]["starts_at"], utc["after"]["starts_at"]))
        self.assertTrue(same_instant(utc["after"]["starts_at"], EASTERN))
        blob = str(utc["after"]["patch"])
        self.assertNotIn("2026-09-29 20:00", blob)
        self.assertNotIn("startDate", blob)
        naive = self._propose(starts_at="2026-09-29 20:00")
        self.assertEqual(naive["gate"], "unknown_field")

    def test_protected_field_mismatch_fails_and_omitted_arrival_is_not_fixed_mode(self) -> None:
        called = {"n": 0}
        original = predict_fixed_shift

        def boom(*args, **kwargs):
            called["n"] += 1
            return original(*args, **kwargs)

        import bt_fieldwork_write_mcp.schedule as schedule_module

        schedule_module.predict_fixed_shift = boom
        try:
            proposed = self._propose()
        finally:
            schedule_module.predict_fixed_shift = original
        self.assertTrue(proposed["ok"], proposed)
        self.assertEqual(called["n"], 0)
        self.assertFalse(proposed["before"]["time_window_kind_present"])
        self.assertIsNone(proposed["before"]["arrival_time_window"])
        self.assertEqual(proposed["arrival_mode"], "unknown")
        self.h.transport.work_orders["50268730"]["instructions"] = "changed"
        token = self.h.approve(proposed["proposal_id"])
        stale = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(stale["gate"], GATE_STALE)
        self.assertIn("instructions", stale["changed_fields"])
        self.assertEqual(self._patches(), [])
        self.h.transport.work_orders["50268730"]["instructions"] = "test account"
        self.h.store.release_open_guard("work_order:50268730", proposed["proposal_id"])
        self.h.store.set_status(proposed["proposal_id"], "expired")

        self.h.transport.work_orders["50268731"] = _pool(
            id=50268731,
            service_appointment_id=8961995,
            arrival_time_window=["2026-09-29T16:00:00-04:00", "2026-09-29T17:00:00-04:00"],
            arrival_time_window_start="16:00",
            arrival_time_window_end="17:00",
        )
        matched = self.h.service.propose(
            OP_WORK_POOL_SCHEDULE,
            {"work_order_id": 50268731, "service_appointment_id": 8961995, "starts_at": EASTERN, "duration": 60, "service_route_ids": [2557]},
            IDENTITY,
        )
        self.assertTrue(matched["ok"], matched)
        self.assertEqual(matched["after"]["arrival_mode"], "unknown")
        self.assertNotIn("schedule_model", matched["after"])
        ordinary = self.h.service.propose(
            OP_WORK_ORDER_SCHEDULE,
            {"work_order_id": 50268731, "service_appointment_id": 8961995, "starts_at": EASTERN, "duration": 60, "service_route_ids": [2557]},
            IDENTITY,
        )
        self.assertEqual(ordinary["gate"], "schedule_coupling_unverified")

        priced = self._propose()
        live = dict(priced["before"])
        live["specific"] = True
        live["starts_at"] = priced["after"]["starts_at"]
        live["status"] = "Scheduled"
        live["line_items"] = [{"name": "Extra Service / Follow-up", "quantity": 1, "price": 12, "payable_id": 38804, "payable_type": "Service"}]
        decision = work_pool_readback_decision(priced["before"], priced["after"], live)
        self.assertFalse(decision["ok"])
        self.assertFalse(decision["write_again"])
        self.assertFalse(decision["retry"])
        self.assertEqual(decision["mismatches"][0]["field"], "line_items")
        self.assertFalse(decision["arrival_mode_proof"])

    def test_ambiguous_or_repeated_execution_never_patches(self) -> None:
        self.assertTrue(WORK_POOL_PUBLIC_API_VERIFIED)
        proposed = self._propose()
        token = self.h.approve(proposed["proposal_id"])
        stranger = self.h.service.execute(proposed["proposal_id"], OTHER, operator_approval=token)
        self.assertEqual(stranger["gate"], GATE_IDENTITY)
        self.h.transport.write_mode = "ambiguous"
        blocked = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(blocked["gate"], "readback_unresolved")
        self.assertFalse(blocked["retry"])
        self.assertFalse(blocked["write_again"])
        self.assertEqual(len(self._patches()), 1)
        again = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(again["gate"], "ambiguous_remote_write_no_retry")
        self.assertEqual(len(self._patches()), 1)
        self.assertEqual(self.h.store.get_proposal(proposed["proposal_id"])["status"], "ambiguous")
        missing = work_pool_readback_decision(proposed["before"], proposed["after"], None)
        self.assertFalse(missing["write_again"])
        self.assertFalse(missing["retry"])
        self.assertFalse(missing["arrival_mode_proof"])
        observed = dict(proposed["before"])
        observed["specific"] = True
        observed["starts_at"] = proposed["after"]["starts_at"]
        observed["status"] = "Scheduled"
        observed["arrival_time_window"] = ["2026-09-29T16:00:00-04:00", "2026-09-29T17:00:00-04:00"]
        accepted = work_pool_readback_decision(proposed["before"], proposed["after"], observed)
        self.assertTrue(accepted["ok"], accepted)
        self.assertEqual(accepted["status_coupling"], "server_computed_not_sent")
        self.assertEqual(accepted["arrival_mode"], "unknown")
        self.assertFalse(accepted["arrival_window_promised"])
        self.assertFalse(accepted["arrival_mode_proof"])
        self.assertFalse(accepted["write_again"])
        self.assertFalse(accepted["recurrence_verified"])
        self.assertFalse(accepted["repeat_type_verified"])
        self.assertEqual(accepted["recurrence_reason"], "occurrence_get_omits_repeat_type")

    def test_recurrence_evidence_is_preserved_and_explicit_changes_fail(self) -> None:
        proposed = self._propose()
        self.assertTrue(proposed["ok"], proposed)
        evidence = proposed["before"]["recurrence"]
        self.assertFalse(evidence["verified"])
        self.assertIsNone(evidence["repeat_type"])
        self.assertEqual(evidence["reason"], "occurrence_get_omits_repeat_type")
        self.assertEqual(evidence["authoritative_source"], "not_in_documented_get")
        self.assertFalse(proposed["repeat_type_verified"])
        self.assertIsNone(proposed["before"]["recurring"])
        self.assertIsNone(proposed["before"]["series_id"])
        self.assertIsNone(proposed["before"]["appointment_occurrence_count"])
        observed = dict(proposed["before"])
        observed["specific"] = True
        observed["starts_at"] = proposed["after"]["starts_at"]
        observed["status"] = "Scheduled"
        missing = work_pool_readback_decision(proposed["before"], proposed["after"], observed)
        self.assertTrue(missing["ok"], missing)
        self.assertFalse(missing["recurrence_verified"])
        self.assertFalse(missing["repeat_type_verified"])
        self.assertEqual(missing["recurrence_reason"], "occurrence_get_omits_repeat_type")

        monthly = dict(observed)
        monthly["repeat_type"] = "monthly"
        changed = work_pool_readback_decision(proposed["before"], proposed["after"], monthly)
        self.assertFalse(changed["ok"])
        self.assertEqual(changed["gate"], GATE_RECURRING)
        self.assertFalse(changed["write_again"])
        self.assertFalse(changed["retry"])
        self.assertFalse(changed["recurrence_verified"])
        self.assertIn("repeat_type", {item["field"] for item in changed["mismatches"]})

        recurring = dict(observed)
        recurring["recurring"] = True
        recurring_decision = work_pool_readback_decision(proposed["before"], proposed["after"], recurring)
        self.assertEqual(recurring_decision["gate"], GATE_RECURRING)
        self.assertFalse(recurring_decision["write_again"])

        series = dict(observed)
        series["series_id"] = 44
        series["appointment_occurrences"] = [{"id": 1}, {"id": 2}]
        series_decision = work_pool_readback_decision(proposed["before"], proposed["after"], series)
        self.assertEqual(series_decision["gate"], GATE_RECURRING)
        self.assertFalse(series_decision["write_again"])
        self.assertEqual(self._patches(), [])

        self.h.store.release_open_guard("work_order:50268730", proposed["proposal_id"])
        self.h.store.set_status(proposed["proposal_id"], "expired")
        self.h.transport.work_orders["50268732"] = _pool(
            id=50268732,
            service_appointment_id=8961996,
            repeat_type="none",
            recurring=False,
            series_id=None,
            appointment_occurrences=[{"id": 50268732}],
        )
        known = self.h.service.propose(
            OP_WORK_POOL_SCHEDULE,
            {"work_order_id": 50268732, "service_appointment_id": 8961996, "starts_at": EASTERN, "duration": 60, "service_route_ids": [2557]},
            IDENTITY,
        )
        self.assertTrue(known["ok"], known)
        self.assertTrue(known["before"]["recurrence"]["verified"])
        self.assertEqual(known["before"]["repeat_type"], "none")
        self.assertEqual(known["before"]["recurring"], False)
        self.assertIsNone(known["before"]["series_id"])
        self.assertEqual(known["before"]["appointment_occurrence_count"], 1)
        self.assertTrue(known["repeat_type_verified"])
        known_live = deepcopy(known["before"])
        known_live["specific"] = True
        known_live["starts_at"] = known["after"]["starts_at"]
        known_live["recurrence"] = dict(known_live["recurrence"])
        known_live["recurrence"]["repeat_type"] = "monthly"
        known_live["recurrence"]["verified"] = False
        known_live["repeat_type"] = "monthly"
        rejected = work_pool_readback_decision(known["before"], known["after"], known_live)
        self.assertEqual(rejected["gate"], GATE_RECURRING)
        self.assertFalse(rejected["recurrence_verified"])
        self.assertFalse(rejected["write_again"])

    def test_chatgpt_confirmation_blocks_once_without_another_write(self) -> None:
        self.h.service.settings = replace(
            self.h.settings,
            writes_enabled=True,
            mapping_verified=True,
            approval_mode="chatgpt_confirmation",
        )
        proposed = self._propose()
        self.assertTrue(proposed["ok"], proposed)
        digest = proposed["digest"]
        wrong = self.h.service.execute(proposed["proposal_id"], IDENTITY, approved=True, expected_digest="0" * 64)
        self.assertEqual(wrong["gate"], GATE_OPERATOR)
        self.assertEqual(wrong["reason"], "explicit_confirmation_and_exact_digest_required")
        self.assertEqual(self.h.store.get_proposal(proposed["proposal_id"])["status"], "proposed")
        guard = self.h.store._conn.execute(
            "SELECT state FROM subject_guards WHERE proposal_id = ?",
            (proposed["proposal_id"],),
        ).fetchone()
        self.assertEqual(guard["state"], "open")
        self.assertEqual(self._approval_count(proposed["proposal_id"]), 0)
        self.assertEqual(self._patches(), [])

        done = self.h.service.execute(proposed["proposal_id"], IDENTITY, approved=True, expected_digest=digest)
        self.assertTrue(done["ok"], done)
        self.assertEqual(len(self._patches()), 1)
        stored = self.h.store.get_proposal(proposed["proposal_id"])
        self.assertEqual(stored["status"], "executed")
        self.assertEqual(stored["digest"], digest)
        self.assertEqual(stored["after"], proposed["after"])
        released = self.h.store._conn.execute(
            "SELECT state FROM subject_guards WHERE subject_key = ?",
            ("work_order:50268730",),
        ).fetchone()
        self.assertIsNone(released)
        self.assertEqual(self._approval_count(proposed["proposal_id"]), 1)
        used_at = self._approval_used_at(proposed["proposal_id"])
        self.assertIsNotNone(used_at)

        again = self.h.service.execute(proposed["proposal_id"], IDENTITY, approved=True, expected_digest=digest)
        self.assertEqual(again["gate"], GATE_REPLAY)
        self.assertEqual(self.h.store.get_proposal(proposed["proposal_id"])["status"], "executed")
        self.assertEqual(self.h.store.get_proposal(proposed["proposal_id"])["digest"], digest)
        self.assertEqual(self._approval_count(proposed["proposal_id"]), 1)
        self.assertEqual(self._approval_used_at(proposed["proposal_id"]), used_at)
        self.assertEqual(len(self._patches()), 1)
        self.h.transport.work_orders["50268730"] = _pool()
        replacement = self._propose()
        self.assertTrue(replacement["ok"], replacement)
        self.assertNotEqual(replacement.get("gate"), "duplicate_in_flight")

    def _approval_count(self, proposal_id: str) -> int:
        row = self.h.store._conn.execute("SELECT COUNT(*) AS n FROM approvals WHERE proposal_id = ?", (proposal_id,)).fetchone()
        return int(row["n"])

    def _approval_used_at(self, proposal_id: str):
        row = self.h.store._conn.execute("SELECT used_at FROM approvals WHERE proposal_id = ?", (proposal_id,)).fetchone()
        return None if row is None else row["used_at"]

    def _execute(self, proposed: dict):
        token = self.h.approve(proposed["proposal_id"])
        return self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)

    def test_verified_fixture_sends_one_patch_and_reads_it_back(self) -> None:
        proposed = self._propose()
        self.assertTrue(proposed["ok"], proposed)
        digest = proposed["digest"]
        done = self._execute(proposed)
        self.assertTrue(done["ok"], done)
        patches = self._patches()
        self.assertEqual(len(patches), 1)
        sent = patches[0]
        self.assertEqual(sent["path"], "/work_orders/8961994")
        self.assertEqual(sent["body"], proposed["after"]["patch"]["body"])
        entry = sent["body"]["service_appointment"]["appointment_occurrences_attributes"][0]
        self.assertEqual(tuple(entry), WORK_POOL_PATCH_KEYS)
        self.assertNotIn("status", entry)
        self.assertNotIn("confirmed", entry)
        self.assertNotIn("arrival_time_window", entry)
        readback = done["readback"]
        self.assertEqual(readback["work_order_id"], "50268730")
        self.assertEqual(readback["service_appointment_id"], "8961994")
        self.assertEqual(readback["customer_id"], "3675473")
        self.assertEqual(readback["location_id"], "4491834")
        self.assertNotIn("service_location_id", readback)
        self.assertTrue(readback["specific"])
        self.assertTrue(same_instant(readback["starts_at"], EASTERN))
        self.assertEqual(readback["duration"], 60)
        self.assertEqual(readback["service_route_ids"], [2557])
        self.assertEqual(readback["status"], "Scheduled")
        self.assertEqual(readback["instructions"], "test account")
        self.assertEqual(readback["private_notes"], "")
        self.assertEqual(readback["production_value"], 0.0)
        self.assertIs(readback["confirmed"], False)
        self.assertEqual(readback["line_items"][0]["payable_id"], 38804)
        self.assertEqual(readback["line_items"][0]["price"], 0)
        self.assertEqual(done["status_observed"], "Scheduled")
        self.assertFalse(done["status_sent"])
        self.assertEqual(done["status_coupling"], "server_computed_not_sent")
        self.assertEqual(done["arrival_window"], "server_computed")
        self.assertEqual(done["arrival_mode"], "unknown")
        self.assertFalse(done["arrival_mode_known"])
        self.assertFalse(done["arrival_window_promised"])
        self.assertNotIn("schedule_model", done)
        self.assertNotIn("fixed_window_id", done)
        self.assertIn("arrival_time_window", done["arrival_observed"])
        self.assertFalse(done["recurrence_verified"])
        self.assertEqual(done["recurrence_reason"], "occurrence_get_omits_repeat_type")
        stored = self.h.store.get_proposal(proposed["proposal_id"])
        self.assertEqual(stored["status"], "executed")
        self.assertEqual(stored["digest"], digest)
        self.assertEqual(stored["after"], proposed["after"])
        guard = self.h.store._conn.execute(
            "SELECT state FROM subject_guards WHERE subject_key = ?",
            ("work_order:50268730",),
        ).fetchone()
        self.assertIsNone(guard)
        again = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(again["gate"], GATE_REPLAY)
        self.assertEqual(len(self._patches()), 1)
        self.assertEqual(self.h.store.get_proposal(proposed["proposal_id"])["digest"], digest)

    def test_raw_location_and_occurrence_ids_normalize_before_compare(self) -> None:
        snap = self.h.service._work_pool_snapshot(_pool())
        self.assertEqual(snap["location_id"], "4491834")
        self.assertEqual(snap["work_order_id"], "50268730")
        self.assertNotIn("service_location_id", snap)
        proposed = self._propose()
        live = dict(proposed["before"])
        live.pop("location_id")
        live.pop("work_order_id")
        live["service_location_id"] = 4491834
        live["id"] = 50268730
        live["specific"] = True
        live["starts_at"] = proposed["after"]["starts_at"]
        live["status"] = "Scheduled"
        decision = work_pool_readback_decision(proposed["before"], proposed["after"], live)
        self.assertTrue(decision["ok"], decision)
        self.assertEqual(decision["arrival_mode"], "unknown")
        self.assertFalse(decision["arrival_window_promised"])

    def test_omitted_finished_at_uses_start_plus_duration(self) -> None:
        self.h.transport.omit_finished_at_on_work_order_get = True
        proposed = self._propose()
        done = self._execute(proposed)
        self.assertTrue(done["ok"], done)
        self.assertIsNone(done["finished_at"])
        self.assertEqual(done["finished_at_on_occurrence_get"], "omitted")
        self.assertEqual(done["scheduled_end"], "2026-09-29T17:00:00-04:00")
        self.assertEqual(len(self._patches()), 1)

    def test_http_204_is_one_patch_then_authoritative_get(self) -> None:
        self.h.transport.write_mode = "http_204"
        proposed = self._propose()
        done = self._execute(proposed)
        self.assertTrue(done["ok"], done)
        self.assertEqual(len(self._patches()), 1)
        self.assertEqual(done["readback"]["status"], "Scheduled")
        self.assertTrue(done["readback"]["specific"])
        self.assertTrue(same_instant(done["readback"]["starts_at"], EASTERN))
        gets = [call for call in self.h.transport.calls if call["method"] == "GET" and call["path"] == "/work_orders/50268730"]
        self.assertGreaterEqual(len(gets), 1)

    def test_readback_mismatch_stays_unresolved_without_another_patch(self) -> None:
        original = self.h.transport.request

        def diverge_after_patch(method, path, body=None, query=None):
            if method == "GET" and any(call["method"] == "PATCH" for call in self.h.transport.calls):
                self.h.transport.readback_line_price = 12
            return original(method, path, body, query)

        self.h.transport.request = diverge_after_patch
        proposed = self._propose()
        digest = proposed["digest"]
        done = self._execute(proposed)
        self.assertFalse(done["ok"])
        self.assertEqual(done["gate"], "readback_unresolved")
        self.assertFalse(done["retry"])
        self.assertFalse(done["write_again"])
        self.assertEqual(done["mismatches"][0]["field"], "line_items")
        self.assertEqual(len(self._patches()), 1)
        self.assertEqual(self.h.store.get_proposal(proposed["proposal_id"])["status"], "ambiguous")
        self.assertEqual(self.h.store.get_proposal(proposed["proposal_id"])["digest"], digest)
        again = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(again["gate"], "ambiguous_remote_write_no_retry")
        self.assertEqual(len(self._patches()), 1)

    def test_explicit_recurrence_conflict_after_patch_is_not_replayed(self) -> None:
        original = self.h.transport.request

        def reveal_monthly(method, path, body=None, query=None):
            result = original(method, path, body, query)
            if method == "PATCH":
                self.h.transport.work_orders["50268730"]["repeat_type"] = "monthly"
            return result

        self.h.transport.request = reveal_monthly
        proposed = self._propose()
        done = self._execute(proposed)
        self.assertEqual(done["gate"], GATE_RECURRING)
        self.assertFalse(done["write_again"])
        self.assertFalse(done["retry"])
        self.assertFalse(done["recurrence_verified"])
        self.assertEqual(len(self._patches()), 1)
        self.assertEqual(self.h.store.get_proposal(proposed["proposal_id"])["status"], "ambiguous")
        again = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(again["gate"], "ambiguous_remote_write_no_retry")
        self.assertEqual(len(self._patches()), 1)

    def test_already_rejected_and_pre_verification_seals_do_not_write(self) -> None:
        rejected = self._propose()
        digest = rejected["digest"]
        after = deepcopy(rejected["after"])
        token = self.h.approve(rejected["proposal_id"])
        self.h.store.set_status(rejected["proposal_id"], "rejected")
        blocked = self.h.service.execute(rejected["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(blocked["gate"], GATE_REPLAY)
        self.assertEqual(blocked["proposal_status"], "rejected")
        self.assertFalse(blocked["write_sent"])
        stored = self.h.store.get_proposal(rejected["proposal_id"])
        self.assertEqual(stored["status"], "rejected")
        self.assertEqual(stored["digest"], digest)
        self.assertEqual(stored["after"], after)
        self.assertEqual(self._patches(), [])

        self.h.store.release_open_guard("work_order:50268730", rejected["proposal_id"])
        historical = self._propose()
        row = self.h.store.get_proposal(historical["proposal_id"])
        old_after = deepcopy(row["after"])
        old_after["live_execution_available"] = False
        old_digest = proposal_digest(
            proposal_id=row["proposal_id"],
            operation=row["operation"],
            identity=row["identity"],
            target=row["subject_key"],
            before=row["before"],
            after=old_after,
            payload=row["payload"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
        )
        self.h.store._conn.execute(
            "UPDATE proposals SET after_json = ?, digest = ? WHERE proposal_id = ?",
            (json.dumps(old_after), old_digest, historical["proposal_id"]),
        )
        historical_token = self.h.approve(historical["proposal_id"])
        predates = self.h.service.execute(historical["proposal_id"], IDENTITY, operator_approval=historical_token)
        self.assertEqual(predates["gate"], GATE_REPLAY)
        self.assertEqual(predates["reason"], "sealed_proposal_predates_verified_execution")
        self.assertFalse(predates["write_sent"])
        sealed = self.h.store.get_proposal(historical["proposal_id"])
        self.assertEqual(sealed["status"], "rejected")
        self.assertEqual(sealed["digest"], old_digest)
        self.assertFalse(sealed["after"]["live_execution_available"])
        self.assertEqual(self._patches(), [])
        repeated = self.h.service.execute(historical["proposal_id"], IDENTITY, operator_approval=historical_token)
        self.assertEqual(repeated["gate"], GATE_REPLAY)
        self.assertEqual(self.h.store.get_proposal(historical["proposal_id"])["digest"], old_digest)
        self.assertEqual(self._patches(), [])

    def test_existing_schedule_status_and_customer_paths_stay_unchanged(self) -> None:
        self.h.service._now = lambda: datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        self.h.transport.customers["644133"] = {"id": 644133, "customer_status": "Active", "name": "Tim"}
        self.h.transport.locations["644133:727573"] = {
            "id": 727573, "customer_id": 644133, "name": "House", "tax_rate_id": 3, "address": {"id": 1, "notes": "n"},
        }
        self.h.transport.work_orders["8210560"] = {
            "id": 8210560,
            "service_appointment_id": 1501269,
            "customer_id": 644133,
            "service_location_id": 727573,
            "starts_at": "2026-09-25T14:00:00-04:00",
            "duration": 60,
            "service_route_ids": [2557],
            "instructions": "gate",
            "private_notes": "secret",
            "specific": True,
            "confirmed": False,
            "status": "Today - Anytime",
        }
        scheduled = self.h.service.propose(
            OP_WORK_ORDER_SCHEDULE,
            {"work_order_id": "8210560", "service_appointment_id": "1501269", "starts_at": "2026-09-25T13:00:00-04:00", "duration": 60, "service_route_ids": [2557]},
            IDENTITY,
        )
        self.assertTrue(scheduled["ok"], scheduled)
        self.assertEqual(scheduled["patch_fields"], ["starts_at", "duration", "service_route_ids"])
        self.assertFalse(scheduled["specific_sent"])
        self.assertEqual(scheduled["fixed_window_id"], 595)
        approved = self.h.approve(scheduled["proposal_id"])
        done = self.h.service.execute(scheduled["proposal_id"], IDENTITY, operator_approval=approved)
        self.assertTrue(done["ok"], done)
        schedule_patch = [call for call in self._patches() if call["path"] == "/work_orders/1501269"]
        self.assertEqual(len(schedule_patch), 1)
        occurrence = schedule_patch[0]["body"]["service_appointment"]["appointment_occurrences_attributes"][0]
        self.assertEqual(set(occurrence), {"id", "starts_at", "duration", "service_route_ids"})

        self.h.transport.work_orders["8210"] = {
            "id": 8210,
            "service_appointment_id": 1501,
            "customer_id": 41,
            "service_location_id": 77,
            "starts_at": "2026-09-28T11:30:00-04:00",
            "duration": 60,
            "service_route_ids": [2557],
            "status": "Scheduled",
            "instructions": "gate",
            "private_notes": "keep",
            "repeat_type": "none",
            "production_value": "150.0",
            "specific": True,
            "confirmed": False,
            "line_items": [{"name": "PestGuard - Set-up", "price": "150.0", "quantity": 1, "payable_id": 38814, "payable_type": "Service"}],
        }
        status = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8210, "service_appointment_id": 1501, "status": "Flagged"},
            IDENTITY,
        )
        self.assertTrue(status["ok"], status)
        self.assertEqual(status["changed_fields"], ["status"])
        status_token = self.h.approve(status["proposal_id"])
        status_done = self.h.service.execute(status["proposal_id"], IDENTITY, operator_approval=status_token)
        self.assertTrue(status_done["ok"], status_done)
        status_patch = [call for call in self._patches() if call["path"] == "/work_orders/1501"]
        self.assertEqual(len(status_patch), 1)
        status_entry = status_patch[0]["body"]["service_appointment"]["appointment_occurrences_attributes"][0]
        self.assertEqual(set(status_entry), {"id", "status"})
        self.assertNotIn("specific", status_entry)

        with self.assertRaises(GateError) as conflict:
            _bind_new_residential_name({"name": "Other Person"}, {"first_name": "Jim", "last_name": "Doe"})
        self.assertEqual(conflict.exception.gate, "residential_name_conflict")
        self.assertFalse(conflict.exception.detail["write_sent"])
        gates = self.h.service.gates()["operations"]["schedule_work_pool_occurrence"]
        self.assertTrue(gates["live_execution_available"])
        self.assertTrue(gates["execute"])
        self.assertNotIn("work_pool_public_api_unverified", gates["execute_blocked_by"])
        self.assertFalse(gates["status_sent"])
        self.assertFalse(gates["arrival_mode_known"])
        self.assertFalse(gates["arrival_window_promised"])
        self.assertEqual(gates["arrival_window"], "server_computed")
