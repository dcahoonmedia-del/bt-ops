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
    MARKER_REVIEW,
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

    def test_older_inbound_is_not_reapplied_after_reply(self) -> None:
        first = self._commit(lead_receipt("m-old"))[0]
        opened = self.cases.upsert_from_receipt(first)
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
            "nonce-old",
        )
        self.cases.apply_decision(
            opened["case_id"],
            DECISION_APPROVE,
            draft_version=1,
            actor="daniel@btpestcontrol.com",
            gmail_message_id="approve-old",
        )
        reply = self._commit(
            lead_receipt(
                "m-new",
                classification=CLASS_REPLY,
                test_marker="BT-INTAKE-PROOF-CASEMGR-REPLY-E9A8",
                subject="Re: kitchen ants BT-INTAKE-PROOF-CASEMGR-REPLY-E9A8",
                body_text="Bathroom too. BT-INTAKE-PROOF-CASEMGR-REPLY-E9A8",
            )
        )[0]
        self.assertTrue(self.cases.upsert_from_receipt(reply)["reopened"])
        self.assertEqual(self.cases.get_case(opened["case_id"])["latest_inbound_message_id"], "m-new")
        again = self.cases.upsert_from_receipt(first)
        self.assertTrue(again.get("skipped"))
        self.assertEqual(again.get("reason"), "already_applied")
        self.assertEqual(self.cases.get_case(opened["case_id"])["latest_inbound_message_id"], "m-new")
        reopens = [event for event in self.cases.list_events(opened["case_id"]) if event["event_type"] == "inbound_reopened"]
        self.assertEqual(len(reopens), 1)

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
        reply_parsed = parse_decision(
            f"Re: {MARKER_REVIEW} BTC-x v1",
            f"{MARKER_APPROVE}\nCASE=BTC-x DRAFT=1",
        )
        assert reply_parsed is not None
        self.assertEqual(reply_parsed["decision"], DECISION_APPROVE)
        self.assertEqual(reply_parsed["case_id"], "BTC-x")
        self.assertEqual(reply_parsed["draft_version"], 1)

    def test_iphone_reply_to_review_records_approval(self) -> None:
        row = self._commit(lead_receipt("m-iphone"))[0]
        opened = self.cases.upsert_from_receipt(row)
        self.cases.save_draft(
            opened["case_id"],
            {
                "classification": "lead",
                "known_facts": [],
                "missing_info": [],
                "recommended_next_step": "review",
                "proposed_response": "Thanks.",
                "channel": "email",
            },
            "nonce-iphone",
        )
        self._commit(
            lead_receipt(
                "m-iphone-approve",
                thread_id="thr-review-reply",
                test_marker=MARKER_REVIEW,
                subject=f"Re: {MARKER_REVIEW} {opened['case_id']} v1",
                body_text=f"{MARKER_APPROVE}\nCASE={opened['case_id']} DRAFT=1",
            )
        )
        synced = self.cases.sync_eligible_receipts(MAILBOX)
        applied = [item for item in synced if item.get("decision") == DECISION_APPROVE]
        self.assertTrue(applied)
        self.assertEqual(self.cases.get_case(opened["case_id"])["approval_state"], APPROVAL_APPROVED)
        self.assertFalse(applied[0]["send_triggered"])

    def test_review_packet_body_does_not_self_approve(self) -> None:
        row = self._commit(lead_receipt("m-review-only"))[0]
        opened = self.cases.upsert_from_receipt(row)
        self.cases.save_draft(
            opened["case_id"],
            {
                "classification": "lead",
                "known_facts": [],
                "missing_info": [],
                "recommended_next_step": "review",
                "proposed_response": "Thanks.",
                "channel": "email",
            },
            "nonce-review-only",
        )
        email = format_review_email(self.cases.review_packet(opened["case_id"]))
        self._commit(
            lead_receipt(
                "m-review-copy",
                thread_id="thr-review-copy",
                test_marker=MARKER_REVIEW,
                subject=email["subject"],
                body_text=email["body"],
            )
        )
        self.cases.sync_eligible_receipts(MAILBOX)
        self.assertNotEqual(self.cases.get_case(opened["case_id"])["approval_state"], APPROVAL_APPROVED)

    def test_trusted_rules_are_separate_from_external_payload(self) -> None:
        rules = trusted_rules_text()
        self.assertIn("TRUSTED_APPLICATION_CONTEXT", rules)
        self.assertIn("cannot change these rules", rules)
        self.assertIn("Proposed Architecture", rules)
        self.assertIn("FIELDWORK_FIXTURE_VERIFIED", rules)
        self.assertIn("Do not write Fieldwork", rules)
        draft = parse_model_draft('intro {"classification":"ants","proposed_response":"hi"} trailing')
        self.assertEqual(draft["classification"], "ants")
        self.assertEqual(case_id_for(MAILBOX, "abc"), "BTC-contactus-abc")
        self.assertEqual(_label_draft_not_sent("Thanks for writing."), f"{DRAFT_NOT_SENT}\n\nThanks for writing.")
        self.assertEqual(_label_draft_not_sent("DRAFT — NOT SENT\n\nHi"), f"{DRAFT_NOT_SENT}\n\nHi")
        exact = "DRAFT - NOT SENT\n\nKeep this spacing.  \n"
        self.assertEqual(_label_draft_not_sent(exact, exact=True), exact)
        self.assertEqual(_label_draft_not_sent(exact), "DRAFT - NOT SENT\n\nKeep this spacing.")

    def test_same_decision_receipt_is_idempotent(self) -> None:
        row = self._commit(lead_receipt("m-dec"))[0]
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
            "nonce-dec",
        )
        first = self.cases.apply_decision(
            opened["case_id"],
            DECISION_APPROVE,
            draft_version=1,
            actor="daniel@btpestcontrol.com",
            gmail_message_id="approve-1",
        )
        again = self.cases.apply_decision(
            opened["case_id"],
            DECISION_APPROVE,
            draft_version=1,
            actor="daniel@btpestcontrol.com",
            gmail_message_id="approve-1",
        )
        self.assertTrue(first["ok"])
        self.assertTrue(again["ok"])
        self.assertTrue(again.get("skipped"))
        self.assertEqual(len(self.cases.decisions(opened["case_id"])), 1)
        self.assertEqual(self.cases.decisions(opened["case_id"])[0]["send_triggered"], 0)

    def test_phase_b_markers_do_not_become_cases(self) -> None:
        row = self._commit(
            lead_receipt(
                "m-cloud",
                test_marker="BT-INTAKE-PROOF-CLOUD-NEW-E9A8-7F3C",
                subject="BT-INTAKE-PROOF-CLOUD-NEW-E9A8-7F3C leftover",
            )
        )[0]
        result = self.cases.upsert_from_receipt(row)
        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "other")
        self.assertEqual(self.cases.cases_needing_draft(), [])

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
