import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bt_intake_proof.constants import CLASS_INELIGIBLE, CLASS_REPLY, CODEX_NAMESPACE, MAILBOX
from bt_intake_proof.eligibility import evaluate_message
from bt_intake_proof.intake_mode import (
    IntakeModeError,
    describe_mode,
    live_receiver_mode,
    require_isolated_live_receiver,
)
from bt_intake_proof.production_intake import (
    DISPOSITIONS,
    SCOPE_CASE,
    SCOPE_COMPANY,
    STATUS_FAILED_VISIBLE,
    RoutingLedger,
    capture_gate,
    captured_event,
    classify_after_capture,
)
from bt_intake_proof.receiver import hydrate_receipt
from bt_intake_proof.store import ReceiptStore


class IsolatedHarnessStillOnTests(unittest.TestCase):
    def test_live_mode_stays_isolated(self) -> None:
        self.assertEqual(live_receiver_mode(), "isolated_test")
        self.assertEqual(require_isolated_live_receiver(), "isolated_test")
        info = describe_mode()
        self.assertFalse(info["real_customer_processing"])
        self.assertEqual(info["subject_marker_filters"], "enabled_for_isolated_testing_only")

    def test_env_cannot_broaden_live_receiver(self) -> None:
        with patch.dict(os.environ, {"BT_INTAKE_MODE": "shadow_all"}):
            with self.assertRaises(IntakeModeError):
                require_isolated_live_receiver()

    def test_harness_still_rejects_unmarked_customer_mail(self) -> None:
        result = evaluate_message(
            mailbox=MAILBOX,
            sender="customer@example.com",
            recipients=MAILBOX,
            subject="Do you treat ants?",
            body="Please come tomorrow",
            gmail_message_id="cust-1",
        )
        self.assertFalse(result["eligible"])
        self.assertEqual(result["classification"], CLASS_INELIGIBLE)
        self.assertIn("missing_bt_intake_proof_marker", result["reasons"])

    def test_hydrate_uses_harness_and_strips_customer_body(self) -> None:
        message = {
            "id": "cust-live",
            "threadId": "thr-cust",
            "labelIds": ["INBOX", "UNREAD"],
            "raw": None,
        }
        receipt = hydrate_receipt(MAILBOX, message, ["cust-live"], "event_driven")
        self.assertFalse(receipt["eligible"])
        self.assertIsNone(receipt["body_text"])
        self.assertIsNone(receipt["subject"])


class ProductionCaptureTests(unittest.TestCase):
    def test_subject_never_decides_capture(self) -> None:
        with_marker = capture_gate(
            mailbox=MAILBOX,
            gmail_message_id="m1",
            sender="anyone@example.com",
            subject="BT-INTAKE-PROOF-NEW-E9A8-7F3C",
        )
        without = capture_gate(
            mailbox=MAILBOX,
            gmail_message_id="m2",
            sender="anyone@example.com",
            subject="ants in the kitchen",
        )
        self.assertTrue(with_marker["capture"])
        self.assertTrue(without["capture"])
        self.assertFalse(without["subject_used_for_capture"])
        self.assertFalse(without["sender_used_for_capture"])

    def test_every_contactus_inbound_is_captured(self) -> None:
        samples = [
            {"sender": "new@example.com", "subject": "price?", "office_owned": False, "known_existing_customer": False},
            {"sender": "oldcust@example.com", "subject": "service issue", "office_owned": False, "known_existing_customer": True},
            {"sender": "brenda@btpestcontrol.com", "subject": "hold this", "office_owned": True, "known_existing_customer": False},
            {"sender": "vendor@example.com", "subject": "invoice", "office_owned": False, "known_existing_customer": False},
            {"sender": "noreply@google.com", "subject": "watch notice", "office_owned": False, "known_existing_customer": False},
        ]
        for index, item in enumerate(samples):
            result = captured_event(
                mailbox=MAILBOX,
                gmail_message_id=f"cap-{index}",
                thread_id=f"thr-{index}",
                sender=item["sender"],
                recipients=[MAILBOX],
                subject=item["subject"],
                body="customer or sender text",
                office_owned=item["office_owned"],
                known_existing_customer=item["known_existing_customer"],
            )
            self.assertTrue(result["capture"], item)
            self.assertTrue(result["event"]["visible"])
            self.assertFalse(result["event"]["suppressed"])
            self.assertEqual(result["event"]["content"]["namespace"], CODEX_NAMESPACE)
            self.assertEqual(result["event"]["disposition_status"], "pending")

    def test_old_thread_reply_is_a_new_event(self) -> None:
        first = captured_event(
            mailbox=MAILBOX,
            gmail_message_id="old",
            thread_id="thr-old",
            sender="customer@example.com",
            recipients=MAILBOX,
            subject="first",
            body="first",
            thread_message_ids_oldest_first=["old"],
        )
        later = captured_event(
            mailbox=MAILBOX,
            gmail_message_id="new",
            thread_id="thr-old",
            sender="customer@example.com",
            recipients=MAILBOX,
            subject="Re: first",
            body="new reply years later",
            thread_message_ids_oldest_first=["old", "new"],
        )
        self.assertNotEqual(first["event"]["event_id"], later["event"]["event_id"])
        self.assertEqual(later["event"]["thread_role"], CLASS_REPLY)
        self.assertTrue(later["pending"])

    def test_existing_customer_and_office_owned_stay_visible(self) -> None:
        existing = captured_event(
            mailbox=MAILBOX,
            gmail_message_id="ex1",
            thread_id="t",
            sender="matt@example.com",
            recipients=MAILBOX,
            subject="callback",
            body="please call",
            known_existing_customer=True,
        )
        classified = classify_after_capture(existing["event"])
        self.assertEqual(classified["disposition"], "existing_customer_other")
        self.assertTrue(classified["visible"])
        self.assertFalse(classified["suppressed"])
        office = classify_after_capture(
            captured_event(
                mailbox=MAILBOX,
                gmail_message_id="off1",
                thread_id="t2",
                sender="ally@btpestcontrol.com",
                recipients=MAILBOX,
                subject="office hold",
                body="we own this",
                office_owned=True,
            )["event"]
        )
        self.assertEqual(office["disposition"], "office_owned")
        self.assertTrue(office["visible"])

    def test_classification_failure_stays_pending_and_is_not_dropped(self) -> None:
        event = captured_event(
            mailbox=MAILBOX,
            gmail_message_id="unk1",
            thread_id="t",
            sender="mystery@example.com",
            recipients=MAILBOX,
            subject="???",
            body="unreadable",
        )["event"]
        failed = classify_after_capture(event, fail=True)
        self.assertEqual(failed["disposition"], "uncertain_needs_daniel")
        self.assertEqual(failed["disposition_status"], STATUS_FAILED_VISIBLE)
        self.assertTrue(failed["pending"])
        self.assertTrue(failed["visible"])
        self.assertFalse(failed["dropped"])
        self.assertFalse(failed["suppressed"])

    def test_initial_dispositions_are_named(self) -> None:
        self.assertEqual(
            DISPOSITIONS,
            (
                "new_customer_lead",
                "existing_customer_service_issue",
                "existing_customer_other",
                "office_owned",
                "vendor_or_internal",
                "automated_system_notice",
                "spam_or_noncustomer",
                "uncertain_needs_daniel",
            ),
        )
        for name in DISPOSITIONS:
            event = captured_event(
                mailbox=MAILBOX,
                gmail_message_id=name,
                thread_id="t",
                sender="a@b.c",
                recipients=MAILBOX,
                subject="x",
                body="y",
            )["event"]
            classified = classify_after_capture(event, suggested=name)
            self.assertEqual(classified["disposition"], name)


class RoutingLearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = sqlite3.connect(Path(self.tmp.name) / "routing.sqlite")
        self.conn.row_factory = sqlite3.Row
        self.ledger = RoutingLedger(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_case_decision_does_not_become_a_global_rule(self) -> None:
        recorded = self.ledger.record_case_decision(
            case_id="BTC-1",
            gmail_message_id="m1",
            disposition="vendor_or_internal",
            actor="daniel@btpestcontrol.com",
            note="this one vendor thread only",
        )
        self.assertEqual(recorded["scope"], SCOPE_CASE)
        self.assertFalse(recorded["promoted"])
        self.assertEqual(self.ledger.company_rules(), [])
        event = captured_event(
            mailbox=MAILBOX,
            gmail_message_id="m2",
            thread_id="other",
            sender="vendor@example.com",
            recipients=MAILBOX,
            subject="another invoice",
            body="pay this",
        )["event"]
        classified = classify_after_capture(event, company_rules=self.ledger.company_rules())
        self.assertNotEqual(classified["disposition"], "vendor_or_internal")
        self.assertEqual(classified["disposition"], "uncertain_needs_daniel")

    def test_explicit_promote_versions_and_override(self) -> None:
        self.ledger.record_case_decision(
            case_id="BTC-1",
            gmail_message_id="m1",
            disposition="automated_system_notice",
            actor="daniel@btpestcontrol.com",
        )
        with self.assertRaises(ValueError):
            self.ledger.promote_to_company_rule(
                decision_id=1,
                actor="daniel@btpestcontrol.com",
                match_sender="alerts@example.com",
                explicit=False,
                provenance={"why": "should fail"},
            )
        promoted = self.ledger.promote_to_company_rule(
            decision_id=1,
            actor="daniel@btpestcontrol.com",
            match_sender="alerts@example.com",
            explicit=True,
            provenance={"why": "all alerts@ mail is automated"},
        )
        self.assertEqual(promoted["scope"], SCOPE_COMPANY)
        self.assertEqual(promoted["version"], 1)
        event = captured_event(
            mailbox=MAILBOX,
            gmail_message_id="m9",
            thread_id="t",
            sender="alerts@example.com",
            recipients=MAILBOX,
            subject="bounce",
            body="auto",
        )["event"]
        classified = classify_after_capture(event, company_rules=self.ledger.company_rules())
        self.assertEqual(classified["disposition"], "automated_system_notice")
        overridden = self.ledger.override(
            case_id="BTC-9",
            gmail_message_id="m9",
            disposition="uncertain_needs_daniel",
            actor="daniel@btpestcontrol.com",
        )
        self.assertTrue(overridden["overridden"])
        hist = self.ledger.history()
        self.assertGreaterEqual(len(hist["decisions"]), 2)
        self.assertEqual(hist["rules"][0]["version"], 1)
        self.assertIn("decision_id", hist["rules"][0]["provenance_json"])


class IsolatedStoreStillStripsCustomerTests(unittest.TestCase):
    def test_live_store_path_still_omits_customer_bodies(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        store = ReceiptStore(Path(tmp.name) / "receipts.sqlite")
        store.commit_notification(
            mailbox=MAILBOX,
            history_id="1",
            detection_path="event_driven",
            pubsub_message_id="p",
            receipts=[
                {
                    "eligible": False,
                    "gmail_message_id": "cust-keep-out",
                    "thread_id": "thr",
                    "sender": "customer@example.com",
                    "classification": "ineligible",
                    "reasons": ["missing_bt_intake_proof_marker"],
                    "body_text": "real customer body",
                    "subject": "ants",
                }
            ],
        )
        row = store.get_receipt(MAILBOX, "cust-keep-out")
        assert row is not None
        self.assertIsNone(row["body_text"])
        self.assertIsNone(row["subject"])
        store.close()
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
