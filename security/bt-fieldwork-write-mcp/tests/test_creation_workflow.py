"""Offline creation workflow. No live Fieldwork calls."""

from __future__ import annotations

import unittest
from datetime import timedelta

from bt_fieldwork_write_mcp.allowlist import GATE_DISTINCT_IDS, GATE_LEAD_STATUS, GATE_PARTIAL
from bt_fieldwork_write_mcp.service import WriteService
from bt_fieldwork_write_mcp.store import WriteStore
from tests.test_write_mcp import IDENTITY, OTHER, Harness


def _customer(**extra: object) -> dict:
    payload = {
        "customer_type": "Residential",
        "last_name": "Ng",
        "service_locations": [{"name": "Home", "same_as_billing_address": True}],
    }
    payload.update(extra)
    return payload


def _order() -> dict:
    return {
        "customer_id": 41,
        "service_location_id": 77,
        "repeat_type": "none",
        "repeat_period": 1,
        "occurrences": [{"service_route_ids": [1], "starts_at": "2026-10-02"}],
    }


class CreationWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness(writes_enabled=True, api_role="writer")
        self.h.transport.users = [{
            "id": 10, "first_name": "Sam", "last_name": "Lee", "email": "sam@example.test",
            "service_route_id": 1, "service_route_name": "North", "is_technician": True, "branches": [],
        }, {
            "id": 11, "first_name": "Riley", "last_name": "Cho", "email": "riley@example.test",
            "service_route_id": 1, "service_route_name": "North", "is_technician": False, "branches": [],
        }]

    def tearDown(self) -> None:
        self.h.close()

    def test_active_customer_and_lead_are_distinct(self) -> None:
        proposed = self.h.service.propose("create_customer", _customer(), IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        self.assertFalse(proposed["live_tested"])
        self.assertTrue(proposed["schema_ready"])
        executed = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=self.h.approve(proposed["proposal_id"]))
        self.assertTrue(executed["ok"], executed)
        self.assertEqual(executed["readback"]["status"], "active")
        self.assertEqual(executed["readback"]["contact_count"], 0)
        self.assertTrue(executed["readback"]["discoverable"])
        lead = self.h.service.propose("create_customer", _customer(status="lead"), IDENTITY)
        self.assertEqual(lead["gate"], GATE_LEAD_STATUS)
        self.h.transport.customers["41"]["customer_status"] = "Lead"
        blocked = self.h.service.propose("create_work_order", _order(), IDENTITY)
        self.assertEqual(blocked["gate"], GATE_LEAD_STATUS)

    def test_duplicate_search_pagination_and_resolution(self) -> None:
        self.h.transport.add_customer(
            {"id": 70, "name": "Ng", "customer_status": "Active", "email": "ng@example.test", "billing_phone": "(716) 555-0100", "billing_address": {"street": "1 Main", "city": "Buffalo"}},
            {"id": 71, "name": "House", "tax_rate_id": 3, "address": {"id": 8, "street": "1 Main"}},
        )
        blocked = self.h.service.propose("create_customer", _customer(billing_phone="716.555.0100"), IDENTITY)
        self.assertEqual(blocked["gate"], "duplicate_unresolved")
        self.assertEqual(blocked["candidates"][0]["email"], "ng@example.test")
        self.assertTrue(blocked["candidates"][0]["locations"])
        self.h.transport.customer_search_fault = "incomplete"
        incomplete = self.h.service.propose("create_customer", _customer(last_name="Other"), IDENTITY)
        self.assertEqual(incomplete["gate"], "duplicate_search_incomplete")
        self.h.transport.customer_search_fault = "error"
        failed = self.h.service.propose("create_customer", _customer(last_name="Other"), IDENTITY)
        self.assertEqual(failed["gate"], "duplicate_search_incomplete")
        self.h.transport.customer_search_fault = None
        resolved = self.h.service.propose("create_customer", _customer(billing_phone="7165550100", confirmed_new=True), IDENTITY)
        self.assertTrue(resolved["ok"], resolved)
        self.assertTrue(resolved["after"]["documented_request"]["duplicate_resolution"]["confirmed_new"])
        self.h.service.execute(resolved["proposal_id"], IDENTITY, operator_approval=self.h.approve(resolved["proposal_id"]))
        before = [call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/customers"]
        existing = self.h.service.propose("create_customer", _customer(billing_phone="7165550100", existing_customer_id=70), IDENTITY)
        self.assertTrue(existing["ok"], existing)
        executed = self.h.service.execute(existing["proposal_id"], IDENTITY, operator_approval=self.h.approve(existing["proposal_id"]))
        self.assertTrue(executed["ok"], executed)
        self.assertEqual([call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/customers"], before)

    def test_distinct_address_and_explicit_contact(self) -> None:
        from bt_fieldwork_write_mcp.create_contract import customer_request

        payload = _customer(
            billing_street="9 Billing",
            service_locations=[{"name": "Home", "same_as_billing_address": False}],
            service_address={"street": "4 Service", "city": "Buffalo", "state": "NY", "zip": "14201"},
            location_tax_rate_id=3,
            contact={"first_name": "Ada", "last_name": "Ng", "email": "ada@example.test"},
            additional_location={"name": "Shop", "tax_rate_id": 3},
        )
        plan = customer_request(payload)
        posted = plan["customer"]["service_locations_attributes"][0]
        self.assertEqual(set(posted), {"name", "same_as_billing_address"})
        self.assertEqual(plan["contact"]["email"], "ada@example.test")
        self.assertNotIn("allow_login_to_portal", plan["contact"])
        self.assertEqual(plan["location_patch"]["address_attributes"]["street"], "4 Service")
        self.assertEqual(set(plan["additional_location"]), {"name", "tax_rate_id"})
        proposed = self.h.service.propose("create_customer", payload, IDENTITY)
        self.assertEqual(proposed["reason"], "email_or_address_coverage_gap")
        self.assertEqual(proposed["coverage_gap"], ["email", "address"])
        self.assertFalse(any(call["method"] == "POST" for call in self.h.transport.calls))
        missing = self.h.service.propose("create_customer", _customer(last_name="Bare", contact={"first_name": "Ada", "last_name": "Ng"}), IDENTITY)
        self.assertEqual(missing["gate"], "contact_incomplete")

    def test_approval_digest_identity_and_stale_catalog(self) -> None:
        proposed = self.h.service.propose("create_work_order", _order(), IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        self.assertTrue(proposed["after"]["invoice_generation_disclosed"])
        self.assertEqual(proposed["after"]["invoice_generation_reason"], "billing_frequency_0_normal_invoice_generation")
        self.assertIsNone(proposed["after"]["auto_generates_invoice"])
        self.assertEqual(proposed["after"]["catalog"]["observed_line"]["quantity"], "1.0")
        self.assertEqual(proposed["after"]["catalog"]["observed_line"]["price"], "150.0")
        self.assertEqual(proposed["after"]["catalog"]["work_order_defaults"]["duration"], 60)
        self.assertIsNone(proposed["after"]["route_staff"][0]["assignee"])
        self.assertTrue(proposed["after"]["route_staff"][0]["ambiguous"])
        self.assertFalse(proposed["after"]["schedule"]["promised_window_enforced"])
        missing = self.h.service.execute(proposed["proposal_id"], IDENTITY)
        self.assertEqual(missing["gate"], "operator_approval_required")
        wrong = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval="not-a-token")
        self.assertEqual(wrong["gate"], "operator_approval_required")
        token = self.h.approve(proposed["proposal_id"])
        other = self.h.service.execute(proposed["proposal_id"], OTHER, operator_approval=token)
        self.assertEqual(other["gate"], "identity_mismatch")
        self.h.store._conn.execute("UPDATE proposals SET payload_json = '{}' WHERE proposal_id = ?", (proposed["proposal_id"],))
        changed = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(changed["gate"], "operator_approval_required")
        self.assertEqual(changed["reason"], "stored_proposal_digest_mismatch")
        self.assertFalse(any(call["method"] == "POST" and call["path"] == "/work_orders" for call in self.h.transport.calls))
        fresh = self.h.service.propose("create_work_order", {**_order(), "occurrences": [{"service_route_ids": [1], "starts_at": "2026-10-03"}]}, IDENTITY)
        self.h.transport.templates[0]["line_items"][0]["price"] = 999
        self.h.transport.services[0]["price"] = 999
        stale = self.h.service.execute(fresh["proposal_id"], IDENTITY, operator_approval=self.h.approve(fresh["proposal_id"]))
        self.assertEqual(stale["gate"], "stale_state")
        self.assertFalse(any(call["method"] == "POST" and call["path"] == "/work_orders" for call in self.h.transport.calls))
        self.h.transport.templates[0]["line_items"][0]["price"] = 150
        self.h.transport.services[0]["price"] = 150
        expiring = self.h.service.propose("create_work_order", {**_order(), "occurrences": [{"service_route_ids": [1], "starts_at": "2026-10-04"}]}, IDENTITY)
        expiring_token = self.h.approve(expiring["proposal_id"])
        self.h.clock = self.h.clock + timedelta(hours=3)
        later = self.h.service.execute(expiring["proposal_id"], IDENTITY, operator_approval=expiring_token)
        self.assertEqual(later["gate"], "approval_or_proposal_expired")

    def test_catalog_disagreement_and_schedule_price_readback(self) -> None:
        self.h.transport.services[0]["price"] = 151
        disagreed = self.h.service.propose("create_work_order", _order(), IDENTITY)
        self.assertEqual(disagreed["gate"], "catalog_disagreement")
        self.h.transport.services[0]["price"] = 150
        self.h.transport.templates[0]["auto_generates_invoice"] = True
        proposed = self.h.service.propose("create_work_order", _order(), IDENTITY)
        self.assertTrue(proposed["after"]["invoice_generation_disclosed"])
        self.assertNotEqual(proposed["after"]["catalog"]["template_id"], None)
        self.h.transport.readback_line_price = 1
        failed = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=self.h.approve(proposed["proposal_id"]))
        self.assertEqual(failed["gate"], GATE_PARTIAL)
        self.assertEqual(failed["reason"], "readback_failed")
        self.assertEqual(len([call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/work_orders"]), 1)
        again = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(again["gate"], "ambiguous_remote_write_no_retry")
        self.assertEqual(len([call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/work_orders"]), 1)
        self.h.transport.readback_line_price = None
        self.h.transport.templates[0].pop("auto_generates_invoice", None)
        clean = self.h.service.propose("create_work_order", {**_order(), "occurrences": [{"service_route_ids": [1], "starts_at": "2026-10-05", "duration": 60}]}, IDENTITY)
        done = self.h.service.execute(clean["proposal_id"], IDENTITY, operator_approval=self.h.approve(clean["proposal_id"]))
        self.assertTrue(done["ok"], done)
        self.assertNotEqual(done["readback"]["occurrence_id"], done["readback"]["service_appointment_id"])
        self.assertNotEqual(done["readback"]["occurrence_id"], clean["after"]["catalog"]["template_id"])
        self.assertEqual(done["readback"]["price"], clean["after"]["service_pricing"]["price"])
        self.assertEqual(done["readback"]["duration"], 60)
        self.assertEqual(done["readback"]["timezone"], "America/New_York")
        self.assertFalse(done["readback"]["clock_time_sent"])
        self.assertFalse(done["readback"]["promised_window_enforced"])
        self.assertTrue(done["readback"]["schedule_complete"])
        self.assertIn("started_at_time", self.h.service.propose("create_work_order", {**_order(), "occurrences": [{"service_route_ids": [1], "starts_at": "2026-10-06", "started_at_time": "1:00 PM", "finished_at_time": "2:00 PM"}]}, IDENTITY)["fields"])

    def test_timeout_crash_and_partial_recovery_do_not_repost(self) -> None:
        proposed = self.h.service.propose("create_customer", _customer(last_name="Partial"), IDENTITY)
        token = self.h.approve(proposed["proposal_id"])
        original = self.h.transport.request

        def request(method, path, body=None, query=None):
            if method == "PATCH" and "service_locations" in path:
                from bt_fieldwork_write_mcp.errors import AmbiguousWriteError

                self.h.transport.calls.append({"method": method, "path": path, "body": body, "query": query})
                raise AmbiguousWriteError("fake_ambiguous")
            return original(method, path, body, query)

        self.h.transport.request = request
        partial = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.h.transport.request = original
        self.assertEqual(partial["gate"], GATE_PARTIAL)
        self.assertEqual(partial["failed_step"], "location_patch")
        self.assertIsNotNone(partial["partial"]["customer_id"])
        posts = [call for call in self.h.transport.calls if call["method"] == "POST"]
        self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual([call for call in self.h.transport.calls if call["method"] == "POST"], posts)
        recovery = self.h.service.propose(
            "create_customer",
            _customer(existing_customer_id=int(partial["partial"]["customer_id"])),
            IDENTITY,
        )
        self.assertTrue(recovery["ok"] or recovery["gate"] in {"duplicate_unresolved", "duplicate_in_flight", "ambiguous_remote_write_no_retry"}, recovery)
        crashed = self.h.service.propose("create_customer", _customer(last_name="Crash"), IDENTITY)
        self.h.store.begin_creation_step(crashed["proposal_id"], "customer_post", {"intent": True})
        self.h.store.close()
        restarted = WriteStore(self.h.path)
        self.h.store = restarted
        service = WriteService(self.h.settings, restarted, self.h.client)
        service._now = lambda: self.h.clock
        blocked = service.execute(crashed["proposal_id"], IDENTITY, operator_approval=service.mint_approval(crashed["proposal_id"])["operator_approval"])
        self.assertEqual(blocked["gate"], "ambiguous_remote_write_no_retry")
        self.assertEqual(blocked["failed_step"], "customer_post")
        self.assertFalse(any(call["path"] == "/customers" and call["method"] == "POST" and call["body"] and call["body"].get("customer", {}).get("last_name") == "Crash" for call in self.h.transport.calls))

    def test_equal_occurrence_and_appointment_ids_fail(self) -> None:
        self.assertEqual(GATE_DISTINCT_IDS, "occurrence_appointment_not_distinct")
        proposed = self.h.service.propose("create_work_order", _order(), IDENTITY)
        original = self.h.transport._fake_work_order

        def same_ids(body):
            status, response = original(body)
            response["service_appointment_id"] = response["id"]
            stored = self.h.transport.work_orders[str(response["id"])]
            stored["service_appointment_id"] = response["id"]
            return status, response

        self.h.transport._fake_work_order = same_ids
        failed = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=self.h.approve(proposed["proposal_id"]))
        self.assertEqual(failed["gate"], GATE_DISTINCT_IDS)
        self.assertEqual(len([call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/work_orders"]), 1)

    def test_timed_start_posts_the_date_then_patches_the_offset_once(self) -> None:
        timed = "2026-10-02T10:00:00-04:00"
        proposed = self.h.service.propose("create_work_order", {**_order(), "occurrences": [{"service_route_ids": [1], "starts_at": timed, "duration": 60}]}, IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        posted = proposed["after"]["documented_request"]["service_appointment"]["appointment_occurrences_attributes"][0]
        self.assertEqual(posted["starts_at"], "2026-10-02")
        self.assertEqual(proposed["after"]["schedule_patch"]["starts_at"], timed)
        self.assertEqual(proposed["after"]["starts_at_instant"], timed)
        self.assertFalse(proposed["after"]["starts_at_post_ready"])
        self.assertFalse(proposed["after"]["starts_at_post_clock_live_tested"])
        self.assertFalse(proposed["after"]["live_tested"])
        done = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=self.h.approve(proposed["proposal_id"]))
        self.assertTrue(done["ok"], done)
        posts = [call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/work_orders"]
        patches = [call for call in self.h.transport.calls if call["method"] == "PATCH" and call["path"].startswith("/work_orders/")]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["body"]["service_appointment"]["appointment_occurrences_attributes"][0]["starts_at"], "2026-10-02")
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0]["body"]["service_appointment"]["appointment_occurrences_attributes"][0]["starts_at"], timed)
        self.assertEqual(done["readback"]["starts_at"], timed)
        zulu = self.h.service.propose("create_work_order", {**_order(), "occurrences": [{"service_route_ids": [1], "starts_at": "2026-10-02T10:00:00Z"}]}, IDENTITY)
        self.assertEqual(zulu["gate"], "starts_at_datetime_unverified")

    def _timed(self, starts_at: str = "2026-10-02T10:00:00-04:00") -> dict:
        return {**_order(), "occurrences": [{"service_route_ids": [1], "starts_at": starts_at, "duration": 60}]}

    def _patches(self) -> list:
        return [call for call in self.h.transport.calls if call["method"] == "PATCH" and call["path"].startswith("/work_orders/")]

    def test_expiry_after_post_does_not_patch(self) -> None:
        proposed = self.h.service.propose("create_work_order", self._timed(), IDENTITY)
        original = self.h.client.create_work_order

        def expire_after(body):
            response = original(body)
            self.h.clock = self.h.clock + timedelta(hours=3)
            return response

        self.h.client.create_work_order = expire_after
        stopped = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=self.h.approve(proposed["proposal_id"]))
        self.assertEqual(stopped["gate"], GATE_PARTIAL)
        self.assertEqual(stopped["failed_step"], "work_order_schedule_patch")
        self.assertEqual(stopped["partial"]["reason"], "proposal_expired")
        self.assertEqual(stopped["retry"], False)
        self.assertIsNotNone(stopped["partial"]["occurrence_id"])
        self.assertIsNotNone(stopped["partial"]["service_appointment_id"])
        self.assertEqual(self._patches(), [])
        again = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertFalse(again["ok"])
        self.assertEqual(self._patches(), [])

    def test_ambiguous_patch_not_landed_keeps_partial_ids(self) -> None:
        proposed = self.h.service.propose("create_work_order", self._timed("2026-10-06T10:00:00-04:00"), IDENTITY)
        original = self.h.transport.request

        def fail_patch(method, path, body=None, query=None):
            if method == "PATCH" and str(path).startswith("/work_orders/"):
                self.h.transport.fail_write_exact.add(path)
            return original(method, path, body, query)

        self.h.transport.request = fail_patch
        stopped = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=self.h.approve(proposed["proposal_id"]))
        self.assertEqual(stopped["gate"], GATE_PARTIAL)
        self.assertEqual(stopped["partial"]["reason"], "schedule_patch_unresolved")
        self.assertEqual(stopped["retry"], False)
        self.assertIsNotNone(stopped["partial"]["occurrence_id"])
        self.assertNotEqual(stopped["partial"]["occurrence_id"], stopped["partial"]["service_appointment_id"])
        self.assertEqual(len(self._patches()), 1)
        again = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(again["gate"], "ambiguous_remote_write_no_retry")
        self.assertEqual(len(self._patches()), 1)

    def test_ambiguous_patch_that_landed_is_verified_success(self) -> None:
        proposed = self.h.service.propose("create_work_order", self._timed("2026-10-07T10:00:00-04:00"), IDENTITY)
        self.h.transport.write_mode = "timeout_after_apply"
        done = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=self.h.approve(proposed["proposal_id"]))
        self.assertTrue(done["ok"], done)
        self.assertEqual(done["readback"]["starts_at"], "2026-10-07T10:00:00-04:00")
        self.assertEqual(len(self._patches()), 1)

    def test_created_get_must_match_before_patch(self) -> None:
        cases = ("appointment", "customer", "location", "duration")
        for index, case in enumerate(cases):
            proposed = self.h.service.propose("create_work_order", self._timed(f"2026-10-{8 + index:02d}T11:00:00-04:00"), IDENTITY)
            original = self.h.transport._fake_work_order

            def mismatch(body, case=case, original=original):
                status, response = original(body)
                stored = self.h.transport.work_orders[str(response["id"])]
                if case == "appointment":
                    response["service_appointment_id"] = 1
                elif case == "customer":
                    stored["customer_id"] = 999
                elif case == "location":
                    stored["service_location_id"] = 999
                else:
                    stored["duration"] = 15
                return status, response

            self.h.transport._fake_work_order = mismatch
            stopped = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=self.h.approve(proposed["proposal_id"]))
            self.assertEqual(stopped["gate"], GATE_PARTIAL, case)
            self.assertEqual(stopped["partial"]["reason"], "created_state_mismatch", case)
            self.assertEqual(stopped["retry"], False)
            self.assertIsNotNone(stopped["partial"]["occurrence_id"])
            self.assertFalse(any(call["method"] == "PATCH" and call["path"].startswith("/work_orders/") for call in self.h.transport.calls), case)
            self.h.transport._fake_work_order = original

    def test_schedule_recheck_and_new_duplicate_need_approval(self) -> None:
        proposed = self.h.service.propose("create_work_order", _order(), IDENTITY)
        self.h.transport.work_orders["80"] = {
            "id": 80, "service_appointment_id": 81, "customer_id": 41, "service_location_id": 77,
            "starts_at": "2026-10-02", "starts_at_date": "2026-10-02", "service_route_ids": [1], "duration": 30,
        }
        blocked = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=self.h.approve(proposed["proposal_id"]))
        self.assertEqual(blocked["gate"], "stale_state")
        self.assertEqual(blocked["reason"], "schedule_changed")
        self.assertFalse(any(call["method"] == "POST" and call["path"] == "/work_orders" for call in self.h.transport.calls))
        fresh = self.h.service.propose("create_customer", _customer(first_name="Ada", last_name="River", confirmed_new=True), IDENTITY)
        queries = [call["query"]["query"] for call in self.h.transport.calls if call["path"] == "/customers/search"]
        self.assertIn("ada river", queries)
        self.assertIn("river", queries)
        self.h.transport.add_customer(
            {"id": 90, "name": "River", "last_name": "River", "customer_status": "Active"},
            {"id": 91, "name": "Home", "tax_rate_id": 3, "address": {"id": 4}},
        )
        denied = self.h.service.execute(fresh["proposal_id"], IDENTITY, operator_approval=self.h.approve(fresh["proposal_id"]))
        self.assertEqual(denied["gate"], "duplicate_unresolved")
        self.assertEqual(denied["reason"], "new_match_requires_approval")
        self.assertFalse(any(call["method"] == "POST" and call["path"] == "/customers" for call in self.h.transport.calls))

    def test_readback_compares_every_sent_field(self) -> None:
        from bt_fieldwork_write_mcp.creation_flow import customer_readback, response_labels
        from bt_fieldwork_write_mcp.errors import GateError

        payload = _customer(
            last_name="Read",
            billing_phone="7165550199",
            billing_phone_kind="Home",
        )
        proposed = self.h.service.propose("create_customer", payload, IDENTITY)
        executed = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=self.h.approve(proposed["proposal_id"]))
        self.assertTrue(executed["ok"], executed)
        self.assertTrue(executed["readback"]["matched_sent_fields"])
        self.assertTrue(executed["readback"]["test_double"])
        self.assertEqual(executed["readback"]["customer"]["billing_phone_kind"], "Home")
        self.assertEqual(executed["readback"]["reminders_type"]["status"], "unverified")
        self.h.transport.customers[str(executed["created_id"])]["billing_phone_kind"] = "Office"
        with self.assertRaises(GateError) as caught:
            customer_readback(
                self.h.client,
                str(executed["created_id"]),
                sent_customer=proposed["after"]["documented_request"]["customer"],
                contact=None,
                location_id=str(executed["readback"]["location_id"]),
                address=None,
                main_location=proposed["after"]["documented_request"]["main_location"],
            )
        self.assertEqual(caught.exception.detail["field"], "billing_phone_kind")

        class Other:
            is_fake_double = False

        self.assertFalse(response_labels(type("C", (), {"transport": Other()})())["test_double"])


if __name__ == "__main__":
    unittest.main()
