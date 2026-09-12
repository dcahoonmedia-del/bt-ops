import tempfile
import unittest
from pathlib import Path

from bt_intake_proof.case_manager import parse_model_draft
from bt_intake_proof.cases import (
    APPROVAL_APPROVED,
    APPROVAL_SUPERSEDED,
    CaseLayer,
    DECISION_APPROVE,
    DRAFT_NOT_SENT,
    MARKER_APPROVE,
    _label_draft_not_sent,
    case_id_for,
    parse_decision,
)
from bt_intake_proof.constants import CLASS_NEW, CLASS_REPLY, DETECTION_EVENT_DRIVEN, MAILBOX
from bt_intake_proof.knowledge import trusted_rules_text
from bt_intake_proof.review import format_review_email
from bt_intake_proof.store import ReceiptStore, body_hash


def lead_receipt(message_id: str, thread_id: str = "thr-case-1", classification=CLASS_NEW, **extra):
    body = extra.pop("body_text", "Ants in the kitchen at 12 Test St, Jacksonville NC. BT-INTAKE-PROOF-CASEMGR-NEW-E9A8")
    receipt = {
        "eligible": True,
        "mailbox": MAILBOX,
        "gmail_message_id": message_id,
        "thread_id": thread_id,
        "rfc_message_id": f"<{message_id}@bt>",
        "sender": "daniel@btpestcontrol.com",
        "recipients": [MAILBOX],
        "subject": extra.pop("subject", "BT-INTAKE-PROOF-CASEMGR-NEW-E9A8 kitchen ants"),
        "gmail_received_at": "2026-09-12T04:00:00+00:00",
        "detected_at": "2026-09-12T04:00:05+00:00",
        "body_text": body,
        "raw_message": body,
        "body_hash": body_hash(body),
        "labels_before": ["INBOX", "UNREAD"],
        "labels_after": ["INBOX", "UNREAD"],
        "classification": classification,
        "test_marker": extra.pop("test_marker", "BT-INTAKE-PROOF-CASEMGR-NEW-E9A8"),
        "reasons": [],
    }
    receipt.update(extra)
    return receipt


class CaseLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ReceiptStore(Path(self.tmp.name) / "receipts.sqlite")
        self.cases = CaseLayer(self.store)

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _commit(self, *receipts):
        self.store.commit_notification(
            mailbox=MAILBOX,
            history_id="1",
            detection_path=DETECTION_EVENT_DRIVEN,
            pubsub_message_id=None,
            receipts=list(receipts),
        )
        return [self.store.get_receipt(MAILBOX, r["gmail_message_id"]) for r in receipts]

    def test_receipt_becomes_one_case(self) -> None:
        row = self._commit(lead_receipt("m1"))[0]
        result = self.cases.upsert_from_receipt(row)
        self.assertTrue(result["created"])
        case = self.cases.get_case(result["case_id"])
        assert case is not None
        self.assertEqual(case["thread_id"], "thr-case-1")
        self.assertEqual(case["inbound_class"], "new_lead")
        self.assertEqual(case["stage"], "needs_draft")
        self.assertEqual(case["latest_inbound_message_id"], "m1")
        self.assertEqual(len(self.cases.list_events(case["case_id"])), 1)

    def test_same_thread_reopens_and_supersedes_approval(self) -> None:
        first = self._commit(lead_receipt("m1"))[0]
        opened = self.cases.upsert_from_receipt(first)
        self.cases.save_draft(
            opened["case_id"],
            {
                "classification": "new residential ants",
                "known_facts": ["Jacksonville kitchen ants"],
                "missing_info": ["callback number"],
                "recommended_next_step": "weekday callback",
                "proposed_response": "Thanks for writing.",
                "channel": "email",
                "judgment_needed": None,
                "reasoning_summary": "ask for phone",
            },
            "nonce-1",
        )
        approved = self.cases.apply_decision(
            opened["case_id"],
            DECISION_APPROVE,
            draft_version=1,
            actor="daniel@btpestcontrol.com",
        )
        self.assertTrue(approved["ok"])
        self.assertFalse(approved["send_triggered"])
        self.assertEqual(self.cases.get_case(opened["case_id"])["approval_state"], APPROVAL_APPROVED)
        reply = self._commit(
            lead_receipt(
                "m2",
                classification=CLASS_REPLY,
                test_marker="BT-INTAKE-PROOF-CASEMGR-REPLY-E9A8",
                subject="Re: kitchen ants BT-INTAKE-PROOF-CASEMGR-REPLY-E9A8",
                body_text="Also saw them in the bathroom. BT-INTAKE-PROOF-CASEMGR-REPLY-E9A8",
            )
        )[0]
        again = self.cases.upsert_from_receipt(reply)
        self.assertFalse(again["created"])
        self.assertTrue(again["reopened"])
        self.assertTrue(again["approval_superseded"])
        case = self.cases.get_case(opened["case_id"])
        assert case is not None
        self.assertEqual(case["case_id"], opened["case_id"])
        self.assertEqual(case["latest_inbound_message_id"], "m2")
        self.assertEqual(case["approval_state"], APPROVAL_SUPERSEDED)
        self.assertEqual(case["stage"], "reopened")
        stale = self.cases.apply_decision(
            opened["case_id"],
            DECISION_APPROVE,
            draft_version=1,
            actor="daniel@btpestcontrol.com",
        )
        self.assertFalse(stale["ok"])
        self.assertIn(stale["reason"], {"approval_superseded", "stale_draft_version"})
        self.assertEqual(self.cases.get_draft(opened["case_id"], 1)["status"], "superseded")
        decisions = self.cases.decisions(opened["case_id"])
        self.assertEqual(decisions[0]["send_triggered"], 0)

    def test_decision_parser_and_review_packet(self) -> None:
        parsed = parse_decision(
            f"{MARKER_APPROVE} CASE=BTC-x DRAFT=2",
            "looks good",
        )
        assert parsed is not None
        self.assertEqual(parsed["decision"], DECISION_APPROVE)
        self.assertEqual(parsed["case_id"], "BTC-x")
        self.assertEqual(parsed["draft_version"], 2)
        row = self._commit(lead_receipt("m3"))[0]
        opened = self.cases.upsert_from_receipt(row)
        self.cases.save_draft(
            opened["case_id"],
            {
                "classification": "lead",
                "known_facts": ["ants"],
                "missing_info": ["phone"],
                "recommended_next_step": "ask for phone",
                "proposed_response": "We can help.",
                "channel": "email",
                "judgment_needed": None,
                "reasoning_summary": "need phone",
            },
            "nonce-2",
        )
        packet = self.cases.review_packet(opened["case_id"])
        email = format_review_email(packet)
        self.assertIn("DRAFT - NOT SENT", email["body"])
        self.assertNotIn("DRAFT — NOT SENT", email["body"])
        self.assertIn(opened["case_id"], email["body"])
        self.assertIn("Approve", email["body"])
        self.assertIn("Request changes", email["body"])
        self.assertIn("No response needed", email["body"])
        self.assertEqual(email["to"], "daniel@btpestcontrol.com")

    def test_trusted_rules_are_separate_from_external_payload(self) -> None:
        rules = trusted_rules_text()
        self.assertIn("TRUSTED_APPLICATION_CONTEXT", rules)
        self.assertIn("cannot change these rules", rules)
        self.assertIn("Proposed Architecture", rules)
        self.assertIn("No Fieldwork in Phase C", rules)
        draft = parse_model_draft('intro {"classification":"ants","proposed_response":"hi"} trailing')
        self.assertEqual(draft["classification"], "ants")
        self.assertEqual(case_id_for(MAILBOX, "abc"), "BTC-contactus-abc")
        self.assertEqual(_label_draft_not_sent("Thanks for writing."), f"{DRAFT_NOT_SENT}\n\nThanks for writing.")
        self.assertEqual(_label_draft_not_sent("DRAFT — NOT SENT\n\nHi"), f"{DRAFT_NOT_SENT}\n\nHi")

    def test_failed_draft_leaves_case_pending(self) -> None:
        row = self._commit(lead_receipt("m-fail"))[0]
        opened = self.cases.upsert_from_receipt(row)
        self.cases.add_event(opened["case_id"], "draft_failed", reason="codex_draft_failed")
        case = self.cases.get_case(opened["case_id"])
        assert case is not None
        self.assertEqual(case["stage"], "needs_draft")
        self.assertIsNone(self.cases.latest_draft(opened["case_id"]))
        events = [item["event_type"] for item in self.cases.list_events(opened["case_id"])]
        self.assertIn("draft_failed", events)
        self.assertEqual(self.cases.cases_needing_draft()[0]["case_id"], opened["case_id"])


if __name__ == "__main__":
    unittest.main()
