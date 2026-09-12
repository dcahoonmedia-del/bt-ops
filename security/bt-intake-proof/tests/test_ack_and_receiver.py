import base64
import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path

from bt_intake_proof.constants import DETECTION_EVENT_DRIVEN, DETECTION_RECOVERY, MAILBOX
from bt_intake_proof.gmail_readonly import added_message_ids, assert_readonly_credentials
from bt_intake_proof.receiver import process_notification, recover_from_cursor
from bt_intake_proof.store import ReceiptStore, should_ack


def _raw_email(*, sender: str, to: str, subject: str, body: str, rfc_id: str) -> str:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = rfc_id
    msg["Date"] = "Fri, 11 Sep 2026 21:00:00 -0400"
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


class FakeGmail:
    def __init__(self, messages: dict[str, dict]) -> None:
        self.messages = messages
        self.history_calls: list[str] = []

    def history(self, start_history_id: str) -> dict:
        self.history_calls.append(str(start_history_id))
        added = [
            {"messagesAdded": [{"message": {"id": mid, "threadId": item["threadId"]}}]}
            for mid, item in self.messages.items()
        ]
        return {"history": added, "historyId": "9000"}

    def get_message(self, message_id: str, fmt: str = "raw") -> dict:
        item = self.messages[message_id]
        if fmt == "metadata":
            return {"id": message_id, "labelIds": list(item["labelIds"]), "threadId": item["threadId"]}
        return dict(item)

    def get_thread_message_ids(self, thread_id: str) -> list[str]:
        return [mid for mid, item in self.messages.items() if item["threadId"] == thread_id]


class AckPolicyTests(unittest.TestCase):
    def test_ack_only_after_successful_commit(self) -> None:
        self.assertTrue(should_ack({"ok": True}))
        self.assertFalse(should_ack(None))
        self.assertFalse(should_ack({"ok": False}))
        self.assertFalse(should_ack({"ok": True}, error=RuntimeError("disk")))


class ReceiverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ReceiptStore(Path(self.tmp.name) / "receipts.sqlite")
        self.store.upsert_watch(MAILBOX, history_id="8000", expiration="1", topic="topic")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_event_driven_commit_then_ack(self) -> None:
        acked = []
        nacked = []
        gmail = FakeGmail(
            {
                "msg-new": {
                    "id": "msg-new",
                    "threadId": "thr-new",
                    "labelIds": ["INBOX", "UNREAD"],
                    "raw": _raw_email(
                        sender="daniel@btpestcontrol.com",
                        to=MAILBOX,
                        subject="BT-INTAKE-PROOF-NEW-E9A8-7F3C",
                        body="Internal new-message proof.",
                        rfc_id="<new@bt>",
                    ),
                }
            }
        )
        result = process_notification(
            self.store,
            {"emailAddress": MAILBOX, "historyId": "8001"},
            gmail=gmail,
            detection_path=DETECTION_EVENT_DRIVEN,
            pubsub_message_id="ps-1",
            ack=lambda: acked.append(True),
            nack=lambda: nacked.append(True),
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["acked"])
        self.assertEqual(acked, [True])
        self.assertEqual(nacked, [])
        row = self.store.get_receipt(MAILBOX, "msg-new")
        assert row is not None
        self.assertEqual(row["classification"], "new_message")
        self.assertEqual(row["detection_path"], DETECTION_EVENT_DRIVEN)
        self.assertIn("UNREAD", row["labels_before_json"])
        self.assertEqual(row["labels_before_json"], row["labels_after_json"])

    def test_nack_when_commit_fails(self) -> None:
        acked = []
        nacked = []

        class BoomStore(ReceiptStore):
            def commit_notification(self, **kwargs):  # type: ignore[no-untyped-def]
                raise RuntimeError("sqlite locked")

        boom = BoomStore(Path(self.tmp.name) / "boom.sqlite")
        boom.upsert_watch(MAILBOX, history_id="1", expiration="1", topic="t")
        gmail = FakeGmail(
            {
                "msg-x": {
                    "id": "msg-x",
                    "threadId": "thr-x",
                    "labelIds": ["INBOX"],
                    "raw": _raw_email(
                        sender="daniel@btpestcontrol.com",
                        to=MAILBOX,
                        subject="BT-INTAKE-PROOF-NEW-E9A8-7F3C",
                        body="x",
                        rfc_id="<x@bt>",
                    ),
                }
            }
        )
        result = process_notification(
            boom,
            {"emailAddress": MAILBOX, "historyId": "2"},
            gmail=gmail,
            pubsub_message_id="ps-fail",
            ack=lambda: acked.append(True),
            nack=lambda: nacked.append(True),
        )
        boom.close()
        self.assertFalse(result["ok"])
        self.assertFalse(result["acked"])
        self.assertEqual(acked, [])
        self.assertEqual(nacked, [True])

    def test_recovery_does_not_duplicate(self) -> None:
        gmail = FakeGmail(
            {
                "msg-rec": {
                    "id": "msg-rec",
                    "threadId": "thr-rec",
                    "labelIds": ["INBOX", "UNREAD"],
                    "raw": _raw_email(
                        sender="daniel@btpestcontrol.com",
                        to=MAILBOX,
                        subject="BT-INTAKE-PROOF-RECOVERY-E9A8-7F3C",
                        body="missed while down",
                        rfc_id="<rec@bt>",
                    ),
                }
            }
        )
        first = recover_from_cursor(self.store, gmail)
        second = recover_from_cursor(self.store, gmail)
        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(second["commit"]["duplicates"], 1)
        self.assertEqual(len(self.store.eligible_receipts(MAILBOX)), 1)
        row = self.store.get_receipt(MAILBOX, "msg-rec")
        assert row is not None
        self.assertEqual(row["detection_path"], DETECTION_RECOVERY)

    def test_old_thread_reply_classified(self) -> None:
        raw_old = _raw_email(
            sender="daniel@btpestcontrol.com",
            to=MAILBOX,
            subject="BT-PILOT-0911-TEST02",
            body="original",
            rfc_id="<old@bt>",
        )
        raw_new = _raw_email(
            sender="daniel@btpestcontrol.com",
            to=MAILBOX,
            subject="Re: BT-PILOT-0911-TEST02 BT-INTAKE-PROOF-REPLY-E9A8-7F3C",
            body="reply body",
            rfc_id="<reply@bt>",
        )
        gmail = FakeGmail(
            {
                "old-id": {
                    "id": "old-id",
                    "threadId": "1a09242c087af92c",
                    "labelIds": ["INBOX"],
                    "raw": raw_old,
                },
                "reply-id": {
                    "id": "reply-id",
                    "threadId": "1a09242c087af92c",
                    "labelIds": ["INBOX", "UNREAD"],
                    "raw": raw_new,
                },
            }
        )
        # History only announces the new reply; thread still contains the older message.
        gmail.history = lambda start: {  # type: ignore[method-assign]
            "history": [{"messagesAdded": [{"message": {"id": "reply-id", "threadId": "1a09242c087af92c"}}]}],
            "historyId": "9100",
        }
        result = process_notification(
            self.store,
            {"emailAddress": MAILBOX, "historyId": "8100"},
            gmail=gmail,
            pubsub_message_id="ps-reply",
            ack=lambda: None,
        )
        self.assertTrue(result["ok"])
        row = self.store.get_receipt(MAILBOX, "reply-id")
        assert row is not None
        self.assertEqual(row["thread_id"], "1a09242c087af92c")
        self.assertEqual(row["classification"], "reply")
        self.assertNotEqual(row["gmail_message_id"], "old-id")

    def test_history_parser(self) -> None:
        ids = added_message_ids(
            {
                "history": [
                    {"messagesAdded": [{"message": {"id": "a", "threadId": "t"}}]},
                    {"messagesAdded": [{"message": {"id": "a", "threadId": "t"}}]},
                ]
            }
        )
        self.assertEqual(ids, [{"id": "a", "threadId": "t"}])

    def test_readonly_scope_enforced(self) -> None:
        with self.assertRaises(Exception):
            assert_readonly_credentials(
                ["https://www.googleapis.com/auth/gmail.modify"],
                MAILBOX,
            )
        with self.assertRaises(Exception):
            assert_readonly_credentials(
                ["https://www.googleapis.com/auth/gmail.readonly"],
                "daniel@btpestcontrol.com",
            )


if __name__ == "__main__":
    unittest.main()
