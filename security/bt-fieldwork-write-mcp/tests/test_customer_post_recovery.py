"""Customer POST response and read recovery. Mock HTTP only. No live Fieldwork calls."""

from __future__ import annotations

import io
import json
import unittest
from urllib.request import Request

from bt_fieldwork_write_mcp.fieldwork import HttpTransport, TypedFieldworkClient
from bt_fieldwork_write_mcp.secrets import InMemoryApiKey
from bt_fieldwork_write_mcp.service import WriteService
from tests.test_write_mcp import IDENTITY, Harness


def _payload(**extra: object) -> dict:
    body = {
        "customer_type": "Residential",
        "first_name": "Case",
        "last_name": "Evidence",
        "status": "active",
        "billing_phone": "9103330000",
        "billing_street": "105 Thorn Tree Ct",
        "billing_city": "Jacksonville",
        "billing_state": "NC",
        "service_locations": {"name": "Main Location", "same_as_billing_address": True},
        "contact": {"first_name": "Case", "last_name": "Evidence", "email": "case@example.test"},
        "confirmed_new": True,
        "acknowledge_duplicate_coverage": ["address", "email"],
    }
    body.update(extra)
    return body


class _Response:
    def __init__(self, status: int, body: bytes, content_type: str = "application/json") -> None:
        self.status = status
        self.headers = {"Content-Type": content_type}
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> bool:
        return False


class Script:
    def __init__(self, post_status: int = 201, post_body: bytes = b'{"id": 88001}', contact_body: bytes = b'{"id": 88002}', *, customers: list | None = None, store_contact: bool = True, drop_post: bool = False) -> None:
        self.requests: list[Request] = []
        self.post_status = post_status
        self.post_body = post_body
        self.contact_body = contact_body
        self.customers = list(customers or [])
        self.store_contact = store_contact
        self.drop_post = drop_post
        self.contacts: list[dict] = []
        self.posted = False
        self.customer_id_on_get = 88001
        self.location_customer_id = 88001
        self.location_street = "105 Thorn Tree Ct"
        self.location_name = "Main Location"
        self.extra_locations: list[dict] = []
        self.location_lists = 0

    def open(self, req: Request, timeout: int = 30) -> _Response:
        self.requests.append(req)
        path = req.full_url.split("api3.fieldworkhq.com")[-1].split("?")[0]
        if path.endswith("/v3.1"):
            path = "/"
        path = path.split("/v3.1", 1)[-1]
        if req.method == "POST" and path == "/customers":
            self.posted = True
            if not self.customers:
                self.customers = [_customer_row()]
            if self.drop_post:
                raise TimeoutError("drop")
            return _Response(self.post_status, self.post_body)
        if req.method == "POST" and path.endswith("/contacts"):
            if self.store_contact:
                self.contacts = [{"id": 88002, "customer_id": 88001, "first_name": "Case", "last_name": "Evidence", "email": "case@example.test"}]
            return _Response(200, self.contact_body)
        return _Response(200, json.dumps(self._get(path)).encode())

    def _get(self, path: str):
        if path == "/profile":
            return {"roles": ["customers", "work_orders", "schedule"]}
        if path == "/location_types":
            return [{"id": 8736, "name": "Residential"}]
        if path == "/customers/search":
            return self.customers if self.posted else []
        if path == "/customers/search_by_phone":
            return []
        if path.startswith("/customers/") and path.count("/") == 2:
            identity = path.rsplit("/", 1)[-1]
            row = _customer_row()
            row["id"] = self.customer_id_on_get if identity == "88001" else int(identity) if identity.isdigit() else row["id"]
            return row
        if path == "/customers/88001/service_locations":
            self.location_lists += 1
            rows = [_location_row(self.location_customer_id, self.location_street)]
            if self.location_lists > 1:
                rows.extend(self.extra_locations)
            return rows
        if path.startswith("/customers/88001/service_locations/"):
            identity = int(path.rsplit("/", 1)[-1])
            if identity == 88011:
                row = _location_row(self.location_customer_id, self.location_street)
                row["name"] = self.location_name
                row["location_type_id"] = 8736
                return {"service_location": row}
            found = next((row for row in self.extra_locations if row.get("id") == identity), None)
            return {"service_location": found} if found else []
        if path == "/customers/88001/contacts":
            return self.contacts
        return []

    def posts(self, suffix: str) -> int:
        return sum(1 for req in self.requests if req.method == "POST" and req.full_url.split("?")[0].endswith(suffix))


