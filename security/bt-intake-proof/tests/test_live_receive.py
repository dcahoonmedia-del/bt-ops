import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bt_intake_proof.constants import MAILBOX
from bt_intake_proof.live_receive import receive_once
from bt_intake_proof.store import ReceiptStore
from test_ack_and_receiver import FakeGmail, _raw_email


class LiveReceiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ReceiptStore(Path(self.tmp.name) / "receipts.sqlite")
        self.store.upsert_watch(MAILBOX, history_id="8000", expiration="1", topic="topic")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_receive_once_acks_only_after_commit(self) -> None:
        payload = json.dumps({"emailAddress": MAILBOX, "historyId": "8001"}).encode("utf-8")
        pull = {
            "subscription": "projects/bt-intake-proof/subscriptions/bt-intake-proof-contactus-sub",
            "received_count": 1,
            "message_ids": ["ps-1"],
            "ack_ids_present": True,
            "received_messages": [
                {
                    "ackId": "ack-1",
                    "message": {
                        "messageId": "ps-1",
                        "data": base64.urlsafe_b64encode(payload).decode("ascii"),
                    },
                }
            ],
        }
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
        with (
            mock.patch("bt_intake_proof.live_receive.pull_subscription", return_value=pull),
            mock.patch("bt_intake_proof.live_receive.acknowledge") as ack_fn,
        ):
            result = receive_once(self.store, gmail, "sa-token")
        ack_fn.assert_called_once_with("sa-token", ["ack-1"])
        self.assertEqual(result["pulled"], 1)
        self.assertEqual(result["acked_count"], 1)
        self.assertEqual(result["processed"][0]["eligible"][0]["test_marker"], "BT-INTAKE-PROOF-NEW-E9A8-7F3C")
        row = self.store.get_receipt(MAILBOX, "msg-new")
        assert row is not None
        self.assertEqual(row["labels_before_json"], row["labels_after_json"])


if __name__ == "__main__":
    unittest.main()
