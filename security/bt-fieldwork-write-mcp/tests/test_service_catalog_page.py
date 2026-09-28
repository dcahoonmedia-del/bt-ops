"""GET /services is one unpaginated all-services response. No live calls."""

from __future__ import annotations

import unittest

from tests.test_write_mcp import IDENTITY, Harness

GERMAN = "German Roach Treatment - Initial"
INVADERS = "Pest Control - Occasional Invaders"
FOLLOW = "Extra Service / Follow-up"


def _order() -> dict:
    return {
        "customer_id": 41,
        "service_location_id": 77,
        "repeat_type": "none",
        "repeat_period": 1,
        "starts_at": "2026-10-02",
        "service_route_ids": [1],
    }


def _line(name: str, payable_id: int, price: int) -> dict:
    return {
        "name": name,
        "type": "service",
        "quantity": 1,
        "price": price,
        "payable_id": payable_id,
        "payable_type": "Service",
        "taxable": False,
    }


def _generic(name: str, payable_id: int, price: int, **extra: object) -> dict:
    payload = {
        **_order(),
        "duration": 45,
        "instructions": "One visit.",
        "line_items": [_line(name, payable_id, price)],
    }
    payload.update(extra)
    return payload


def _rows(include_setup: bool, extras: list[dict] | None = None, size: int = 180) -> list[dict]:
    extras = list(extras or [])
    filler_count = size - (1 if include_setup else 0) - len(extras)
    if filler_count < 0:
        raise AssertionError("size smaller than named rows")
    rows = [{"id": 1000 + index, "description": f"Other {index}", "price": "10.0"} for index in range(filler_count)]
    if include_setup:
        rows.append({
            "id": 38814,
            "description": "PestGuard - Set-up",
            "price": "150.0",
            "category": "Pest - One Time",
            "account_id": 1741,
        })
    rows.extend(extras)
    return rows


class ServiceCatalogPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness(writes_enabled=True, api_role="writer")
        self.h.transport.users = [{
            "id": 10, "first_name": "Sam", "last_name": "Lee", "email": "sam@example.test",
            "service_route_id": 1, "service_route_name": "North", "is_technician": True, "branches": [],
        }]

    def tearDown(self) -> None:
        self.h.close()

    def _service_calls(self) -> list[dict]:
        return [call for call in self.h.transport.calls if call["path"] == "/services"]

    def test_unpaginated_180_row_catalog_is_complete(self) -> None:
        self.h.transport.services = _rows(True)
        proposed = self.h.service.propose("create_work_order", _order(), IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        self.assertTrue(proposed["after"]["catalog"]["service_list_complete"])
        self.assertIsNone(proposed["after"]["catalog"]["service_list_caveat"])
        self.assertEqual(proposed["after"]["catalog"]["service"]["id"], 38814)
        self.assertEqual(proposed["after"]["catalog"]["service"]["description"], "PestGuard - Set-up")
        self.assertEqual(proposed["after"]["catalog"]["service"]["category"], "Pest - One Time")
        listed = self._service_calls()
        self.assertEqual(len(listed), 1)
        self.assertIsNone(listed[0]["query"])
        self.assertFalse(any(call["method"] == "POST" for call in self.h.transport.calls))
        template_calls = [call for call in self.h.transport.calls if call["path"] == "/work_order_templates"]
        self.assertTrue(template_calls)
        self.assertEqual(template_calls[0]["query"]["page"], 1)
        self.assertEqual(template_calls[0]["query"]["per_page"], 100)

    def test_catalog_size_is_not_hardcoded(self) -> None:
        self.h.transport.services = _rows(True, size=7)
        small = self.h.client.list_services()
        self.assertTrue(small["complete"])
        self.assertEqual(len(small["items"]), 7)
        self.assertEqual(small["completeness"], "documented_get_services_all_services_response")
        self.assertIsNone(small["per_page"])
        self.assertFalse(small["pagination_query_sent"])
        self.h.transport.calls.clear()
        self.h.transport.services = _rows(True, size=1)
        one = self.h.client.list_services()
        self.assertTrue(one["complete"])
        self.assertEqual(len(one["items"]), 1)
        self.assertEqual(len(self._service_calls()), 1)
        self.assertIsNone(self._service_calls()[0]["query"])

    def test_full_catalog_generic_prices_succeed(self) -> None:
        extras = [
            {"id": 38812, "description": GERMAN, "price": "225.0"},
            {"id": 131844, "description": INVADERS, "price": "225.0"},
            {"id": 38804, "description": FOLLOW, "price": "0.0"},
        ]
        self.h.transport.services = _rows(True, extras)
        self.h.transport.work_orders["49965490"] = {
            "id": 49965490,
            "service_appointment_id": 8001,
            "customer_id": 99,
            "service_location_id": 100,
            "starts_at": "2024-05-01T10:00:00-04:00",
            "starts_at_date": "2024-05-01",
            "duration": 90,
            "service_route_ids": [9],
            "status": "scheduled",
            "line_items": [{"name": GERMAN, "price": "350.0", "payable_id": 38812, "payable_type": "Service", "type": "service"}],
        }
        german = self.h.service.propose("create_work_order", _generic(GERMAN, 38812, 225, starts_at="2026-10-03"), IDENTITY)
        self.assertTrue(german["ok"], german)
        self.assertEqual(german["after"]["standard_price"], 225)
        self.assertNotEqual(german["after"]["standard_price"], 350)
        self.assertIsNone(german["after"]["price_resolution"]["observed_existing_work_order_price"])
        invaders = self.h.service.propose("create_work_order", _generic(INVADERS, 131844, 225, starts_at="2026-10-04"), IDENTITY)
        self.assertTrue(invaders["ok"], invaders)
        self.assertEqual(invaders["after"]["price"], 225)
        self.assertFalse(invaders["after"]["execution_blocked"])
        follow = self.h.service.propose("create_work_order", _generic(FOLLOW, 38804, 0, starts_at="2026-10-05", production_value=40), IDENTITY)
        self.assertTrue(follow["ok"], follow)
        self.assertEqual(follow["after"]["price"], 0)
        self.assertEqual(follow["after"]["price_source"], "catalog/default")
        occurrence = follow["after"]["documented_request"]["service_appointment"]["appointment_occurrences_attributes"][0]
        self.assertEqual(occurrence["production_value"], 40)
        override = self.h.service.propose("create_work_order", _generic(GERMAN, 38812, 200, starts_at="2026-10-06"), IDENTITY)
        self.assertTrue(override["ok"], override)
        self.assertEqual(override["after"]["price_source"], "explicit_approved_override")
        self.assertEqual(override["after"]["price"], 200)
        self.assertEqual(override["after"]["standard_price"], 225)
        service_calls = self._service_calls()
        self.assertGreaterEqual(len(service_calls), 1)
        self.assertTrue(all(call["query"] is None for call in service_calls))
        self.assertEqual(self.h.transport.work_orders["49965490"]["line_items"][0]["price"], "350.0")

    def test_missing_service_on_a_complete_catalog_fails_closed(self) -> None:
        self.h.transport.services = _rows(False)
        missing = self.h.service.propose("create_work_order", _order(), IDENTITY)
        self.assertEqual(missing["gate"], "catalog_disagreement")
        self.assertEqual(missing["reason"], "payable_not_in_services")
        self.assertEqual(len(self._service_calls()), 1)
        self.assertIsNone(self._service_calls()[0]["query"])

    def test_malformed_duplicate_failed_and_truncated_catalogs_fail(self) -> None:
        self.h.transport.services_status = 500
        self.h.transport.services_body = {"error": "down"}
        failed = self.h.service.propose("create_work_order", _order(), IDENTITY)
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["gate"], "read_rejected")
        self.h.transport.services_status = 200
        self.h.transport.services_body = {"not_a_list": True}
        shape = self.h.service.propose("create_work_order", {**_order(), "starts_at": "2026-10-03"}, IDENTITY)
        self.assertEqual(shape["gate"], "read_shape_unverified")
        self.h.transport.services_body = [
            {"id": 38814, "description": "PestGuard - Set-up", "price": "150.0"},
            "not-a-service",
        ]
        row = self.h.service.propose("create_work_order", {**_order(), "starts_at": "2026-10-04"}, IDENTITY)
        self.assertEqual(row["gate"], "read_shape_unverified")
        self.assertEqual(row["reason"], "service_row_not_object")
        self.h.transport.services_body = {"items": _rows(True, size=3), "truncated": True, "next_page": 2}
        truncated = self.h.service.propose("create_work_order", {**_order(), "starts_at": "2026-10-05"}, IDENTITY)
        self.assertEqual(truncated["gate"], "catalog_disagreement")
        self.assertEqual(truncated["reason"], "service_list_incomplete")
        self.h.transport.services_body = None
        self.h.transport.services = [
            {"id": 38814, "description": "PestGuard - Set-up", "price": "150.0"},
            {"id": 38814, "description": "PestGuard - Set-up", "price": "99.0"},
        ]
        conflict = self.h.service.propose("create_work_order", {**_order(), "starts_at": "2026-10-06"}, IDENTITY)
        self.assertEqual(conflict["reason"], "service_id_conflict")
        self.h.transport.services = [{"id": 38814, "description": "Other name", "price": "150.0"}]
        label = self.h.service.propose("create_work_order", {**_order(), "starts_at": "2026-10-07"}, IDENTITY)
        self.assertEqual(label["reason"], "service_disagrees_with_template")
        self.h.transport.services = _rows(True, [{"id": 38899, "description": "Closed Service", "price": "10.0", "active": False}], size=4)
        inactive = self.h.service.propose("create_work_order", _generic("Closed Service", 38899, 10, starts_at="2026-10-08"), IDENTITY)
        self.assertEqual(inactive["reason"], "service_inactive")
        self.assertFalse(any(call["method"] == "POST" and call["path"] == "/work_orders" for call in self.h.transport.calls))
