"""Write contract v7. Offline. Documents the semantics older tests still encode."""

from __future__ import annotations

import unittest

from bt_fieldwork_write_mcp.allowlist import (
    GATE_ARRIVAL_WINDOW,
    GATE_READONLY,
    GATE_READBACK,
    GATE_RECURRING,
    GATE_REPLAY,
    GATE_SCHEMA_UNVERIFIED,
    GATE_STALE,
    OP_CREATE_WORK_ORDER,
    OP_WORK_ORDER_NOTES,
    OP_WORK_ORDER_SCHEDULE,
)
from bt_fieldwork_write_mcp.fieldwork import TypedFieldworkClient
from tests.test_write_mcp import IDENTITY, Harness


class _RoleClient:
    def __init__(self, inner: TypedFieldworkClient, role: str) -> None:
        self._inner = inner
        self._role = role
        self.patches: list[dict] = []
        self.persist = True

    def get_api_role(self) -> str:
        return self._role

    def patch_work_order_fields(self, before: dict, after: dict, fields: list[str]) -> dict:
        self.patches.append({"before": before, "after": after, "fields": list(fields)})
        if self.persist:
            row = self._inner.transport.work_orders[str(before["work_order_id"])]
            for field in fields:
                row[field] = after[field]
        return {"ok": True}

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


