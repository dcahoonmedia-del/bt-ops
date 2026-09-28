"""Service-catalog price stays separate from another work order's line. Offline only."""

from __future__ import annotations

import json
import unittest

from tests.test_write_mcp import IDENTITY, Harness

GERMAN = "German Roach Treatment - Initial"
INSTRUCTIONS = (
    "German cockroach initial treatment. Customer reports activity began around the sink "
    "and is now throughout the home after spraying around the sink. Approx. 1,000 sq ft townhome. "
    "Customer works from home and is available. Call on the way."
)


def _german(price: int) -> dict:
    return {
        "name": GERMAN,
        "type": "service",
        "quantity": 1,
        "price": price,
        "payable_id": 38812,
        "payable_type": "Service",
        "taxable": False,
    }


def _order(**extra: object) -> dict:
    payload = {
        "customer_id": 41,
        "service_location_id": 77,
        "repeat_type": "none",
        "repeat_period": 1,
        "starts_at": "2026-09-29",
        "duration": 90,
        "service_route_ids": [1],
        "instructions": INSTRUCTIONS,
        "line_items": [_german(225)],
    }
    payload.update(extra)
    return payload


class CatalogPriceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness(writes_enabled=True, api_role="writer")
        self.h.transport.users = [{
            "id": 10, "first_name": "Sam", "last_name": "Lee", "email": "sam@example.test",
            "service_route_id": 1, "service_route_name": "North", "is_technician": True, "branches": [],
        }]
        self.h.transport.services.append({
            "id": 38812,
            "description": GERMAN,
            "price": "225.0",
        })
        self.h.transport.work_orders["49965490"] = {
            "id": 49965490,
            "service_appointment_id": 8001,
            "customer_id": 99,
            "service_location_id": 100,
            "starts_at": "2024-05-01T10:00:00-04:00",
            "starts_at_date": "2024-05-01",
            "duration": 90,
            "service_route_ids": [9],
            "repeat_type": "none",
            "status": "scheduled",
            "line_items": [{
                "name": GERMAN,
                "type": "service",
                "quantity": "1.0",
                "price": "350.0",
                "payable_id": 38812,
                "payable_type": "Service",
                "taxable": False,
            }],
        }

    def tearDown(self) -> None:
        self.h.close()

    def test_historical_work_order_price_does_not_replace_catalog_price(self) -> None:
        proposed = self.h.service.propose("create_work_order", _order(), IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        self.assertEqual(proposed["after"]["standard_price"], 225)
        self.assertNotEqual(proposed["after"]["standard_price"], 350)
        resolution = proposed["after"]["price_resolution"]
        self.assertEqual(resolution["catalog_price"], 225)
        self.assertIsNone(resolution["template_price"])
        self.assertFalse(proposed["after"]["template_consulted"])
        self.assertIsNone(resolution["observed_existing_work_order_price"])
        self.assertEqual(resolution["historical_work_order_price_role"], "not_catalog_evidence")
        self.assertEqual(self.h.transport.work_orders["49965490"]["line_items"][0]["price"], "350.0")

    def test_caller_price_matching_catalog_is_not_an_override(self) -> None:
        proposed = self.h.service.propose("create_work_order", _order(starts_at="2026-09-29T14:30:00-04:00"), IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        self.assertNotEqual(proposed.get("reason"), "caller_line_disagrees_with_template")
        resolution = proposed["after"]["price_resolution"]
        self.assertEqual(resolution["price_source"], "catalog/default")
        self.assertFalse(resolution["override"])
        self.assertEqual(resolution["caller_approved_price"], 225)
        self.assertEqual(resolution["final_price"], 225)
        self.assertEqual(proposed["after"]["price_source"], "catalog/default")
        self.assertEqual(proposed["after"]["service_pricing"]["name"], GERMAN)
        self.assertEqual(proposed["after"]["service_pricing"]["payable_id"], 38812)
        self.assertEqual(proposed["after"]["service_pricing"]["standard_price"], 225)
        line = proposed["after"]["documented_request"]["service_appointment"]["line_items_attributes"][0]
        self.assertEqual(line["price"], 225)
        self.assertEqual(line["name"], GERMAN)
        self.assertFalse(line["taxable"])
        occurrence = proposed["after"]["documented_request"]["service_appointment"]["appointment_occurrences_attributes"][0]
        self.assertEqual(occurrence["duration"], 90)
        self.assertEqual(occurrence["instructions"], INSTRUCTIONS)
        self.assertNotIn("production_value", occurrence)
        self.assertEqual(proposed["after"]["production_source"], "omitted_remote_default_unverified")
        self.assertFalse(proposed["after"]["production_sent"])
        self.assertEqual(proposed["after"]["documented_request"]["service_appointment"]["repeat_type"], "none")
        self.assertFalse(proposed["after"]["recurrence"])
        self.assertFalse(proposed["after"]["agreement"])
        self.assertFalse(proposed["after"]["execution_blocked"])
        self.assertEqual(proposed["after"]["work_order_selectability"], "current_complete_catalog_member")
        self.assertFalse(proposed["after"]["list_membership_proves_active"])
        self.assertEqual(proposed["after"]["active_eligibility"], "unverified")
        self.assertEqual(proposed["after"]["invoice_generation_reason"], "not_in_service_catalog")
        self.assertIsNone(proposed["after"]["auto_generates_invoice"])
        done = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=self.h.approve(proposed["proposal_id"]))
        self.assertTrue(done["ok"], done)
        self.assertFalse(done["live_tested"])
        posts = [call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/work_orders"]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["body"]["service_appointment"]["line_items_attributes"][0]["price"], 225)
        self.assertEqual(self.h.transport.work_orders["49965490"]["line_items"][0]["price"], "350.0")

    def test_caller_price_above_catalog_stays_an_explicit_override(self) -> None:
        proposed = self.h.service.propose("create_work_order", _order(line_items=[_german(200)], starts_at="2026-09-30"), IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        resolution = proposed["after"]["price_resolution"]
        self.assertEqual(resolution["price_source"], "explicit_approved_override")
        self.assertTrue(resolution["override"])
        self.assertEqual(resolution["catalog_price"], 225)
        self.assertEqual(resolution["caller_approved_price"], 200)
        self.assertEqual(resolution["final_price"], 200)
        self.assertEqual(resolution["service_name"], GERMAN)
        self.assertEqual(resolution["payable_id"], 38812)
        self.assertIsNone(resolution["observed_existing_work_order_price"])
        self.assertEqual(proposed["after"]["standard_price"], 225)
        self.assertEqual(proposed["after"]["price"], 200)
        self.assertIsNone(proposed["after"]["production_value"])
        self.assertEqual(proposed["after"]["production_source"], "omitted_remote_default_unverified")
        done = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=self.h.approve(proposed["proposal_id"]))
        self.assertTrue(done["ok"], done)
        posts = [call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/work_orders"]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["body"]["service_appointment"]["line_items_attributes"][0]["price"], 200)
        self.assertEqual(self.h.transport.work_orders["49965490"]["line_items"][0]["price"], "350.0")

    def test_missing_catalog_price_does_not_use_historical_line(self) -> None:
        self.h.transport.services[1].pop("price")
        missing_price = self.h.service.propose("create_work_order", _order(), IDENTITY)
        self.assertFalse(missing_price["ok"])
        self.assertEqual(missing_price["gate"], "catalog_disagreement")
        self.assertEqual(missing_price["reason"], "service_catalog_price_unverified")
        self.assertIsNone(missing_price["observed_existing_work_order_price"])
        self.assertNotIn("350", json.dumps(missing_price))
        self.h.transport.services.pop(1)
        missing_service = self.h.service.propose("create_work_order", _order(starts_at="2026-10-01"), IDENTITY)
        self.assertEqual(missing_service["gate"], "catalog_disagreement")
        self.assertEqual(missing_service["reason"], "payable_not_in_services")
        self.assertNotIn("350", json.dumps(missing_service))
        self.assertNotIn("standard_price", missing_service)

    def test_historical_line_does_not_false_disagree_when_caller_matches_catalog(self) -> None:
        proposed = self.h.service.propose("create_work_order", _order(starts_at="2026-10-02"), IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        self.assertNotEqual(proposed.get("reason"), "caller_line_disagrees_with_template")
        self.assertEqual(proposed["after"]["price_source"], "catalog/default")
        self.assertEqual(proposed["after"]["standard_price"], 225)
        self.assertEqual(proposed["after"]["catalog"]["line"]["payable_id"], 38812)
        self.assertEqual(proposed["after"]["catalog"]["line"]["price"], 225)
        self.assertIsNone(proposed["after"]["catalog"]["template_id"])
        self.assertIsNone(proposed["after"]["catalog"]["work_order_defaults"])

    def test_pestguard_initial_price_behavior_unchanged(self) -> None:
        self.h.transport.services[0]["price"] = 151
        disagreed = self.h.service.propose("create_work_order", {
            "customer_id": 41,
            "service_location_id": 77,
            "repeat_type": "none",
            "repeat_period": 1,
            "starts_at": "2026-10-06",
            "service_route_ids": [1],
        }, IDENTITY)
        self.assertEqual(disagreed["gate"], "catalog_disagreement")
        self.assertEqual(disagreed["reason"], "service_disagrees_with_template")
        self.h.transport.services[0]["price"] = "150.0"
        plain = self.h.service.propose("create_work_order", {
            "customer_id": 41,
            "service_location_id": 77,
            "repeat_type": "none",
            "repeat_period": 1,
            "starts_at": "2026-10-07",
            "service_route_ids": [1],
        }, IDENTITY)
        self.assertTrue(plain["ok"], plain)
        self.assertEqual(plain["after"]["price_source"], "catalog/default")
        self.assertEqual(plain["after"]["production_source"], "template_default")
        self.assertEqual(plain["after"]["price"], 150)
        self.assertEqual(plain["after"]["standard_price"], 150)
        self.assertEqual(plain["after"]["service_pricing"]["payable_id"], 38814)
        self.assertEqual(plain["after"]["service_pricing"]["name"], "PestGuard - Set-up")
        self.assertNotIn("price_resolution", plain["after"])
        self.assertEqual(plain["after"]["production_value"], 150)
        quoted = self.h.service.propose("create_work_order", {
            "customer_id": 41,
            "service_location_id": 77,
            "repeat_type": "none",
            "repeat_period": 1,
            "starts_at": "2026-10-08",
            "service_route_ids": [1],
            "line_items": [{
                "name": "PestGuard - Set-up",
                "type": "service",
                "quantity": 1,
                "price": 175,
                "payable_id": 38814,
                "payable_type": "Service",
                "taxable": False,
            }],
        }, IDENTITY)
        self.assertTrue(quoted["ok"], quoted)
        self.assertEqual(quoted["after"]["price_source"], "explicit_approved_override")
        self.assertEqual(quoted["after"]["production_value"], 150)
        self.assertEqual(quoted["after"]["production_source"], "template_default")
        self.assertEqual(quoted["after"]["price"], 175)
        self.assertEqual(quoted["after"]["standard_price"], 150)
        self.assertEqual(quoted["after"]["price_resolution"]["catalog_price"], 150)
        self.assertEqual(quoted["after"]["price_resolution"]["final_price"], 175)
        self.assertTrue(quoted["after"]["price_resolution"]["override"])
        self.assertEqual(quoted["after"]["service_pricing"]["payable_id"], 38814)
        self.assertTrue(quoted["after"]["template_consulted"])
        self.assertFalse(quoted["after"]["execution_blocked"])

    def test_pestguard_template_changes_do_not_control_a_generic_service(self) -> None:
        self.h.transport.templates[0]["line_items"][0]["price"] = "999.0"
        self.h.transport.templates[0]["repeat_period"] = 99
        self.h.transport.templates[0]["work_order"]["production_value"] = 1
        self.h.transport.templates[0]["work_order"]["duration"] = 15
        self.h.transport.templates[0]["work_order"]["instructions"] = "template text"
        proposed = self.h.service.propose("create_work_order", _order(starts_at="2026-10-09"), IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        self.assertFalse(proposed["after"]["template_consulted"])
        self.assertIsNone(proposed["after"]["template_id"])
        self.assertEqual(proposed["after"]["standard_price"], 225)
        self.assertIsNone(proposed["after"]["price_resolution"]["template_price"])
        self.assertEqual(proposed["after"]["production_source"], "omitted_remote_default_unverified")
        body = proposed["after"]["documented_request"]["service_appointment"]
        self.assertEqual(body["repeat_period"], 1)
        self.assertEqual(body["appointment_occurrences_attributes"][0]["duration"], 90)
        self.assertEqual(body["appointment_occurrences_attributes"][0]["instructions"], INSTRUCTIONS)
        self.assertNotIn("production_value", body["appointment_occurrences_attributes"][0])
        self.assertFalse(any(call["path"].startswith("/work_order_templates") for call in self.h.transport.calls))
        self.h.transport.templates.clear()
        again = self.h.service.propose("create_work_order", _order(starts_at="2026-10-10"), IDENTITY)
        self.assertTrue(again["ok"], again)
        self.assertEqual(again["after"]["standard_price"], 225)
        self.assertEqual(again["after"]["invoice_generation_reason"], "not_in_service_catalog")
        blocked = self.h.service.propose("create_work_order", {
            "customer_id": 41,
            "service_location_id": 77,
            "repeat_type": "none",
            "repeat_period": 1,
            "starts_at": "2026-10-11",
            "service_route_ids": [1],
        }, IDENTITY)
        self.assertEqual(blocked["gate"], "template_unverified")
