"""Phase 2 read filters. Fake transport only."""

from __future__ import annotations

import unittest

from bt_fieldwork_write_mcp.errors import GateError
from bt_fieldwork_write_mcp.fieldwork import FakeTransport, TypedFieldworkClient
from bt_fieldwork_write_mcp.server import build_mcp
from tests.test_write_mcp import Harness


def _user(user_id: int, route_id: int, first: str, last: str, *, technician: bool = True, route_name: str | None = "Route") -> dict:
    return {
        "id": user_id,
        "first_name": first,
        "last_name": last,
        "email": f"{first.lower()}@example.test",
        "phone_number": "555",
        "is_technician": technician,
        "is_admin": False,
        "job_title": "staff",
        "service_route_id": route_id,
        "service_route_name": route_name,
        "stripe_pk": "pk_live_secret",
        "features": {"internal": True},
        "account": {"api_key": "nope"},
        "branches": [{"id": 1, "name": "Main", "company_name": "B&T", "address": "1 Main", "time_zone": "America/New_York", "internal_meta": "hide"}],
    }


class Phase2ReadTests(unittest.TestCase):
    def test_customer_filters_phone_and_details(self) -> None:
        transport = FakeTransport()
        transport.customers["41"] = {
            "id": 41, "name": "Ada House", "customer_status": "Active", "balance": 12, "terms": "net",
            "tags": ["vip"], "contacts": [{"name": "Ada"}], "billing_address": {"zip": "12345"},
            "card_number": "4242", "stripe_pk": "pk_live_secret",
        }
        client = TypedFieldworkClient(transport)
        found = client.search_customers("Ada", customer_status="Active", billing_postal_code="12345", date_added="2026-01-02", start_date="2026-01-01", end_date="2026-01-31", include_details=True)
        sent = transport.calls[0]
        self.assertEqual(sent["path"], "/customers/search")
        self.assertEqual(sent["query"]["query"], "Ada")
        self.assertEqual(sent["query"]["filter[customer_status]"], "Active")
        self.assertEqual(sent["query"]["filter[postal_code]"], "12345")
        self.assertEqual(sent["query"]["filter[date_added]"], "2026-01-02")
        self.assertEqual(found["postal_code_scope"], "documented_as_postal_code_not_billing_specific")
        self.assertIn("not_verified_as_created", found["date_range_semantics"])
        self.assertEqual(found["items"][0]["balance"], 12)
        self.assertNotIn("card_number", found["items"][0])
        self.assertNotIn("stripe_pk", found["items"][0])
        phone = client.search_customers(phone="555")
        self.assertEqual(transport.calls[-1]["path"], "/customers/search_by_phone")
        self.assertEqual(transport.calls[-1]["query"]["as_object"], True)
        self.assertNotIn("card_number", phone["items"][0] if phone["items"] else {})
        named = client.search_customers("House", name="Ada")
        self.assertEqual(named["name_filter"], "local_only")
        self.assertEqual(named["items"][0]["name"], "Ada House")
        with self.assertRaises(GateError) as caught:
            client.search_customers("Ada", branch="north")
        self.assertEqual(caught.exception.gate, "unsupported_filter")

    def test_locations_require_customer_and_keep_ownership(self) -> None:
        transport = FakeTransport()
        transport.add_customer({"id": 41, "name": "Ada", "customer_status": "Active"}, {"id": 77, "name": "House", "tax_rate_id": 3, "address": {"id": 9, "street": "1 Main", "notes": "porch"}})
        transport.add_customer({"id": 42, "name": "Bea", "customer_status": "Active"}, {"id": 78, "name": "Shop", "tax_rate_id": 3, "address": {"id": 10, "street": "2 Main"}})
        client = TypedFieldworkClient(transport)
        found = client.list_service_locations("41", phone="555", updated_after="2026-01-01")
        self.assertEqual(transport.calls[-1]["path"], "/customers/41/service_locations")
        self.assertEqual(transport.calls[-1]["query"]["filter[phone]"], "555")
        self.assertEqual([item["id"] for item in found["items"]], [77])
        self.assertEqual(found["items"][0]["address"]["notes"], "porch")
        self.assertTrue(found["customer_required"])
        self.assertFalse(found["global_endpoint"])
        with self.assertRaises(GateError):
            client.list_service_locations("41", active="true", branch="1")

    def test_work_order_filters_completeness_and_ids(self) -> None:
        transport = FakeTransport()
        for index in range(4):
            transport.work_orders[str(index)] = {
                "id": index, "service_appointment_id": 100 + index, "customer_id": 41 if index < 3 else 42,
                "service_location_id": 77, "service_route_ids": [9], "starts_at": "2026-09-25T08:00:00-04:00", "status": "scheduled",
            }
        transport.work_orders["9"] = {"id": 9, "service_appointment_id": 109, "service_route_ids": [9], "starts_at": "2026-09-25T08:00:00-04:00", "status": "scheduled"}
        client = TypedFieldworkClient(transport)
        found = client.list_work_orders(start_date="2026-09-25", end_date="2026-09-25", customer_id="41", service_location_id="77", per_page=2, max_pages=3)
        self.assertEqual([item["work_order_id"] for item in found["items"]], [0, 1, 2])
        self.assertEqual(found["items"][0]["service_appointment_id"], 100)
        self.assertNotEqual(found["items"][0]["work_order_id"], found["items"][0]["service_appointment_id"])
        self.assertIn("customer_id", found["local_filter"])
        self.assertGreaterEqual(found["rows_missing_filter_field"], 1)
        self.assertFalse(found["complete"])
        with self.assertRaises(GateError):
            client.list_work_orders(start_date="2026-09-25", end_date="2026-09-25", branch="1")
        transport.repeat_work_order_page = True
        repeated = client.list_work_orders(start_date="2026-09-25", end_date="2026-09-25", per_page=2, max_pages=3)
        self.assertTrue(repeated["repeated_page"])
        self.assertFalse(repeated["complete"])
        self.assertIsNone(repeated["next_page"])
        transport.repeat_work_order_page = False
        transport.fail_work_order_page = 2
        partial = client.list_work_orders(start_date="2026-09-25", end_date="2026-09-25", per_page=2, max_pages=3)
        self.assertFalse(partial["complete"])
        self.assertEqual(partial["partial_error"]["page"], 2)
        self.assertGreaterEqual(len(partial["items"]), 1)

    def test_live_users_keep_non_technicians_and_shared_routes(self) -> None:
        transport = FakeTransport()
        transport.users = [
            _user(3081, 2557, "Daniel", "Cahoon", technician=False, route_name="Route #3"),
            _user(4000, 2557, "Ally", "Office", technician=True, route_name="Route #3"),
            _user(9, -1, "Pool", "Person", technician=False, route_name=None),
        ]
        transport.work_orders["1"] = {
            "id": 1, "service_appointment_id": 2, "service_route_ids": [2557],
            "starts_at": "2026-09-25T08:00:00-04:00", "status": "scheduled", "technician_id": None,
        }
        client = TypedFieldworkClient(transport)
        listed = client.list_users()
        encoded = str(listed)
        self.assertNotIn("pk_live_secret", encoded)
        self.assertNotIn("api_key", encoded)
        daniel = next(item for item in listed["items"] if item["id"] == 3081)
        self.assertFalse(daniel["is_technician"])
        self.assertEqual(daniel["service_route_id"], 2557)
        self.assertEqual(daniel["branches"][0]["time_zone"], "America/New_York")
        self.assertNotIn("internal_meta", daniel["branches"][0])
        route = next(item for item in listed["directory"]["routes"] if item["route_id"] == "2557")
        self.assertTrue(route["ambiguous"])
        self.assertIsNone(route["assignee"])
        self.assertEqual(len(route["staff"]), 2)
        self.assertEqual(listed["directory"]["unassigned"][0]["service_route_id"], -1)
        schedule = client.list_work_orders(start_date="2026-09-25", end_date="2026-09-25", technician="Daniel Cahoon")
        self.assertEqual(schedule["technician_resolved_from"], "live_user_directory")
        self.assertIsNone(schedule["items"][0]["route_assignee"])
        self.assertTrue(schedule["items"][0]["route_staff_ambiguous"])
        self.assertEqual(len(schedule["items"][0]["route_staff"]), 2)
        routes = client.list_service_routes()
        self.assertEqual(routes["items"], [])
        self.assertEqual(routes["directory_source"], "live_user_directory")
        transport.users = None
        fallback = TypedFieldworkClient(transport, route_directory={"kind": "configured_snapshot", "routes": []}).list_service_routes()
        self.assertEqual(fallback["fallback_reason"], "live_users_unavailable")
        self.assertEqual(fallback["directory_source"], "configured_snapshot")

    def test_execute_schema_has_no_operator_parameter(self) -> None:
        harness = Harness()
        try:
            server = build_mcp(harness.service, harness.settings, __import__("bt_fieldwork_write_mcp.oauth_rs", fromlist=["JwtTokenVerifier"]).JwtTokenVerifier(harness.settings))
            execute = next(tool for tool in server._tool_manager.list_tools() if tool.name == "execute_approved_write")
            properties = set((execute.parameters or {}).get("properties") or {})
            self.assertEqual(properties, {"proposal_id", "approved", "expected_digest"})
            self.assertIn("list_users", {tool.name for tool in server._tool_manager.list_tools()})
            self.assertIn("list_service_locations", {tool.name for tool in server._tool_manager.list_tools()})
        finally:
            harness.close()