class ContractV7Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness(writes_enabled=True, api_role="writer", mapping_verified=True)
        self.role = _RoleClient(self.h.client, "writer")
        self.h.service.client = self.role
        self.h.transport.work_orders["10"] = {
            "id": 10,
            "service_appointment_id": 20,
            "customer_id": 41,
            "service_location_id": 77,
            "instructions": "old",
            "private_notes": "secret",
            "starts_at": "2026-09-25T08:00:00-04:00",
            "duration": 60,
            "service_route_ids": [2557],
            "arrival_time_window_str": "8-12",
            "arrival_time_window_start": "08:00",
            "arrival_time_window_end": "12:00",
        }

    def tearDown(self) -> None:
        self.h.close()

    def test_notes_require_strings_and_identity_snapshot(self) -> None:
        rejected = self.h.service.propose(OP_WORK_ORDER_NOTES, {"work_order_id": "10", "service_appointment_id": "20", "instructions": 5}, IDENTITY)
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["gate"], "unknown_field")
        proposed = self.h.service.propose(OP_WORK_ORDER_NOTES, {"work_order_id": "10", "service_appointment_id": "20", "instructions": "gate code"}, IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        self.assertEqual(proposed["before"]["customer_id"], 41)
        self.assertEqual(proposed["before"]["location_id"], 77)
        self.assertEqual(str(proposed["before"]["customer_status"]).lower(), "active")
        self.assertEqual(proposed["before"]["arrival_time_window_str"], "8-12")
        self.assertEqual(proposed["after"]["instructions"], "gate code")
        self.assertEqual(proposed["after"]["arrival_time_window_str"], "8-12")

    def test_lead_customer_blocks_notes(self) -> None:
        self.h.transport.customers["41"]["customer_status"] = "Lead"
        result = self.h.service.propose(OP_WORK_ORDER_NOTES, {"work_order_id": "10", "service_appointment_id": "20", "private_notes": "x"}, IDENTITY)
        self.assertEqual(result["gate"], "never_lead_status_accounts")

    def test_notes_execute_uses_profile_role_and_readback(self) -> None:
        self.h.settings = self.h.settings.__class__(**{**self.h.settings.__dict__, "api_role": "readonly"})
        proposed = self.h.service.propose(OP_WORK_ORDER_NOTES, {"work_order_id": "10", "service_appointment_id": "20", "instructions": "gate code"}, IDENTITY)
        token = self.h.approve(proposed["proposal_id"])
        executed = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertTrue(executed["ok"], executed)
        self.assertEqual(self.role.patches[0]["fields"], ["instructions"])
        self.assertEqual(executed["readback"]["instructions"], "gate code")
        self.assertEqual(executed["readback"]["arrival_time_window_str"], "8-12")
        self.role._role = "readonly"
        again = self.h.service.propose(OP_WORK_ORDER_NOTES, {"work_order_id": "10", "service_appointment_id": "20", "instructions": "later"}, IDENTITY)
        blocked = self.h.service.execute(again["proposal_id"], IDENTITY, operator_approval=self.h.approve(again["proposal_id"]))
        self.assertEqual(blocked["gate"], GATE_READONLY)

    def test_notes_stale_replay_and_readback(self) -> None:
        proposed = self.h.service.propose(OP_WORK_ORDER_NOTES, {"work_order_id": "10", "service_appointment_id": "20", "instructions": "gate code"}, IDENTITY)
        token = self.h.approve(proposed["proposal_id"])
        self.h.transport.work_orders["10"]["instructions"] = "changed"
        stale = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(stale["gate"], GATE_STALE)
        self.assertEqual(self.role.patches, [])
        self.h.transport.work_orders["10"]["instructions"] = "old"
        proposed = self.h.service.propose(OP_WORK_ORDER_NOTES, {"work_order_id": "10", "service_appointment_id": "20", "instructions": "gate code"}, IDENTITY)
        token = self.h.approve(proposed["proposal_id"])
        self.role.persist = False
        failed = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(failed["gate"], GATE_READBACK)
        replay = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(replay["gate"], "ambiguous_remote_write_no_retry")

    def test_schedule_single_occurrence_preserves_arrival_window(self) -> None:
        proposed = self.h.service.propose(
            OP_WORK_ORDER_SCHEDULE,
            {"work_order_id": "10", "service_appointment_id": "20", "starts_at": "2026-09-25T13:00:00-04:00", "duration": 45, "service_route_ids": [2557, 4550]},
            IDENTITY,
        )
        self.assertFalse(proposed["ok"])
        self.assertEqual(proposed["gate"], "schedule_coupling_unverified")

    def test_schedule_rejects_bad_values_series_and_arrival_edits(self) -> None:
        bad = self.h.service.propose(OP_WORK_ORDER_SCHEDULE, {"work_order_id": "10", "service_appointment_id": "20", "starts_at": "2026-09-25T13:00:00Z", "duration": 45, "service_route_ids": [1]}, IDENTITY)
        self.assertEqual(bad["gate"], "unknown_field")
        bad = self.h.service.propose(OP_WORK_ORDER_SCHEDULE, {"work_order_id": "10", "service_appointment_id": "20", "starts_at": "2026-09-25T13:00:00-04:00", "duration": 0, "service_route_ids": [1]}, IDENTITY)
        self.assertEqual(bad["gate"], "unknown_field")
        bad = self.h.service.propose(OP_WORK_ORDER_SCHEDULE, {"work_order_id": "10", "service_appointment_id": "20", "starts_at": "2026-09-25T13:00:00-04:00", "duration": 30, "service_route_ids": [0]}, IDENTITY)
        self.assertEqual(bad["gate"], "unknown_field")
        window = self.h.service.propose(OP_WORK_ORDER_SCHEDULE, {"work_order_id": "10", "service_appointment_id": "20", "starts_at": "2026-09-25T13:00:00-04:00", "duration": 30, "service_route_ids": [1], "arrival_time_window_str": "1-2"}, IDENTITY)
        self.assertEqual(window["gate"], "unknown_field")
        self.h.transport.work_orders["10"]["repeat_type"] = "weekly"
        series = self.h.service.propose(OP_WORK_ORDER_SCHEDULE, {"work_order_id": "10", "service_appointment_id": "20", "starts_at": "2026-09-25T13:00:00-04:00", "duration": 30, "service_route_ids": [1]}, IDENTITY)
        self.assertEqual(series["gate"], GATE_RECURRING)

    def test_schedule_stale_before_patch(self) -> None:
        self.h.transport.work_orders["10"].update({
            "arrival_time_window": ["2026-09-25T08:00:00-04:00", "2026-09-25T08:45:00-04:00"],
            "arrival_time_window_start": "08:00",
            "arrival_time_window_end": "08:45",
        })
        proposed = self.h.service.propose(OP_WORK_ORDER_SCHEDULE, {"work_order_id": "10", "service_appointment_id": "20", "starts_at": "2026-09-25T13:00:00-04:00", "duration": 45, "service_route_ids": [2557]}, IDENTITY)
        self.assertEqual(proposed["gate"], "schedule_coupling_unverified")
        self.assertIn("stale", proposed["reason"])
        self.assertEqual(self.role.patches, [])

    def test_create_stays_unavailable(self) -> None:
        proposed = self.h.service.propose(
            OP_CREATE_WORK_ORDER,
            {"customer_id": 41, "service_location_id": 77, "repeat_type": "none", "repeat_period": 0, "line_items": [], "occurrences": []},
            IDENTITY,
        )
        self.assertFalse(proposed["ok"])
        self.assertEqual(proposed["gate"], GATE_SCHEMA_UNVERIFIED)
        self.assertNotIn("proposal_id", proposed)
        self.assertEqual(self.role.patches, [])

    def test_arrival_constant_is_still_closed(self) -> None:
        self.assertEqual(GATE_ARRIVAL_WINDOW, "arrival_window_unverified")
