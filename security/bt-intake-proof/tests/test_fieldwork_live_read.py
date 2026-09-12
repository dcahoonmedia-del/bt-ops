import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bt_intake_proof.fieldwork_booking import LABEL_FIXTURE, LABEL_LIVE, operational_context
from bt_intake_proof.fieldwork_fixture import GrokBotFieldwork
from bt_intake_proof.fieldwork_live_read import (
    AUTHORIZED_LABELS,
    EXAMPLE_MANIFEST,
    SYNTHETIC_CATALOG,
    SYNTHETIC_NO_MATCH_QUERY,
    compare_to_direct,
    direct_read_bundle,
    fixture_client,
    load_manifest,
    preflight,
    resolve_authorized,
    run_bounded_read,
    scenario_receipt,
)
from bt_intake_proof.fieldwork_match import (
    MATCH_AMBIGUOUS,
    MATCH_BLOCKED,
    MATCH_EXISTING,
    MATCH_INCOMPLETE,
    MATCH_INSUFFICIENT,
    MATCH_NONE,
    _status,
    location_for,
    match_and_context,
    score_candidate,
    street_matches,
    street_number_in_blob,
)
from bt_intake_proof.fieldwork_readonly import (
    FieldworkReadError,
    FieldworkWriteForbidden,
    ReadOnlyFieldworkClient,
    grok_bot_client,
    live_read_client,
    parse_collection,
)

SHELLEY = (
    "Hi, this is Shelley Fixture. Ants at 14 Oak Street, Holly Ridge NC 28445. "
    "910-555-7701 shelley.fixture.syn@example.com"
)


class StreetAndStatusTests(unittest.TestCase):
    def test_fourteen_does_not_match_two_fourteen(self) -> None:
        self.assertTrue(street_number_in_blob("14", "14 oak street"))
        self.assertFalse(street_number_in_blob("14", "214 oak street"))
        self.assertTrue(street_matches("14 Oak Street", "14 oak street holly ridge"))
        self.assertFalse(street_matches("14 Oak Street", "214 oak street holly ridge"))

    def test_missing_status_is_unknown_not_active(self) -> None:
        self.assertEqual(_status({"name": "x"}), "unknown")
        self.assertEqual(_status({"customer_status": None}), "unknown")
        self.assertEqual(_status({"customer_status": "lead"}), "lead")

    def test_score_uses_best_property_only(self) -> None:
        customer = {"id": 77001, "name": "Shelley Fixture", "email": "shelley.fixture.syn@example.com"}
        locations = [
            {"id": 66001, "address": {"street": "14 Oak Street", "city": "Holly Ridge", "zip": "28445"}},
            {"id": 66002, "address": {"street": "214 Oak Street", "city": "Holly Ridge", "zip": "28445"}},
        ]
        identifiers = {
            "emails": ["shelley.fixture.syn@example.com"],
            "phones": [],
            "names": ["Shelley Fixture"],
            "addresses": [{"street": "14 Oak Street", "city": "Holly Ridge", "zip": "28445"}],
        }
        scored = score_candidate(customer, locations, identifiers)
        self.assertIn("street", scored["hits"])
        loc = location_for(scored, identifiers)
        self.assertEqual(loc["id"], 66001)


