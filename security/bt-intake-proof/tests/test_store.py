import tempfile
import unittest
from pathlib import Path

from bt_intake_proof.constants import CLASS_NEW, DETECTION_EVENT_DRIVEN, MAILBOX
from bt_intake_proof.store import ReceiptStore, body_hash


def eligible_receipt(message_id: str, thread_id: str = "thread-1", **extra):
    body = extra.pop("body_text", f"body for {message_id}")
    raw = extra.pop("raw_message", f"raw:{body}")
    receipt = {
        "eligible": True,
        "gmail_message_id": message_id,
        "thread_id": thread_id,
        "rfc_message_id": f"<{message_id}@btpestcontrol.com>",
        "sender": "daniel@btpestcontrol.com",
        "recipients": [MAILBOX],
        "subject": "BT-INTAKE-PROOF-NEW-E9A8-7F3C",
        "gmail_received_at": "2026-09-12T00:00:00+00:00",
        "detected_at": "2026-09-12T00:00:05+00:00",
        "body_text": body,
        "raw_message": raw,
        "body_hash": body_hash(raw),
        "labels_before": ["INBOX", "UNREAD"],
        "labels_after": ["INBOX", "UNREAD"],
        "classification": CLASS_NEW,
        "test_marker": "BT-INTAKE-PROOF-NEW-E9A8-7F3C",
        "reasons": [],
    }
    receipt.update(extra)
    return receipt


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ReceiptStore(Path(self.tmp.name) / "receipts.sqlite")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_persists_required_fields(self) -> None:
        self.store.upsert_watch(MAILBOX, history_id="100", expiration="1789999999999", topic="projects/x/topics/t")
        result = self.store.commit_notification(
            mailbox=MAILBOX,
            history_id="101",
            detection_path=DETECTION_EVENT_DRIVEN,
            pubsub_message_id="pubsub-1",
            receipts=[eligible_receipt("mid-1")],
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["inserted"], 1)
        row = self.store.get_receipt(MAILBOX, "mid-1")
        assert row is not None
        for field in (
            "gmail_message_id",
            "thread_id",
            "rfc_message_id",
            "sender",
            "recipients_json",
            "subject",
            "gmail_received_at",
            "detected_at",
            "body_text",
            "raw_message",
            "body_hash",
            "labels_before_json",
            "labels_after_json",
            "detection_path",
            "codex_dispatch_state",
        ):
            self.assertTrue(row[field], msg=field)
        self.assertEqual(row["codex_dispatch_state"], "pending")
        self.assertTrue(self.store.labels_unchanged(row))
        cursor = self.store.get_watch(MAILBOX)
        assert cursor is not None
        self.assertEqual(cursor["history_id"], "101")
        self.assertEqual(cursor["watch_expiration"], "1789999999999")

    def test_dedup_on_mailbox_and_message_id(self) -> None:
        first = self.store.commit_notification(
            mailbox=MAILBOX,
            history_id="1",
            detection_path=DETECTION_EVENT_DRIVEN,
            pubsub_message_id="a",
            receipts=[eligible_receipt("mid-dup")],
        )
        second = self.store.commit_notification(
            mailbox=MAILBOX,
            history_id="2",
            detection_path="recovery",
            pubsub_message_id="b",
            receipts=[eligible_receipt("mid-dup", body_text="changed")],
        )
        self.assertEqual(first["inserted"], 1)
        self.assertEqual(second["inserted"], 0)
        self.assertEqual(second["duplicates"], 1)
        self.assertEqual(len(self.store.eligible_receipts(MAILBOX)), 1)
        row = self.store.get_receipt(MAILBOX, "mid-dup")
        assert row is not None
        self.assertEqual(row["body_text"], "body for mid-dup")
        self.assertEqual(row["detection_path"], DETECTION_EVENT_DRIVEN)

    def test_ineligible_customer_body_is_not_stored(self) -> None:
        self.store.commit_notification(
            mailbox=MAILBOX,
            history_id="3",
            detection_path=DETECTION_EVENT_DRIVEN,
            pubsub_message_id="c",
            receipts=[
                {
                    "eligible": False,
                    "gmail_message_id": "cust-9",
                    "thread_id": "thr-cust",
                    "sender": "customer@example.com",
                    "classification": "ineligible",
                    "reasons": ["sender_not_authorized_internal"],
                    "body_text": "Please treat my house",
                    "raw_message": "secret customer body",
                    "subject": "Ants",
                }
            ],
        )
        row = self.store.get_receipt(MAILBOX, "cust-9")
        assert row is not None
        self.assertEqual(row["eligible"], 0)
        self.assertIsNone(row["body_text"])
        self.assertIsNone(row["raw_message"])
        self.assertIsNone(row["subject"])
        self.assertEqual(row["sender"], "")
        self.assertEqual(row["codex_dispatch_state"], "skipped")


if __name__ == "__main__":
    unittest.main()
