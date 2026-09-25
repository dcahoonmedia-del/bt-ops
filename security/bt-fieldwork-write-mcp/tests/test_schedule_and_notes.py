"""Schedule reads and enabled occurrence-note writes. Offline only."""

from __future__ import annotations

import unittest

from bt_fieldwork_write_mcp.allowlist import GATE_READBACK, GATE_REPLAY, GATE_STALE, OP_WORK_ORDER_NOTES
from bt_fieldwork_write_mcp.fieldwork import FakeTransport, TypedFieldworkClient
from bt_fieldwork_write_mcp.server import report_gates_body
from tests.test_write_mcp import IDENTITY, Harness


def _row(wid: int, route: int, day: str, status: str = "scheduled") -> dict:
    return {
        "id": wid,
        "service_appointment_id": 1000 + wid,
        "service_route_ids": [route],
        "service_routes": [{"id": route, "name": f"Route {route}"}],
        "technician_id": None,
        "starts_at": f"{day}T08:00:00-04:00",
        "ends_at": f"{day}T09:00:00-04:00",
        "status": status,
        "instructions": "old",
        "private_notes": "secret",
    }


class ScheduleTests(unittest.TestCase):
    def test_handler_filters_date_status_and_route_across_pages(self) -> None:
        transport = FakeTransport()
        for index in range(5):
            transport.work_orders[str(index)] = _row(index, 4550 if index == 0 else 135779, "2026-09-25" if index < 4 else "2026-09-26")
        found = TypedFieldworkClient(transport).list_work_orders(
            start_date="2026-09-25",
            end_date="2026-09-25",
            status="scheduled",
            service_route_ids=["135779"],
            per_page=2,
            max_pages=3,
        )
        self.assertEqual([item["work_order_id"] for item in found["items"]], [1, 2, 3])
        self.assertFalse(found["server_side_filtering"])
        self.assertTrue(found["complete"])
        self.assertIsNone(found["next_page"])
        self.assertEqual(found["pages_read"], 3)
        self.assertIsNone(found["items"][0]["technician_id"])
        self.assertEqual(found["items"][0]["service_routes"], [{"id": 135779, "name": "Route 135779"}])
        sent = [call["query"] for call in transport.calls if call["path"] == "/work_orders"]
        self.assertEqual(sent[0]["start_date"], "2026-09-25")
        self.assertEqual(sent[0]["filter[service_routes_ids][]"], ["135779"])

    def test_configured_snapshot_selects_route_without_changing_null_technician(self) -> None:
        import json
        import tempfile
        from pathlib import Path

        from bt_fieldwork_write_mcp.fieldwork import load_route_directory

        transport = FakeTransport()
        transport.work_orders["1"] = _row(1, 2557, "2026-09-25")
        transport.work_orders["2"] = _row(2, 4550, "2026-09-25")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "routes.json"
            path.write_text(json.dumps({
                "source": "operator snapshot",
                "verified_at": "2026-09-25T01:00:00Z",
                "routes": [{"route_id": "2557", "name": "Route #3", "user_id": "3081", "user_name": "Daniel Cahoon"}],
            }), encoding="utf-8")
            client = TypedFieldworkClient(transport, route_directory=load_route_directory(str(path)))
        found = client.list_work_orders(start_date="2026-09-25", end_date="2026-09-25", technician="Daniel Cahoon", per_page=10)
        self.assertEqual([item["work_order_id"] for item in found["items"]], [1])
        self.assertIsNone(found["items"][0]["technician_id"])
        self.assertEqual(found["items"][0]["configured_route_assignee"]["route_id"], "2557")
        self.assertEqual(found["technician_resolved_from"], "configured_snapshot")
        self.assertTrue(found["items"][0]["configured_route_assignee"]["not_live_api_staff"])
        routes = client.list_service_routes()
        self.assertEqual(routes["items"], [])
        self.assertEqual(routes["configured_snapshot"]["kind"], "configured_snapshot")

    def test_full_page_reports_next_page(self) -> None:
        transport = FakeTransport()
        for index in range(4):
            transport.work_orders[str(index)] = _row(index, 7, "2026-09-25")
        found = TypedFieldworkClient(transport).list_work_orders(start_date="2026-09-25", end_date="2026-09-25", per_page=2, max_pages=1)
        self.assertEqual(len(found["items"]), 2)
        self.assertFalse(found["complete"])
        self.assertTrue(found["truncated"])
        self.assertEqual(found["next_page"], 2)


class WorkOrderNoteWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness(writes_enabled=True, api_role="writer")
        self.h.transport.work_orders["10"] = {"id": 10, "service_appointment_id": 20, "customer_id": 41, "service_location_id": 77, "instructions": "old", "private_notes": "secret"}

    def tearDown(self) -> None:
        self.h.close()

    def _propose(self) -> dict:
        proposed = self.h.service.propose(
            OP_WORK_ORDER_NOTES,
            {"work_order_id": "10", "service_appointment_id": "20", "instructions": "gate code"},
            IDENTITY,
        )
        self.assertTrue(proposed["ok"], proposed)
        return proposed

    def test_approved_patch_readback(self) -> None:
        proposed = self._propose()
        token = self.h.approve(proposed["proposal_id"])
        executed = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertTrue(executed["ok"], executed)
        self.assertEqual(executed["readback"]["instructions"], "gate code")
        self.assertEqual(self.h.transport.work_orders["10"]["instructions"], "gate code")

    def test_stale_before_patch(self) -> None:
        proposed = self._propose()
        token = self.h.approve(proposed["proposal_id"])
        self.h.transport.work_orders["10"]["instructions"] = "changed elsewhere"
        result = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(result["gate"], GATE_STALE)
        self.assertFalse(any(call["method"] == "PATCH" for call in self.h.transport.calls))

    def test_replayed_approval(self) -> None:
        proposed = self._propose()
        token = self.h.approve(proposed["proposal_id"])
        first = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertTrue(first["ok"], first)
        again = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(again["gate"], GATE_REPLAY)

    def test_readback_mismatch_does_not_retry(self) -> None:
        proposed = self._propose()
        token = self.h.approve(proposed["proposal_id"])
        self.h.transport.skip_work_order_persist = True
        result = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(result["gate"], GATE_READBACK)
        retry = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(retry["gate"], "ambiguous_remote_write_no_retry")

    def test_readiness_does_not_require_offline_access_on_the_access_token(self) -> None:
        body = report_gates_body(self.h.service, self.h.settings)
        self.assertFalse(body["offline_access_required_on_access_token"])
        self.assertTrue(body["existing_downstream_sessions_remain_usable"])
        self.assertTrue(body["refresh_token_needs_one_new_authorization"])
        self.assertFalse(body["offline_access_observed_by_this_process"])