def _customer_row() -> dict:
    return {
        "id": 88001,
        "customer_type": "Residential",
        "first_name": "Case",
        "last_name": "Evidence",
        "name": "Case Evidence",
        "status": "active",
        "billing_phone": "9103330000",
        "billing_street": "105 Thorn Tree Ct",
        "billing_city": "Jacksonville",
        "billing_state": "NC",
    }


def _location_row(customer_id: int = 88001, street: str = "105 Thorn Tree Ct") -> dict:
    return {
        "id": 88011,
        "customer_id": customer_id,
        "name": "Main Location",
        "same_as_billing_address": True,
        "tax_rate_id": 3,
        "address": {"id": 12, "street": street, "city": "Jacksonville", "state": "NC"},
    }


class CustomerPostRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness(writes_enabled=True, api_role="writer")

    def tearDown(self) -> None:
        self.h.close()

    def _use(self, script: Script) -> None:
        self.script = script
        self.h.service.client = TypedFieldworkClient(HttpTransport(InMemoryApiKey("hidden-key"), opener=script))

    def _run(self, payload: dict | None = None) -> dict:
        proposed = self.h.service.propose("create_customer", payload or _payload(), IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        token = self.h.approve(proposed["proposal_id"])
        self.proposal = proposed
        return self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)

    def test_integer_id_success_posts_customer_once(self) -> None:
        self._use(Script())
        done = self._run()
        self.assertTrue(done["ok"], done)
        self.assertEqual(done["created_id"], 88001)
        self.assertFalse(done["reconciled"])
        self.assertEqual(done["readback"]["contact"]["email"], "case@example.test")
        self.assertEqual(self.script.posts("/customers"), 1)
        self.assertEqual(self.script.posts("/contacts"), 1)

    def test_empty_success_recovers_one_new_account_and_continues_contact(self) -> None:
        self._use(Script(post_status=200, post_body=b""))
        done = self._run()
        self.assertTrue(done["ok"], done)
        self.assertTrue(done["reconciled"])
        self.assertEqual(done["created_id"], 88001)
        self.assertEqual(done["readback"]["location_id"], 88011)
        self.assertEqual(self.script.posts("/customers"), 1)
        self.assertEqual(self.script.posts("/contacts"), 1)
        journal = self.h.store.creation_journal(self.proposal["proposal_id"])
        customer_step = next(row for row in journal if row["step"] == "customer_post")
        self.assertEqual(customer_step["outcome"], "succeeded")
        self.assertEqual(customer_step["result"]["response"]["parser_stage"], "empty_body")
        self.assertEqual(customer_step["result"]["response"]["status"], 200)
        self.assertFalse(customer_step["result"]["response"]["response_body_retained"])

    def test_unverified_wrapper_is_not_an_id_and_still_recovers(self) -> None:
        self._use(Script(post_body=b'{"customer":{"id":88001}}'))
        done = self._run()
        self.assertTrue(done["reconciled"], done)
        self.assertEqual(self.script.posts("/customers"), 1)
        journal = self.h.store.creation_journal(self.proposal["proposal_id"])
        response = next(row for row in journal if row["step"] == "customer_post")["result"]["response"]
        self.assertEqual(response["top_level_keys"], ["customer"])
        self.assertNotIn("88001", json.dumps(response))

    def test_multiple_preexisting_and_incomplete_do_not_bind_or_repost(self) -> None:
        self._use(Script(post_body=b"", customers=[{**_customer_row(), "id": 1}, {**_customer_row(), "id": 2}]))
        many = self._run()
        self.assertEqual(many["partial"]["reason"], "multiple_new_matches")
        self.assertIsNone(many["partial"]["customer_id"])
        self.assertEqual(self.script.posts("/customers"), 1)
        self.h.service.execute(self.proposal["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(self.script.posts("/customers"), 1)

    def test_preexisting_and_incomplete_search_do_not_bind(self) -> None:
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        prior = Script(post_body=b"", customers=[_customer_row()])
        prior.posted = True
        self._use(prior)
        preexisting = self._run()
        self.assertEqual(preexisting["partial"]["reason"], "preexisting_match")
        self.assertEqual(self.script.posts("/customers"), 1)

        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        incomplete = Script(post_body=b"")
        incomplete.customers = [{"id": index, "name": "Case Evidence", "first_name": "Case", "last_name": "Evidence", "billing_phone": "9103330000"} for index in range(1, 101)]
        self._use(incomplete)
        failed = self._run()
        self.assertEqual(failed["partial"]["reason"], "duplicate_search_incomplete")
        self.assertEqual(self.script.posts("/customers"), 1)

    def test_email_or_street_is_a_coverage_gap_and_does_not_post(self) -> None:
        self._use(Script())
        email_only = _payload()
        email_only.pop("acknowledge_duplicate_coverage")
        email_only.pop("billing_street")
        email_only.pop("billing_city")
        email_only.pop("billing_state")
        emailed = self.h.service.propose("create_customer", email_only, IDENTITY)
        self.assertEqual(emailed["gate"], "duplicate_search_incomplete")
        self.assertEqual(emailed["reason"], "coverage_acknowledgment_required")
        self.assertEqual(emailed["coverage_gap"], ["email"])
        street_only = _payload()
        street_only.pop("acknowledge_duplicate_coverage")
        street_only.pop("contact")
        addressed = self.h.service.propose(
            "create_customer",
            street_only,
            IDENTITY,
        )
        self.assertEqual(addressed["reason"], "coverage_acknowledgment_required")
        self.assertIn("address", addressed["coverage_gap"])
        self.assertEqual(self.script.posts("/customers"), 0)
        self.assertEqual(self.script.posts("/contacts"), 0)

    def test_transport_drop_diagnostic_is_unknown_and_can_recover(self) -> None:
        self._use(Script(drop_post=True))
        done = self._run()
        self.assertTrue(done["reconciled"], done)
        journal = self.h.store.creation_journal(self.proposal["proposal_id"])
        response = next(row for row in journal if row["step"] == "customer_post")["result"]["response"]
        self.assertEqual(response["status"], "unknown")
        self.assertEqual(response["parser_stage"], "transport_drop")
        self.assertEqual(self.script.posts("/customers"), 1)

    def test_conflicting_identity_does_not_post_again(self) -> None:
        self._use(Script())
        self.script.contacts = [{
            "id": 88002,
            "customer_id": 88001,
            "first_name": "Case",
            "last_name": "Evidence",
            "email": "case@example.test",
            "phone": "9100000000",
        }]
        phone = self._run(_payload(contact={"first_name": "Case", "last_name": "Evidence", "email": "case@example.test", "phone": "9103330000"}))
        self.assertEqual(phone["partial"]["reason"], "contact_field_conflict")
        self.assertEqual(self.script.posts("/contacts"), 0)
        self.assertEqual(self.script.posts("/customers"), 1)

        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        self._use(Script())
        self.script.extra_locations = [{
            "id": 88012,
            "customer_id": 88001,
            "name": "Shop",
            "tax_rate_id": 7704,
            "address": {"id": 13, "street": "9 Wrong", "city": "Jacksonville", "state": "NC"},
        }]
        extra = self._run(_payload(additional_location={"name": "Shop", "tax_rate_id": 7704, "address": {"street": "2 Side", "city": "Jacksonville", "state": "NC"}}))
        self.assertEqual(extra["partial"]["reason"], "location_field_conflict")
        self.assertEqual(self.script.posts("/service_locations"), 0)

        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        wrong_customer = Script(post_body=b"")
        self._use(wrong_customer)
        wrong_customer.customer_id_on_get = 99999
        customer = self._run()
        self.assertEqual(customer["partial"]["reason"], "identity_not_proved")
        self.assertEqual(self.script.posts("/contacts"), 0)
        again = self.h.service.execute(self.proposal["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(again["gate"], "ambiguous_remote_write_no_retry")
        self.assertEqual(self.script.posts("/customers"), 1)

        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        wrong_owner = Script(post_body=b"")
        self._use(wrong_owner)
        wrong_owner.location_customer_id = 5
        owner = self._run()
        self.assertEqual(owner["partial"]["reason"], "identity_not_proved")
        self.assertEqual(self.script.posts("/contacts"), 0)

        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        wrong_street = Script(post_body=b"")
        self._use(wrong_street)
        wrong_street.location_name = "Other"
        street = self._run()
        self.assertEqual(street["partial"]["reason"], "identity_not_proved")
        self.assertEqual(self.script.posts("/contacts"), 0)

    def test_wrong_digest_expiry_and_replay_do_not_post(self) -> None:
        self._use(Script())
        proposed = self.h.service.propose("create_customer", _payload(), IDENTITY)
        token = self.h.approve(proposed["proposal_id"])
        wrong = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval="not-the-token")
        self.assertEqual(wrong["gate"], "operator_approval_required")
        self.assertEqual(self.script.posts("/customers"), 0)
        self.h.service._now = lambda: self.h.clock.replace(year=2027)
        expired = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(expired["gate"], "approval_or_proposal_expired")
        self.assertEqual(self.script.posts("/customers"), 0)
