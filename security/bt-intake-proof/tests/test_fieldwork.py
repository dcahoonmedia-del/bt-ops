import tempfile
import unittest
from pathlib import Path

from bt_intake_proof.case_manager import build_case_payload
from bt_intake_proof.cases import CaseLayer
from bt_intake_proof.constants import CLASS_NEW, DETECTION_EVENT_DRIVEN, MAILBOX
from bt_intake_proof.fieldwork_booking import LABEL_FIXTURE, LABEL_LIVE, draft_booking_guidance
from bt_intake_proof.fieldwork_fixture import GrokBotFieldwork
from bt_intake_proof.fieldwork_match import MATCH_AMBIGUOUS, MATCH_EXISTING, MATCH_NONE, extract_identifiers, match_and_context
from bt_intake_proof.fieldwork_readonly import FieldworkWriteForbidden, ReadOnlyFieldworkClient
from bt_intake_proof.review import format_review_email
from bt_intake_proof.store import ReceiptStore, body_hash

MATT_MULTI = (
    "Hi, this is Matt Audit. Ants at 14 Fixture Lane, Holly Ridge NC 28445. "
    "910-555-0001 matt.phased.001@example.com"
)
ONE_ID = "Please call me back. 910-555-0099. BT-INTAKE-PROOF-CASEMGR-FWD-ONEID-E9A8"


def _receipt(message_id: str, body: str, marker: str) -> dict:
    return {
        "eligible": True,
        "mailbox": MAILBOX,
        "gmail_message_id": message_id,
        "thread_id": message_id,
        "rfc_message_id": f"<{message_id}@bt>",
        "sender": "daniel@btpestcontrol.com",
        "recipients": [MAILBOX],
        "subject": marker,
        "gmail_received_at": "2026-09-12T05:00:00+00:00",
        "detected_at": "2026-09-12T05:00:05+00:00",
        "body_text": body,
        "raw_message": body,
        "body_hash": body_hash(body),
        "labels_before": ["INBOX", "UNREAD"],
        "labels_after": ["INBOX", "UNREAD"],
        "classification": CLASS_NEW,
        "test_marker": marker,
        "reasons": [],
    }


class FieldworkReadOnlyTests(unittest.TestCase):
    def test_write_methods_are_forbidden(self) -> None:
        client = GrokBotFieldwork()
        with self.assertRaises(FieldworkWriteForbidden):
            client.create_customer(name="nope")
        with self.assertRaises(FieldworkWriteForbidden):
            client.update_customer(99001, name="nope")
        with self.assertRaises(FieldworkWriteForbidden):
            client.create_work_order()
        with self.assertRaises(FieldworkWriteForbidden):
            ReadOnlyFieldworkClient(token="x")._request("POST", "/v3.1/customers")
        self.assertGreaterEqual(client.write_attempts, 3)

    def test_payload_is_fixture_not_live(self) -> None:
        receipt = _receipt("m1", MATT_MULTI, "BT-INTAKE-PROOF-CASEMGR-FWD-MATT-E9A8")
        fw = match_and_context(GrokBotFieldwork(snapshot="pre_booking"), receipt)
        payload = build_case_payload({"case_id": "BTC-x"}, receipt, "nonce-fw", fw)
        self.assertEqual(payload["trusted_fieldwork"]["label"], LABEL_FIXTURE)
        self.assertFalse(payload["trusted_fieldwork"]["live"])
        self.assertNotEqual(payload["trusted_fieldwork"]["label"], LABEL_LIVE)
        self.assertNotIn("trusted_fieldwork", payload["constructor"]["content"])


