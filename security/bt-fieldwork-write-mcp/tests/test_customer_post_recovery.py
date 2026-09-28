"""Customer POST response and read recovery. Mock HTTP only. No live Fieldwork calls."""

from __future__ import annotations

import io
import json
import unittest
import urllib.parse
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
    def __init__(self, post_status: int = 201, post_body: bytes = b'{"id": 88001}', contact_body: bytes = b'{"id": 88002}', *, customers: list | None = None, store_contact: bool = True, drop_post: bool = False, customer_factory=None) -> None:
        self.requests: list[Request] = []
        self.post_status = post_status
        self.post_body = post_body
        self.contact_body = contact_body
        self.customers = list(customers or [])
        self.store_contact = store_contact
        self.drop_post = drop_post
        self.customer_factory = customer_factory or _customer_row
        self.contacts: list[dict] = []
        self.posted = False
        self.customer_id_on_get = 88001
        self.location_customer_id = 88001
        self.location_street = "105 Thorn Tree Ct"
        self.location_name = "Main Location"
        self.extra_locations: list[dict] = []
        self.location_lists = 0
        self.invoice_email: str | None = None
        self.patches: list[tuple[str, dict]] = []

    def open(self, req: Request, timeout: int = 30) -> _Response:
        self.requests.append(req)
        path = req.full_url.split("api3.fieldworkhq.com")[-1].split("?")[0]
        if path.endswith("/v3.1"):
            path = "/"
        path = path.split("/v3.1", 1)[-1]
        if req.method == "POST" and path == "/customers":
            self.posted = True
            if not self.customers:
                self.customers = [self.customer_factory()]
            if self.drop_post:
                raise TimeoutError("drop")
            return _Response(self.post_status, self.post_body)
        if req.method == "PATCH":
            form = _form(req)
            self.patches.append((path, form))
            email = form.get("customer[invoice_email]")
            if path == "/customers/88001" and isinstance(email, str):
                self.invoice_email = email
            return _Response(200, b"{}")
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
            found = next((row for row in self.customers if str(row.get("id")) == identity), None)
            if identity == "88001" or found is None:
                row = self.customer_factory()
                row["id"] = self.customer_id_on_get if identity == "88001" else int(identity) if identity.isdigit() else row["id"]
            else:
                row = dict(found)
            if self.invoice_email is not None and identity == "88001":
                row["invoice_email"] = self.invoice_email
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
                if self.invoice_email is not None:
                    row["email"] = self.invoice_email
                return {"service_location": row}
            found = next((row for row in self.extra_locations if row.get("id") == identity), None)
            return {"service_location": found} if found else []
        if path == "/customers/88001/contacts":
            return self.contacts
        return []

    def posts(self, suffix: str) -> int:
        return sum(1 for req in self.requests if req.method == "POST" and req.full_url.split("?")[0].endswith(suffix))


def _form(req: Request) -> dict[str, str]:
    raw = req.data.decode() if isinstance(req.data, bytes) else str(req.data or "")
    parsed = urllib.parse.parse_qs(raw, keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items()}


