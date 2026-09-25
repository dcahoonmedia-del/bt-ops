"""Fixed windows follow start time only when occurrence evidence is fresh."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timezone

from bt_fieldwork_write_mcp.allowlist import OP_WORK_ORDER_SCHEDULE
from bt_fieldwork_write_mcp.schedule import OCCURRENCE_FORM_FIELD, OccurrenceEvidence
from tests.test_write_mcp import IDENTITY, Harness


def _live_before() -> dict:
    return {
        "id": 8210560,
        "service_appointment_id": 1501269,
        "customer_id": 644133,
        "service_location_id": 727573,
        "starts_at": "2026-09-25T14:00:00-04:00",
        "duration": 60,
        "service_route_ids": [2557],
        "arrival_time_window": ["2026-09-25T14:00:00.000-04:00", "2026-09-25T15:00:00.000-04:00"],
        "arrival_time_window_start": "14:00",
        "arrival_time_window_end": "15:00",
        "instructions": "gate",
        "private_notes": "secret",
        "specific": True,
        "locked": False,
        "confirmed": False,
        "status": "Today - Anytime",
    }


class ScheduleReadbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness(writes_enabled=True, api_role="writer", mapping_verified=True)
        self.h.service.settings = replace(self.h.settings, writes_enabled=True, mapping_verified=True, approval_mode="chatgpt_confirmation")
        self.h.service._now = lambda: datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        self.h.transport.customers["644133"] = {"id": 644133, "customer_status": "Active", "name": "Tim"}
        self.h.transport.locations["644133:727573"] = {
            "id": 727573, "customer_id": 644133, "name": "House", "tax_rate_id": 3, "address": {"id": 1, "notes": "n"},
        }
        self.h.transport.work_orders["8210560"] = _live_before()

    def tearDown(self) -> None:
        self.h.close()

    def _propose(self, **overrides):
        payload = {"work_order_id": "8210560", "service_appointment_id": "1501269", "starts_at": "2026-09-25T13:00:00-04:00", "duration": 60, "service_route_ids": [2557]}
        payload.update(overrides)
        return self.h.service.propose(OP_WORK_ORDER_SCHEDULE, payload, IDENTITY)

    def test_fixed_window_follows_start_not_duration(self) -> None:
        proposed = self._propose()
        self.assertTrue(proposed["ok"], proposed)
        self.assertEqual(proposed["arrival_coupling"], "fixed_window_selected_by_start")
        self.assertEqual(proposed["fixed_window_id"], 595)
        self.assertEqual(proposed["occurrence_evidence_field"], OCCURRENCE_FORM_FIELD)
        self.assertEqual(proposed["predicted_changes"]["arrival_time_window_start"], "13:00")
        self.assertEqual(proposed["predicted_changes"]["arrival_time_window_end"], "14:00")
        self.assertNotIn("time_window_kind", proposed["before"])
        longer = self._propose(duration=90, starts_at="2026-09-25T13:30:00-04:00")
        self.assertEqual(longer["predicted_changes"]["arrival_time_window_start"], "13:00")
        self.assertEqual(longer["predicted_changes"]["ends_at"], "2026-09-25T15:00:00-04:00")
        half = self._propose(starts_at="2026-09-25T14:30:00-04:00", duration=15)
        self.assertEqual(half["fixed_window_id"], 596)
        self.assertEqual(half["predicted_changes"]["arrival_time_window_end"], "15:00")

    def test_missing_stale_manual_and_outside_windows_are_visible(self) -> None:
        self.h.transport.work_orders["8210560"]["time_window_kind"] = "1"
        other = dict(_live_before())
        other["id"] = 50
        other["service_appointment_id"] = 51
        self.h.transport.work_orders["50"] = other
        missing = self.h.service.propose(OP_WORK_ORDER_SCHEDULE, {"work_order_id": "50", "service_appointment_id": "51", "starts_at": "2026-09-25T13:00:00-04:00", "duration": 60, "service_route_ids": [2557]}, IDENTITY)
        self.assertEqual(missing["gate"], "schedule_coupling_unverified")
        self.assertIn("time_window_kind", missing["reason"])
        self.h.service._now = lambda: datetime(2026, 9, 27, tzinfo=timezone.utc)
        stale = self._propose()
        self.assertIn("stale", stale["reason"])
        self.h.service._now = lambda: datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        manual = OccurrenceEvidence("50", "51", "644133", "727573", "manual", "4")
        self.h.service.window_evidence = self.h.service.window_evidence.with_occurrence(manual)
        blocked = self.h.service.propose(OP_WORK_ORDER_SCHEDULE, {"work_order_id": "50", "service_appointment_id": "51", "starts_at": "2026-09-25T13:00:00-04:00", "duration": 60, "service_route_ids": [2557]}, IDENTITY)
        self.assertIn("manual", blocked["reason"])
        outside = self._propose(starts_at="2026-09-25T07:30:00-04:00")
        self.assertIn("outside", outside["reason"])
        self.assertFalse(any(call["method"] == "PATCH" for call in self.h.transport.calls))

    def test_another_occurrence_uses_the_same_rule(self) -> None:
        other = dict(_live_before())
        other["id"] = 77
        other["service_appointment_id"] = 78
        self.h.transport.work_orders["77"] = other
        self.h.service.window_evidence = self.h.service.window_evidence.with_occurrence(OccurrenceEvidence("77", "78", "644133", "727573", "fixed", "1"))
        proposed = self.h.service.propose(OP_WORK_ORDER_SCHEDULE, {"work_order_id": "77", "service_appointment_id": "78", "starts_at": "2026-09-25T16:15:00-04:00", "duration": 60, "service_route_ids": [2557]}, IDENTITY)
        self.assertEqual(proposed["fixed_window_id"], 598)
        self.assertEqual(proposed["predicted_changes"]["arrival_time_window_start"], "16:00")

    def test_historical_tim_state_reconciles_without_patch(self) -> None:
        before = {
            "work_order_id": "8210560", "service_appointment_id": "1501269", "customer_id": "644133", "location_id": "727573",
            "starts_at": "2026-09-25T14:00:00-04:00", "duration": 60, "service_route_ids": [2557],
            "arrival_time_window": ["2026-09-25T14:00:00-04:00", "2026-09-25T15:00:00-04:00"],
            "arrival_time_window_start": "14:00", "arrival_time_window_end": "15:00",
            "instructions": "gate", "private_notes": "secret",
        }
        payload = {"work_order_id": "8210560", "service_appointment_id": "1501269", "starts_at": "2026-09-25T13:00:00-04:00", "duration": 60, "service_route_ids": [2557]}
        stored_after = {"starts_at": "2026-09-25T13:00:00-04:00", "arrival_time_window": ["2026-09-25T14:00:00-04:00", "2026-09-25T15:00:00-04:00"]}
        self.h.store.create_proposal({
            "proposal_id": "452170d3-6431-419b-b939-391b5a7860e0", "operation": OP_WORK_ORDER_SCHEDULE,
            "identity_sub": IDENTITY["sub"], "identity_email": IDENTITY["email"], "subject_key": "work_order:8210560",
            "before": before, "after": stored_after, "payload": payload, "digest": "b" * 64,
            "created_at": "2026-09-25T02:49:02Z", "expires_at": "2026-09-25T03:49:02Z",
        })
        self.h.store._conn.execute("UPDATE proposals SET status='ambiguous' WHERE proposal_id=?", ("452170d3-6431-419b-b939-391b5a7860e0",))
        self.h.store._conn.execute("UPDATE subject_guards SET state='ambiguous' WHERE proposal_id=?", ("452170d3-6431-419b-b939-391b5a7860e0",))
        row = self.h.transport.work_orders["8210560"]
        row.update({
            "starts_at": "2026-09-25T13:00:00.000-04:00", "ends_at": "2026-09-25T14:00:00.000-04:00", "finished_at": "2026-09-25T14:00:00.000-04:00",
            "duration": 60, "arrival_time_window": ["2026-09-25T13:00:00.000-04:00", "2026-09-25T14:00:00.000-04:00"],
            "arrival_time_window_start": "13:00", "arrival_time_window_end": "14:00",
        })
        done = self.h.service.reconcile_ambiguous("452170d3-6431-419b-b939-391b5a7860e0", IDENTITY)
        self.assertTrue(done["ok"], done)
        self.assertTrue(done["legacy_stored_after_not_authoritative"])
        self.assertTrue(done["immutable_payload_unchanged"])
        self.assertFalse(any(call["method"] == "PATCH" for call in self.h.transport.calls))
        self.assertEqual(self.h.store.get_proposal("452170d3-6431-419b-b939-391b5a7860e0")["after"], stored_after)
