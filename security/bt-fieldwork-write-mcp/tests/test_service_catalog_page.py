"""Exact service id on a repeated /services page. No live calls."""

from __future__ import annotations

import unittest

from tests.test_write_mcp import IDENTITY, Harness


def _order() -> dict:
    return {
        "customer_id": 41,
        "service_location_id": 77,
        "repeat_type": "none",
        "repeat_period": 1,
        "starts_at": "2026-10-02",
        "service_route_ids": [1],
    }


def _rows(include: bool, extra: dict | None = None) -> list[dict]:
    rows = [{"id": 1000 + index, "description": f"Other {index}", "price": "10.0"} for index in range(179)]
    if include:
        rows.append({
            "id": 38814,
            "description": "PestGuard - Set-up",
            "price": "150.0",
            "category": "Pest - One Time",
            "account_id": 1741,
        })
    else:
        rows.append({"id": 999, "description": "Other", "price": "10.0"})
    if extra:
        rows.append(extra)
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

    def test_repeated_180_page_verifies_the_one_setup_service(self) -> None:
        self.h.transport.services = _rows(True)
        proposed = self.h.service.propose("create_work_order", _order(), IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        self.assertFalse(proposed["after"]["catalog"]["service_list_complete"])
        self.assertEqual(proposed["after"]["catalog"]["service_list_caveat"], "exact_service_id_only_list_not_complete")
        self.assertEqual(proposed["after"]["catalog"]["service"]["id"], 38814)
        self.assertEqual(proposed["after"]["catalog"]["service"]["description"], "PestGuard - Set-up")
        self.assertEqual(proposed["after"]["catalog"]["service"]["category"], "Pest - One Time")
        listed = [call for call in self.h.transport.calls if call["path"] == "/services"]
        self.assertGreaterEqual(len(listed), 2)
        self.assertFalse(any(call["method"] == "POST" for call in self.h.transport.calls))

    def test_repeated_page_without_the_id_stays_incomplete(self) -> None:
        self.h.transport.services = _rows(False)
        missing = self.h.service.propose("create_work_order", _order(), IDENTITY)
        self.assertEqual(missing["gate"], "catalog_disagreement")
        self.assertEqual(missing["reason"], "service_list_incomplete")

    def test_partial_error_and_conflicting_ids_fail(self) -> None:
        self.h.transport.services = _rows(True)
        original = self.h.transport.request

        def fail_second(method, path, body=None, query=None):
            if path == "/services" and str((query or {}).get("page")) == "2":
                return 500, {"error": "page_failed"}
            return original(method, path, body, query)

        self.h.transport.request = fail_second
        failed = self.h.service.propose("create_work_order", _order(), IDENTITY)
        self.assertEqual(failed["reason"], "service_list_incomplete")
        self.h.transport.request = original
        self.h.transport.services = [
            {"id": 38814, "description": "PestGuard - Set-up", "price": "150.0"},
            {"id": 38814, "description": "PestGuard - Set-up", "price": "99.0"},
        ]
        conflict = self.h.service.propose("create_work_order", {**_order(), "starts_at": "2026-10-03"}, IDENTITY)
        self.assertEqual(conflict["reason"], "service_id_conflict")
        self.h.transport.services = [{"id": 38814, "description": "Other name", "price": "150.0"}]
        label = self.h.service.propose("create_work_order", {**_order(), "starts_at": "2026-10-04"}, IDENTITY)
        self.assertEqual(label["reason"], "service_disagrees_with_template")
