"""Configured PestGuard initial template. Offline only. No live Fieldwork call."""

from __future__ import annotations

import copy
import unittest

from bt_fieldwork_write_mcp.auth0_bridge import resolve_human_identity
from tests.test_write_mcp import IDENTITY, Harness


def _line(price: int) -> dict:
    return {
        "name": "PestGuard - Set-up",
        "type": "service",
        "quantity": 1,
        "price": price,
        "payable_id": 38814,
        "payable_type": "Service",
        "taxable": False,
    }


class PestGuardTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness(writes_enabled=True, api_role="writer")
        self.h.transport.users = [{
            "id": 10, "first_name": "Sam", "last_name": "Lee", "email": "sam@example.test",
            "service_route_id": 1, "service_route_name": "North", "is_technician": True, "branches": [],
        }]

    def tearDown(self) -> None:
        self.h.close()

    def _add_recurring(self) -> None:
        other = copy.deepcopy(self.h.transport.templates[0])
        other["id"] = 8835903
        other["name"] = "PestGuard recurring"
        other["repeat_type"] = "monthly"
        self.h.transport.templates.append(other)

    def test_configured_initial_is_selected_among_several(self) -> None:
        self._add_recurring()
        proposed = self.h.service.propose("create_work_order", {
            "customer_id": 41, "service_location_id": 77, "repeat_type": "none", "repeat_period": 1,
            "starts_at": "2026-10-02", "service_route_ids": [1], "line_items": [_line(175)],
        }, IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        self.assertEqual(proposed["after"]["template_id"], 8835901)
        self.assertEqual(proposed["after"]["price"], 175)
        self.assertEqual(proposed["after"]["line_total"], 175)
        line = proposed["after"]["documented_request"]["service_appointment"]["line_items_attributes"][0]
        self.assertEqual(line["price"], 175)
        self.assertNotIn("id", line)
        self.assertNotIn("105539222", str(line))
        self.assertFalse(any(call["method"] == "POST" for call in self.h.transport.calls))

    def test_missing_and_wrong_configured_id_fail_closed(self) -> None:
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer", pestguard_initial_template_id="")
        missing = self.h.service.propose("create_work_order", {
            "customer_id": 41, "service_location_id": 77, "repeat_type": "none", "repeat_period": 1,
            "starts_at": "2026-10-02", "service_route_ids": [1],
        }, IDENTITY)
        self.assertEqual(missing["gate"], "template_unverified")
        self.assertEqual(missing["reason"], "template_not_configured")
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer", pestguard_initial_template_id="1")
        wrong = self.h.service.propose("create_work_order", {
            "customer_id": 41, "service_location_id": 77, "repeat_type": "none", "repeat_period": 1,
            "starts_at": "2026-10-02", "service_route_ids": [1],
        }, IDENTITY)
        self.assertEqual(wrong["gate"], "template_unverified")
        self.assertEqual(wrong["reason"], "template_id_not_in_list")

    def test_recurring_template_and_wrong_service_are_rejected(self) -> None:
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer", pestguard_initial_template_id="8835903")
        recurring = copy.deepcopy(self.h.transport.templates[0])
        recurring["id"] = 8835903
        recurring["repeat_type"] = "monthly"
        self.h.transport.templates.append(recurring)
        rejected = self.h.service.propose("create_work_order", {
            "customer_id": 41, "service_location_id": 77, "repeat_type": "none", "repeat_period": 1,
            "starts_at": "2026-10-02", "service_route_ids": [1],
        }, IDENTITY)
        self.assertEqual(rejected["gate"], "recurring_series_rejected")
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer", pestguard_initial_service_id="1")
        mismatch = self.h.service.propose("create_work_order", {
            "customer_id": 41, "service_location_id": 77, "repeat_type": "none", "repeat_period": 1,
            "starts_at": "2026-10-02", "service_route_ids": [1],
        }, IDENTITY)
        self.assertEqual(mismatch["gate"], "catalog_disagreement")
        self.assertEqual(mismatch["reason"], "configured_service_mismatch")

    def test_jane_style_timed_proposal_does_not_post(self) -> None:
        self.h.transport.add_customer(
            {"id": 3675448, "customer_status": "Active", "name": "Jane Doe"},
            {"id": 4491818, "name": "Main Location", "tax_rate_id": 3, "address": {"id": 1}},
        )
        proposed = self.h.service.propose("create_work_order", {
            "customer_id": 3675448,
            "service_location_id": 4491818,
            "repeat_type": "none",
            "repeat_period": 1,
            "starts_at": "2026-10-02T14:00:00-04:00",
            "duration": 60,
            "service_route_ids": [1],
        }, IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        self.assertEqual(proposed["after"]["template_id"], 8835901)
        self.assertEqual(proposed["after"]["schedule_patch"]["starts_at"], "2026-10-02T14:00:00-04:00")
        self.assertEqual(proposed["after"]["documented_request"]["service_appointment"]["appointment_occurrences_attributes"][0]["starts_at"], "2026-10-02")
        self.assertFalse(any(call["method"] in {"POST", "PATCH"} for call in self.h.transport.calls))

    def test_same_permit_list_accepts_a_verified_email_and_does_not_invent_a_subject(self) -> None:
        permitted = ("daniel@btpestcontrol.com", "joshua1740@icloud.com")
        subject_map = {"auth0|daniel": "daniel@btpestcontrol.com"}
        daniel = resolve_human_identity(
            {"sub": "auth0|daniel", "email": "daniel@btpestcontrol.com", "email_verified": True},
            permitted=permitted,
            subject_map=subject_map,
        )
        josh = resolve_human_identity(
            {"sub": "auth0|from-verified-token", "email": "joshua1740@icloud.com", "email_verified": True},
            permitted=permitted,
            subject_map=subject_map,
        )
        inferred = resolve_human_identity(
            {"sub": "auth0|from-verified-token", "preferred_username": "joshua1740@icloud.com"},
            permitted=permitted,
            subject_map=subject_map,
        )
        self.assertEqual(daniel["email"], "daniel@btpestcontrol.com")
        self.assertEqual(josh["email"], "joshua1740@icloud.com")
        self.assertEqual(josh["sub"], "auth0|from-verified-token")
        self.assertIsNone(inferred)
        self.assertNotIn("joshua1740@icloud.com", subject_map.values())