class MatcherFailurePathTests(unittest.TestCase):
    def test_auth_failure_is_blocked_not_no_match(self) -> None:
        def getter(path: str, params: dict) -> dict:
            raise FieldworkReadError("http_401")

        client = ReadOnlyFieldworkClient(token="x", getter=getter, live=True)
        evidence = match_and_context(
            client,
            {"sender": "a@b.com", "subject": "x", "body_text": "This is Nobody Proof. 910-555-0000 nobody@example.org"},
        )
        self.assertEqual(evidence["status"], MATCH_BLOCKED)
        self.assertEqual(evidence["reason"], "http_401")
        self.assertTrue(evidence["live"])
        self.assertEqual(evidence["source_label"], LABEL_LIVE)

    def test_schema_mismatch_is_blocked(self) -> None:
        def getter(path: str, params: dict) -> dict:
            return {"unexpected": True}

        client = ReadOnlyFieldworkClient(token="x", getter=getter, live=True)
        evidence = match_and_context(
            client,
            {"sender": "a@b.com", "subject": "x", "body_text": "This is Nobody Proof. 910-555-0000 nobody@example.org"},
        )
        self.assertEqual(evidence["status"], MATCH_BLOCKED)
        self.assertEqual(evidence["reason"], "schema_mismatch")

    def test_truncated_search_is_incomplete_not_no_match(self) -> None:
        def full_pages(path: str, params: dict) -> list:
            if path == "/v3.1/customers/search":
                return [{"id": i, "name": f"Pad {i}"} for i in range(int(params.get("per_page") or 1))]
            if path.startswith("/v3.1/customers/") and path.count("/") == 3:
                return {"id": int(path.rsplit("/", 1)[-1]), "name": "Pad"}
            return []

        client = ReadOnlyFieldworkClient(token="x", getter=full_pages, live=False, per_page=1, max_pages=2)
        evidence = match_and_context(
            client,
            {
                "sender": "nobody.proof.syn@example.org",
                "subject": SYNTHETIC_NO_MATCH_QUERY,
                "body_text": (
                    "This is Nobody Proof at 999 Missing Avenue, Nowhere NC 00000. "
                    f"910-555-0000 nobody.proof.syn@example.org {SYNTHETIC_NO_MATCH_QUERY}"
                ),
            },
        )
        self.assertEqual(evidence["status"], MATCH_INCOMPLETE)
        self.assertNotEqual(evidence["status"], MATCH_NONE)

    def test_no_identifiers_is_insufficient(self) -> None:
        evidence = match_and_context(fixture_client(), {"sender": "", "subject": "", "body_text": "please help"})
        self.assertEqual(evidence["status"], MATCH_INSUFFICIENT)

    def test_fixture_provenance_stays_fixture(self) -> None:
        evidence = match_and_context(
            fixture_client(),
            {"sender": "shelley.fixture.syn@example.com", "subject": "x", "body_text": SHELLEY},
        )
        self.assertEqual(evidence["status"], MATCH_EXISTING)
        self.assertEqual(evidence["source_label"], LABEL_FIXTURE)
        self.assertFalse(evidence["live"])
        self.assertEqual(evidence["location_id"], 66001)
        self.assertEqual(evidence["customer_status"], "active")
        self.assertNotEqual(evidence["source_label"], LABEL_LIVE)
        ops = operational_context(evidence)
        self.assertFalse(ops["live"])
        self.assertEqual(ops["source_label"], LABEL_FIXTURE)

    def test_unknown_status_customer_is_not_active(self) -> None:
        body = (
            "This is Mariah Fixture. Ants at 5 Elm Court, Jacksonville NC 28540. "
            "910-555-7704 mariah.fixture.syn@example.com"
        )
        evidence = match_and_context(
            fixture_client(),
            {"sender": "mariah.fixture.syn@example.com", "subject": "x", "body_text": body},
        )
        self.assertEqual(evidence["status"], MATCH_EXISTING)
        self.assertEqual(evidence["customer_status"], "unknown")
        self.assertNotEqual(evidence["customer_status"], "active")

    def test_multi_property_without_street_abstains(self) -> None:
        body = "This is Shelley Fixture. Please call 910-555-7701. shelley.fixture.syn@example.com"
        evidence = match_and_context(
            fixture_client(),
            {"sender": "shelley.fixture.syn@example.com", "subject": "x", "body_text": body},
        )
        self.assertEqual(evidence["status"], MATCH_AMBIGUOUS)
        self.assertEqual(evidence.get("reason"), "multiple_locations_unresolved")
        self.assertIsNone(evidence.get("location_id"))

    def test_unscoped_work_orders_are_omitted(self) -> None:
        inner = fixture_client()

        def getter(path: str, params: dict):
            if path == "/v3.1/work_orders/search":
                return [{"id": 9, "status": "completed", "customer_id": 1, "completed": True}]
            return inner._lookup(path, params)

        client = ReadOnlyFieldworkClient(token="x", getter=getter, live=False)
        client.identity = {"label": LABEL_FIXTURE, "live": False}
        evidence = match_and_context(
            client,
            {"sender": "shelley.fixture.syn@example.com", "subject": "x", "body_text": SHELLEY},
        )
        self.assertEqual(evidence["status"], MATCH_EXISTING)
        self.assertIn("work_orders", evidence.get("omitted") or {})
        self.assertFalse(evidence.get("upcoming_work_orders"))
        self.assertIsNone(evidence.get("last_service"))

    def test_parse_unknown_object_is_not_empty_success(self) -> None:
        fetched = parse_collection({"foo": 1})
        self.assertFalse(fetched.ok)
        self.assertTrue(fetched.incomplete)
        self.assertEqual(fetched.reason, "schema_mismatch")