class PhaseDMattFixtureTests(unittest.TestCase):
    def test_multi_identifier_match_and_near_checks(self) -> None:
        receipt = _receipt("matt1", MATT_MULTI, "BT-INTAKE-PROOF-CASEMGR-FWD-MATT-E9A8")
        ids = extract_identifiers(receipt)
        self.assertTrue(ids["emails"])
        self.assertTrue(ids["phones"])
        self.assertTrue(ids["names"])
        self.assertTrue(ids["addresses"])
        evidence = match_and_context(GrokBotFieldwork(snapshot="pre_booking"), receipt)
        self.assertEqual(evidence["status"], MATCH_EXISTING)
        self.assertEqual(evidence["fixture_id"], "PHASE-D-MATT-001")
        self.assertGreaterEqual(len(evidence.get("match_hits") or []), 2)
        kinds = {item["kind"] for item in evidence.get("near_matches_investigated") or []}
        self.assertIn("nearby_address", kinds)
        self.assertIn("surname", kinds)
        self.assertEqual(evidence["source_label"], LABEL_FIXTURE)
        self.assertNotEqual(evidence["source_label"], LABEL_LIVE)
        self.assertFalse(evidence["live"])

    def test_identity_is_not_booking_state(self) -> None:
        receipt = _receipt("matt2", MATT_MULTI, "BT-INTAKE-PROOF-CASEMGR-FWD-MATT-E9A8")
        evidence = match_and_context(GrokBotFieldwork(snapshot="pre_booking"), receipt)
        self.assertEqual(evidence["identity_kind"], "pipeline_lead")
        self.assertEqual((evidence.get("pipeline") or {}).get("lead_id"), 9949)
        self.assertEqual((evidence.get("pipeline") or {}).get("opportunity_id"), 92205)
        self.assertEqual((evidence.get("pipeline") or {}).get("stage"), "Contacted")
        self.assertEqual((evidence.get("pipeline") or {}).get("setup_checklist"), "verified")
        self.assertEqual(evidence["booking_state"], "no_work_order")
        self.assertFalse(evidence.get("upcoming_work_orders"))

    def test_no_wo_versus_verified_wo(self) -> None:
        receipt = _receipt("matt3", MATT_MULTI, "BT-INTAKE-PROOF-CASEMGR-FWD-MATT-E9A8")
        pre = match_and_context(GrokBotFieldwork(snapshot="pre_booking"), receipt)
        post = match_and_context(GrokBotFieldwork(snapshot="post_booking"), receipt)
        self.assertEqual(pre["booking_state"], "no_work_order")
        self.assertEqual(post["booking_state"], "scheduled")
        self.assertEqual(post["upcoming_work_orders"][0]["id"], 172708)
        self.assertEqual(post["upcoming_work_orders"][0]["technician"], "Josh")
        self.assertEqual(post["upcoming_work_orders"][0]["amount"], 325)
        self.assertTrue(post["upcoming_work_orders"][0]["scheduled"])
        self.assertFalse(post["upcoming_work_orders"][0]["completed"])
        self.assertFalse(post["upcoming_work_orders"][0]["sold"])

    def test_draft_before_booking_verification(self) -> None:
        receipt = _receipt("matt4", MATT_MULTI, "BT-INTAKE-PROOF-CASEMGR-FWD-MATT-E9A8")
        pending = match_and_context(GrokBotFieldwork(snapshot="pending_write"), receipt)
        self.assertEqual(pending["booking_state"], "pending_write_not_verified")
        self.assertTrue(pending["customer_email_reported_sent"])
        guide = draft_booking_guidance(pending)
        self.assertFalse(guide["may_confirm_booking"])
        self.assertFalse(guide["may_cite_work_order"])
        self.assertTrue(guide["do_not_infer_customer_confirmation"])
        self.assertFalse(guide["treat_pending_write_as_verified"])
        self.assertEqual(guide["source_label"], LABEL_FIXTURE)

    def test_draft_after_booking_verification(self) -> None:
        receipt = _receipt("matt5", MATT_MULTI, "BT-INTAKE-PROOF-CASEMGR-FWD-MATT-E9A8")
        post = match_and_context(GrokBotFieldwork(snapshot="post_booking"), receipt)
        guide = draft_booking_guidance(post)
        self.assertTrue(guide["may_confirm_booking"])
        self.assertTrue(guide["may_cite_work_order"])
        self.assertTrue(guide["scheduled"])
        self.assertFalse(guide["sold"])
        self.assertFalse(guide["completed"])
        self.assertEqual(guide["verified_work_order"]["id"], 172708)

    def test_sold_scheduled_completed_stay_separate(self) -> None:
        receipt = _receipt("matt6", MATT_MULTI, "BT-INTAKE-PROOF-CASEMGR-FWD-MATT-E9A8")
        post = match_and_context(GrokBotFieldwork(snapshot="post_booking"), receipt)
        wo = post["upcoming_work_orders"][0]
        self.assertNotEqual(wo["sold"], wo["scheduled"])
        self.assertNotEqual(wo["scheduled"], wo["completed"])
        guide = draft_booking_guidance(post)
        self.assertIn("collapse sold/scheduled/completed", " ".join(guide["draft_must_not"]))

    def test_one_identifier_is_ambiguous(self) -> None:
        receipt = _receipt("one", ONE_ID, "BT-INTAKE-PROOF-CASEMGR-FWD-ONEID-E9A8")
        ids = extract_identifiers(receipt)
        self.assertTrue(ids["phones"])
        self.assertFalse(ids["emails"])
        self.assertFalse(ids["names"])
        evidence = match_and_context(GrokBotFieldwork(), receipt)
        self.assertEqual(evidence["status"], MATCH_AMBIGUOUS)
        self.assertEqual(evidence.get("reason"), "single_identifier_is_not_enough")
        self.assertIsNone(evidence.get("customer_id"))

    def test_no_match_does_not_create(self) -> None:
        receipt = _receipt(
            "none",
            "This is Nobody Fake at 999 Missing Ave, Nowhere NC 00000. 910-555-0000 nobody.fake.fwd@example.org",
            "BT-INTAKE-PROOF-CASEMGR-FWD-ONEID-E9A8",
        )
        client = GrokBotFieldwork()
        evidence = match_and_context(client, receipt)
        self.assertEqual(evidence["status"], MATCH_NONE)
        self.assertEqual(client.write_attempts, 0)


class FieldworkCasePersistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ReceiptStore(Path(self.tmp.name) / "receipts.sqlite")
        self.cases = CaseLayer(self.store)

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_review_uses_fixture_label(self) -> None:
        receipt = _receipt("p1", MATT_MULTI, "BT-INTAKE-PROOF-CASEMGR-FWD-MATT-E9A8")
        self.store.commit_notification(
            mailbox=MAILBOX,
            history_id="1",
            detection_path=DETECTION_EVENT_DRIVEN,
            pubsub_message_id=None,
            receipts=[receipt],
        )
        row = self.store.get_receipt(MAILBOX, "p1")
        opened = self.cases.upsert_from_receipt(row)
        evidence = match_and_context(GrokBotFieldwork(snapshot="pre_booking"), row)
        saved = self.cases.save_fieldwork(opened["case_id"], evidence, "p1")
        self.assertFalse(saved["write_attempted"])
        self.cases.save_draft(
            opened["case_id"],
            {
                "classification": "pipeline lead, no verified WO",
                "known_facts": ["FIELDWORK_FIXTURE_VERIFIED Pipeline Lead 9949 Contacted"],
                "missing_info": [],
                "recommended_next_step": "do not confirm booking",
                "proposed_response": "Thanks. I have your request and will confirm any appointment only after it is on the board.",
                "channel": "email",
                "judgment_needed": None,
                "reasoning_summary": "identity is not booking",
            },
            "nonce-fw",
        )
        email = format_review_email(self.cases.review_packet(opened["case_id"]))
        self.assertIn(LABEL_FIXTURE, email["body"])
        self.assertNotIn(LABEL_LIVE, email["body"])
        self.assertIn("Write attempted: 0", email["body"])


if __name__ == "__main__":
    unittest.main()
