import unittest

from bt_intake_proof.constants import CLASS_NEW, CLASS_REPLY, MAILBOX
from bt_intake_proof.eligibility import classify_thread_role, evaluate_message, extract_marker


class EligibilityTests(unittest.TestCase):
    def test_marker_extraction(self) -> None:
        self.assertEqual(
            extract_marker("Re: hello BT-INTAKE-PROOF-NEW-E9A8-7F3C inside"),
            "BT-INTAKE-PROOF-NEW-E9A8-7F3C",
        )
        self.assertIsNone(extract_marker("ordinary customer quote request"))

    def test_internal_marked_message_is_eligible(self) -> None:
        result = evaluate_message(
            mailbox=MAILBOX,
            sender="Daniel Cahoon <daniel@btpestcontrol.com>",
            recipients="Contact Us <contactus@btpestcontrol.com>",
            subject="BT-INTAKE-PROOF-NEW-E9A8-7F3C",
            body="Internal B&T intake proof only.",
            gmail_message_id="msg-new",
            thread_message_ids_oldest_first=["msg-new"],
        )
        self.assertTrue(result["eligible"])
        self.assertEqual(result["classification"], CLASS_NEW)
        self.assertEqual(result["marker"], "BT-INTAKE-PROOF-NEW-E9A8-7F3C")

    def test_customer_mail_is_rejected(self) -> None:
        result = evaluate_message(
            mailbox=MAILBOX,
            sender="customer@example.com",
            recipients=MAILBOX,
            subject="Do you treat ants?",
            body="Please come tomorrow",
            gmail_message_id="cust-1",
        )
        self.assertFalse(result["eligible"])
        self.assertIn("sender_not_authorized_internal", result["reasons"])
        self.assertIn("missing_bt_intake_proof_marker", result["reasons"])

    def test_wrong_mailbox_is_rejected(self) -> None:
        result = evaluate_message(
            mailbox="daniel@btpestcontrol.com",
            sender="daniel@btpestcontrol.com",
            recipients=MAILBOX,
            subject="BT-INTAKE-PROOF-NEW-E9A8-7F3C",
            body="x",
            gmail_message_id="msg-2",
        )
        self.assertFalse(result["eligible"])
        self.assertIn("mailbox_not_contactus", result["reasons"])

    def test_old_thread_reply_classification(self) -> None:
        self.assertEqual(classify_thread_role("new", ["old", "new"]), CLASS_REPLY)
        self.assertEqual(classify_thread_role("only", ["only"]), CLASS_NEW)
        result = evaluate_message(
            mailbox=MAILBOX,
            sender="daniel@btpestcontrol.com",
            recipients=[MAILBOX],
            subject="Re: BT-PILOT-0911-TEST02 BT-INTAKE-PROOF-REPLY-E9A8-7F3C",
            body="reply",
            gmail_message_id="msg-reply",
            thread_message_ids_oldest_first=["1a09242fdcd542f0", "msg-reply"],
        )
        self.assertTrue(result["eligible"])
        self.assertEqual(result["classification"], CLASS_REPLY)


if __name__ == "__main__":
    unittest.main()