class LiveReadRunnerTests(unittest.TestCase):
    def test_grok_bot_client_stays_fixture(self) -> None:
        client = grok_bot_client()
        self.assertFalse(client.live)
        self.assertEqual(client.identity["label"], LABEL_FIXTURE)
        self.assertNotEqual(client.identity["label"], LABEL_LIVE)

    def test_live_read_client_requires_flag(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "BT_FIELDWORK_LIVE_READ"}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(FieldworkReadError) as raised:
                live_read_client()
            self.assertEqual(raised.exception.reason, "live_read_not_enabled")

    def test_live_preflight_without_flag_is_blocked(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "BT_FIELDWORK_LIVE_READ"}
        with mock.patch.dict(os.environ, env, clear=True):
            payload = preflight("live")
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertEqual(payload["reason"], "live_read_not_enabled")

    def test_fixture_preflight_passes(self) -> None:
        payload = preflight("fixture")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["source_label"], LABEL_FIXTURE)
        self.assertFalse(payload["live"])

    def test_direct_read_is_independent_of_matcher(self) -> None:
        client = fixture_client()
        matcher = match_and_context(
            client,
            {"sender": "shelley.fixture.syn@example.com", "subject": "x", "body_text": SHELLEY},
        )
        direct = direct_read_bundle(client, "77001", "66001")
        self.assertTrue(direct["ok"])
        self.assertEqual(direct["customer_id"], "77001")
        self.assertEqual(direct["location_id"], "66001")
        compared = compare_to_direct(matcher, direct)
        self.assertTrue(compared["ok"], compared)
        self.assertNotIn("summary", compared)

    def test_resolve_requires_unique_authorized_name(self) -> None:
        client = fixture_client()
        with tempfile.TemporaryDirectory() as tmp:
            payload = resolve_authorized(
                client,
                labels=AUTHORIZED_LABELS,
                out_path=Path(tmp) / "manifest.json",
            )
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertTrue(all(item["hit_count"] == 0 for item in payload["authorized"]))

    def test_resolve_synthetic_names_and_bounded_read(self) -> None:
        client = fixture_client()
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "manifest.json"
            resolved = resolve_authorized(
                client,
                labels=(
                    {"key": "authorized_case_1", "search_name": "Shelley Fixture"},
                    {"key": "authorized_case_2", "search_name": "Jordan Fixture"},
                    {"key": "authorized_case_3", "search_name": "Mariah Fixture"},
                ),
                out_path=manifest_path,
            )
            self.assertEqual(resolved["status"], "PASS")
            self.assertTrue(all(item["customer_id_present"] for item in resolved["authorized"]))
            self.assertEqual(resolved["authorized"][0]["location_count"], 2)
            manifest = load_manifest(manifest_path)
            self.assertLessEqual(sum(1 for row in manifest["scenarios"] if row["kind"] == "authorized_identity"), 3)
            self.assertLessEqual(
                sum(1 for row in manifest["scenarios"] if str(row.get("kind")).startswith("ambiguity")),
                2,
            )
            scorecard = run_bounded_read(client, manifest, evidence_dir=Path(tmp) / "evidence")
            self.assertEqual(client.write_attempts, 0)
            self.assertFalse(scorecard["drafted"])
            self.assertFalse(scorecard["sent"])
            self.assertFalse(scorecard["live"])
            by_key = {row["key"]: row for row in scorecard["scenarios"]}
            self.assertEqual(by_key["authorized_case_1"]["result"], "PASS")
            self.assertEqual(by_key["authorized_case_2"]["result"], "PASS")
            self.assertEqual(by_key["authorized_case_3"]["result"], "PASS")
            self.assertEqual(by_key["ambiguity_probe_1"]["result"], "PASS")
            self.assertEqual(by_key["synthetic_no_match"]["matcher_status"], MATCH_NONE)
            self.assertEqual(by_key["synthetic_no_match"]["result"], "PASS")
            private = json.loads((Path(tmp) / "evidence" / "authorized_case_1.json").read_text(encoding="utf-8"))
            dumped = json.dumps(private)
            self.assertNotIn("shelley.fixture.syn@example.com", dumped)
            self.assertNotIn("14 Oak Street", dumped)

    def test_example_manifest_fixture_run(self) -> None:
        client = fixture_client()
        manifest = load_manifest(EXAMPLE_MANIFEST)
        with tempfile.TemporaryDirectory() as tmp:
            scorecard = run_bounded_read(client, manifest, evidence_dir=Path(tmp))
        by_key = {row["key"]: row for row in scorecard["scenarios"]}
        self.assertEqual(by_key["authorized_case_1"]["matcher_status"], MATCH_EXISTING)
        self.assertEqual(by_key["ambiguity_probe_1"]["matcher_status"], MATCH_AMBIGUOUS)
        self.assertEqual(by_key["ambiguity_probe_2"]["matcher_status"], MATCH_AMBIGUOUS)
        self.assertEqual(by_key["synthetic_no_match"]["matcher_status"], MATCH_NONE)
        self.assertEqual(scorecard["source_label"], LABEL_FIXTURE)
        self.assertFalse(scorecard["live"])
        self.assertEqual(scorecard["write_attempts"], 0)

    def test_writes_still_forbidden(self) -> None:
        client = fixture_client()
        with self.assertRaises(FieldworkWriteForbidden):
            client.create_customer(name="nope")

    def test_synthetic_catalog_is_not_live_hq(self) -> None:
        blob = json.loads(SYNTHETIC_CATALOG.read_text(encoding="utf-8"))
        self.assertTrue(blob["not_live"])
        self.assertEqual(blob["label"], LABEL_FIXTURE)


class CaseManagerStillFixtureTests(unittest.TestCase):
    def test_case_manager_imports_fixture_client(self) -> None:
        from bt_intake_proof import case_manager

        source = Path(case_manager.__file__).read_text(encoding="utf-8")
        self.assertIn("grok_bot_client()", source)
        self.assertNotIn("live_read_client()", source)


if __name__ == "__main__":
    unittest.main()