def _customer_row() -> dict:
    return {
        "id": 88001,
        "customer_type": "Residential",
        "first_name": "Case",
        "last_name": "Evidence",
        "name": "Case Evidence",
        "status": "active",
        "billing_phone": "9103330000",
        "billing_phone_kind": "Mobile",
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


WRAPPER = b'{"customer":{"wrapped":true}}'
LAST_ONLY = "B&T Reminder Creation Test 2026-09-28"


def _ada(**extra: object) -> dict:
    body = {
        "customer_type": "Residential",
        "first_name": "Ada",
        "last_name": "Ng",
        "name": "Ada  Ng",
        "status": "active",
        "billing_phone": "9105550147",
        "billing_street": "111 Thorn Tree Ct",
        "billing_city": "Jacksonville",
        "billing_state": "NC",
        "primary_email": "ada-ng@example.invalid",
        "service_locations": {"name": "Main Location", "same_as_billing_address": True},
        "acknowledge_duplicate_coverage": ["address", "email"],
        "confirmed_new": True,
    }
    body.update(extra)
    return body


def _ada_row(**extra: object) -> dict:
    row = {
        "id": 88001,
        "customer_type": "Residential",
        "first_name": "Ada",
        "last_name": "Ng",
        "name": "",
        "customer_name": "Ada Ng",
        "billing_name": "Ada Ng",
        "status": "active",
        "billing_phone": "9105550147",
        "billing_phone_kind": "Mobile",
        "billing_street": "111 Thorn Tree Ct",
        "billing_city": "Jacksonville",
        "billing_state": "NC",
        "billing_address": {"street": "111 Thorn Tree Ct", "city": "Jacksonville", "state": "NC"},
    }
    row.update(extra)
    return row


def _last_only(**extra: object) -> dict:
    body = _ada()
    body.pop("first_name")
    body["last_name"] = LAST_ONLY
    body["name"] = LAST_ONLY
    body.update(extra)
    return body


def _last_row(**extra: object) -> dict:
    row = _ada_row()
    row.pop("first_name")
    row["last_name"] = LAST_ONLY
    row["customer_name"] = LAST_ONLY
    row["billing_name"] = LAST_ONLY
    row.update(extra)
    return row


def _shop() -> dict:
    return {
        "customer_type": "Commercial",
        "name": "Shop",
        "billing_phone": "9105550147",
        "billing_street": "111 Thorn Tree Ct",
        "billing_city": "Jacksonville",
        "billing_state": "NC",
        "service_locations": {"name": "Shop", "same_as_billing_address": True},
        "location_type_id": 8736,
        "acknowledge_duplicate_coverage": ["address"],
        "confirmed_new": True,
    }


class ResidentialNameSemanticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness(writes_enabled=True, api_role="writer")

    def tearDown(self) -> None:
        self.h.close()

    def _use(self, script: Script) -> None:
        script.location_street = "111 Thorn Tree Ct"
        self.script = script
        self.h.service.client = TypedFieldworkClient(HttpTransport(InMemoryApiKey("hidden-key"), opener=script))

    def _reset(self, script: Script) -> None:
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        self._use(script)

    def _run(self, payload: dict, script: Script | None = None) -> dict:
        if script is not None:
            self._use(script)
        proposed = self.h.service.propose("create_customer", payload, IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        self.proposal = proposed
        token = self.h.approve(proposed["proposal_id"])
        return self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)

    def _posted_form(self) -> dict[str, str]:
        req = next(req for req in self.script.requests if req.method == "POST" and req.full_url.split("?")[0].endswith("/customers"))
        return _form(req)

    def _patches(self, suffix: str) -> list[dict]:
        return [body for path, body in self.script.patches if path.endswith(suffix) or suffix in path]

    def test_redundant_first_and_last_name_recovers_when_fieldwork_name_is_blank(self) -> None:
        from bt_fieldwork_write_mcp.create_contract import response_id

        self.assertIsNone(response_id({"customer": {"id": 88001}}))
        done = self._run(_ada(), Script(post_status=201, post_body=WRAPPER, customer_factory=_ada_row))
        customer = self.proposal["after"]["documented_request"]["customer"]
        self.assertNotIn("name", customer)
        self.assertEqual(customer["first_name"], "Ada")
        self.assertEqual(customer["last_name"], "Ng")
        self.assertNotIn("reminders_type", customer["service_locations_attributes"][0])
        self.assertEqual(self.proposal["after"]["intended_display_name"], "Ada Ng")
        self.assertFalse(self.proposal["after"]["residential_name"]["customer_name_sent"])
        self.assertEqual(self.proposal["after"]["residential_name"]["caller_name"], "Ada  Ng")
        self.assertTrue(self.proposal["immutable"])
        self.assertTrue(done["ok"], done)
        self.assertTrue(done["reconciled"])
        self.assertEqual(done["created_id"], 88001)
        self.assertEqual(done["readback"]["location_id"], 88011)
        self.assertEqual(done["readback"]["primary_email"]["value"], "ada-ng@example.invalid")
        self.assertEqual(done["readback"]["location_type_id"]["value"], 8736)
        self.assertIsNone(done["readback"]["contact_id"])
        self.assertFalse(self.proposal["after"]["creation_time_reminders_experiment"])
        posted = self._posted_form()
        self.assertNotIn("customer[name]", posted)
        self.assertEqual(posted["customer[first_name]"], "Ada")
        self.assertEqual(posted["customer[last_name]"], "Ng")
        self.assertFalse(any("reminders_type" in key for key in posted))
        self.assertNotIn("customer[invoice_email]", posted)
        self.assertEqual(self.script.posts("/customers"), 1)
        self.assertEqual(self.script.posts("/contacts"), 0)
        location_patches = [body for path, body in self.script.patches if "/service_locations/" in path]
        invoice_patches = [body for path, body in self.script.patches if path == "/customers/88001"]
        self.assertEqual(len(location_patches), 1)
        self.assertEqual(location_patches[0]["service_location[location_type_id]"], "8736")
        self.assertEqual(location_patches[0]["service_location[reminders_type]"], "0")
        self.assertEqual(invoice_patches, [{"customer[invoice_email]": "ada-ng@example.invalid"}])
        journal = self.h.store.creation_journal(self.proposal["proposal_id"])
        response = next(row for row in journal if row["step"] == "customer_post")["result"]["response"]
        self.assertEqual(response["top_level_keys"], ["customer"])
        self.assertEqual(response["status"], 201)
        self.assertNotIn("88001", json.dumps(response))
        again = self.h.service.execute(self.proposal["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(again["gate"], "approval_replayed")
        self.assertEqual(self.script.posts("/customers"), 1)
        self.assertEqual(len([body for path, body in self.script.patches if "/service_locations/" in path]), 1)

    def test_last_name_only_redundant_name_uses_the_same_rule(self) -> None:
        done = self._run(_last_only(), Script(post_body=WRAPPER, customer_factory=_last_row))
        customer = self.proposal["after"]["documented_request"]["customer"]
        self.assertNotIn("name", customer)
        self.assertNotIn("first_name", customer)
        self.assertEqual(customer["last_name"], LAST_ONLY)
        self.assertEqual(self.proposal["after"]["intended_display_name"], LAST_ONLY)
        self.assertTrue(done["ok"], done)
        self.assertTrue(done["reconciled"])
        posted = self._posted_form()
        self.assertEqual(posted["customer[last_name]"], LAST_ONLY)
        self.assertNotIn("customer[name]", posted)
        self.assertNotIn("customer[first_name]", posted)
        self.assertEqual(self.script.posts("/customers"), 1)
        self.assertEqual(self.script.posts("/contacts"), 0)

    def test_conflicting_residential_name_fails_before_write(self) -> None:
        self._use(Script(post_body=WRAPPER, customer_factory=_ada_row))
        conflicts = [
            _ada(name="Not Ada Ng"),
            _ada(name="Ng"),
            _ada(name="ada ng"),
            _ada(name=""),
            _ada(name=12),
        ]
        gates = []
        for payload in conflicts:
            failed = self.h.service.propose("create_customer", payload, IDENTITY)
            gates.append((failed.get("gate"), failed.get("fields"), failed.get("ok")))
        self.assertEqual(gates[:4], [("residential_name_conflict", ["name"], False)] * 4)
        self.assertEqual(gates[4][0], "unknown_field")
        self.assertEqual(self.script.posts("/customers"), 0)
        self.assertEqual(self.script.patches, [])

    def test_wrong_identity_phone_address_status_type_and_ownership_stay_rejected(self) -> None:
        from bt_fieldwork_write_mcp.creation_flow import _customer_matches

        sent = {
            "customer_type": "Residential",
            "first_name": "Ada",
            "last_name": "Ng",
            "status": "active",
            "billing_phone": "9105550147",
            "billing_street": "111 Thorn Tree Ct",
            "billing_city": "Jacksonville",
            "billing_state": "NC",
        }
        self.assertTrue(_customer_matches(_ada_row(), sent))
        self.assertFalse(_customer_matches(_ada_row(first_name="Eve"), sent))
        self.assertFalse(_customer_matches(_ada_row(last_name="No"), sent))
        self.assertFalse(_customer_matches(_ada_row(billing_phone="9100000000"), sent))
        self.assertFalse(_customer_matches(_ada_row(billing_street="9 Wrong", billing_address={"street": "9 Wrong"}), sent))
        self.assertFalse(_customer_matches(_ada_row(status="inactive"), sent))
        self.assertFalse(_customer_matches(_ada_row(customer_type="Commercial"), sent))
        commercial = {"customer_type": "Commercial", "name": "Shop", "status": "active"}
        self.assertFalse(_customer_matches({"customer_type": "Commercial", "name": "Other Shop", "status": "active"}, commercial))
        self.assertTrue(_customer_matches({"customer_type": "Commercial", "name": "Shop", "status": "active"}, commercial))

        cases = [
            (_ada_row(first_name="Eve"), "identity_not_proved"),
            (_ada_row(billing_phone="9100000000"), "identity_not_proved"),
            (_ada_row(billing_street="9 Wrong", billing_address={"street": "9 Wrong", "city": "Jacksonville", "state": "NC", "zip": "28540"}), "identity_not_proved"),
            (_ada_row(status="inactive"), "identity_not_proved"),
            (_ada_row(customer_type="Commercial"), "identity_not_proved"),
        ]
        for factory_row, reason in cases:
            self._reset(Script(post_body=WRAPPER, customer_factory=lambda row=factory_row: dict(row)))
            failed = self._run(_ada())
            self.assertEqual(failed["partial"]["reason"], reason)
            self.assertEqual(self.script.posts("/customers"), 1)
            self.assertEqual(self.script.posts("/contacts"), 0)
            self.assertEqual(self.script.patches, [])
            replay = self.h.service.execute(self.proposal["proposal_id"], IDENTITY, operator_approval="unused")
            self.assertEqual(replay["gate"], "ambiguous_remote_write_no_retry")
            self.assertEqual(self.script.posts("/customers"), 1)

        self._reset(Script(post_body=WRAPPER, customer_factory=_ada_row))
        self.script.customer_id_on_get = 99999
        wrong_id = self._run(_ada())
        self.assertEqual(wrong_id["partial"]["reason"], "identity_not_proved")
        self.assertEqual(self.script.patches, [])

        self._reset(Script(post_body=WRAPPER, customer_factory=_ada_row))
        self.script.location_customer_id = 5
        wrong_owner = self._run(_ada())
        self.assertEqual(wrong_owner["partial"]["reason"], "identity_not_proved")
        self.assertEqual(self.script.posts("/contacts"), 0)

        self._reset(Script(post_body=b'{"id": 88001}', customer_factory=lambda: _ada_row(last_name="No")))
        readback = self._run(_ada())
        self.assertEqual(readback["reason"], "field_mismatch")
        self.assertEqual(readback["partial"]["field"], "last_name")
        self.assertEqual(self.script.posts("/customers"), 1)
        again = self.h.service.execute(self.proposal["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertNotEqual(again.get("ok"), True)
        self.assertEqual(self.script.posts("/customers"), 1)

    def test_commercial_name_mismatch_stays_rejected(self) -> None:
        proposed = self.h.service.propose("create_customer", _shop(), IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        self.assertEqual(proposed["after"]["documented_request"]["customer"]["name"], "Shop")
        self.assertIsNone(proposed["after"]["residential_name"])
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        shop = _ada_row(customer_type="Commercial", name="Other Shop", customer_name="Other Shop", billing_name="Other Shop")
        shop.pop("first_name", None)
        shop.pop("last_name", None)
        self._use(Script(post_body=WRAPPER, customer_factory=lambda: dict(shop)))
        failed = self._run(_shop())
        self.assertEqual(failed["partial"]["reason"], "identity_not_proved")
        self.assertEqual(self._posted_form()["customer[name]"], "Shop")
        self.assertEqual(self.script.posts("/customers"), 1)
        self.assertEqual(self.script.patches, [])

    def test_no_multiple_preexisting_and_incomplete_matches_stay_blocked(self) -> None:
        self._use(Script(post_body=WRAPPER, customers=[{"id": 5, "name": "Other Person", "last_name": "Person", "billing_phone": "9100000000"}], customer_factory=_ada_row))
        missing = self._run(_ada())
        self.assertEqual(missing["partial"]["reason"], "no_new_match")
        self.assertEqual(self.script.posts("/customers"), 1)
        self.assertEqual(self.script.patches, [])

        self._reset(Script(post_body=WRAPPER, customers=[_ada_row(), {**_ada_row(), "id": 88002}], customer_factory=_ada_row))
        many = self._run(_ada())
        self.assertEqual(many["partial"]["reason"], "multiple_new_matches")
        self.assertIsNone(many["partial"]["customer_id"])
        self.assertEqual(self.script.posts("/customers"), 1)

        self._reset(Script(post_body=WRAPPER, customers=[_ada_row()], customer_factory=_ada_row))
        self.script.posted = True
        preexisting = self._run(_ada())
        self.assertEqual(preexisting["partial"]["reason"], "preexisting_match")
        self.assertEqual(self.script.posts("/customers"), 1)

        self._reset(Script(post_body=WRAPPER, customer_factory=_ada_row))
        self.script.customers = [{**_ada_row(), "id": index} for index in range(1, 101)]
        incomplete = self._run(_ada())
        self.assertEqual(incomplete["partial"]["reason"], "duplicate_search_incomplete")
        self.assertEqual(self.script.posts("/customers"), 1)
        self.assertEqual(self.script.patches, [])

    def test_approval_digest_expiry_and_user_binding_do_not_post(self) -> None:
        self._use(Script(post_body=WRAPPER, customer_factory=_ada_row))
        proposed = self.h.service.propose("create_customer", _ada(), IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        token = self.h.approve(proposed["proposal_id"])
        wrong = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval="not-the-token")
        self.assertEqual(wrong["gate"], "operator_approval_required")
        other = self.h.service.execute(proposed["proposal_id"], {"sub": "other", "email": "other@example.invalid"}, operator_approval=token)
        self.assertEqual(other["gate"], "identity_mismatch")
        stored = self.h.store.get_proposal(proposed["proposal_id"])
        after = stored["after"]
        after["documented_request"]["customer"]["name"] = "Ada Ng"
        self.h.store._conn.execute("UPDATE proposals SET after_json = ? WHERE proposal_id = ?", (json.dumps(after), proposed["proposal_id"]))
        altered = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(altered["reason"], "stored_proposal_digest_mismatch")
        self.assertEqual(self.script.posts("/customers"), 0)
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer")
        self._use(Script(post_body=WRAPPER, customer_factory=_ada_row))
        proposed = self.h.service.propose("create_customer", _ada(), IDENTITY)
        token = self.h.approve(proposed["proposal_id"])
        self.h.service._now = lambda: self.h.clock.replace(year=2027)
        expired = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)
        self.assertEqual(expired["gate"], "approval_or_proposal_expired")
        self.assertEqual(self.script.posts("/customers"), 0)
