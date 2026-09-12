import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from bt_intake_proof.bounded_send import raw_b64
from bt_intake_proof.constants import DESK_SEND_BODY, DESK_SEND_SUBJECT, DESIGNATED_REPLY_THREAD_ID, MAILBOX
from bt_intake_proof.contactus_send import (
    GMAIL_SEND_SCOPE,
    HttpContactusSendGmail,
    classify_gmail_http_error,
    gmail_send_request_payload,
)
from bt_intake_proof.desk_fresh_case import FRESH_THREAD_ID
from bt_intake_proof.phasee_constants import PHASEE_BODY, PHASEE_FROM, PHASEE_SUBJECT, PHASEE_TO
from bt_intake_proof.send_bind import provider_gmail_thread_id
from bt_intake_proof.send_verify import compare_outbound


def _desk_binding(thread_id: str) -> dict:
    return {
        "from_addr": PHASEE_FROM,
        "to_addr": PHASEE_TO,
        "subject": DESK_SEND_SUBJECT,
        "body": DESK_SEND_BODY,
        "thread_id": thread_id,
    }


class GmailSendPayloadTests(unittest.TestCase):
    def test_provider_thread_id_rejects_synthetic_local_key(self) -> None:
        self.assertIsNone(provider_gmail_thread_id(FRESH_THREAD_ID))
        self.assertIsNone(provider_gmail_thread_id("desk-roundtrip-e9a8-20260912"))
        self.assertIsNone(provider_gmail_thread_id("thr-desk-1"))
        self.assertIsNone(provider_gmail_thread_id(""))
        self.assertEqual(provider_gmail_thread_id(DESIGNATED_REPLY_THREAD_ID), DESIGNATED_REPLY_THREAD_ID)
        self.assertEqual(provider_gmail_thread_id("1a09242c087af92c"), "1a09242c087af92c")

    def test_outgoing_json_omits_synthetic_thread_and_keeps_hex(self) -> None:
        synthetic = gmail_send_request_payload(_desk_binding(FRESH_THREAD_ID))
        self.assertEqual(set(synthetic), {"raw"})
        self.assertNotIn("threadId", synthetic)
        hexed = gmail_send_request_payload(_desk_binding(DESIGNATED_REPLY_THREAD_ID))
        self.assertEqual(set(hexed), {"raw", "threadId"})
        self.assertEqual(hexed["threadId"], DESIGNATED_REPLY_THREAD_ID)
        self.assertEqual(synthetic["raw"], raw_b64(_desk_binding(FRESH_THREAD_ID)))

    def test_classify_allowlisted_invalid_thread_without_raw_mail(self) -> None:
        self.assertEqual(
            classify_gmail_http_error(400, '{"error":{"message":"Invalid threadId value"}}'),
            "invalid_gmail_thread_id",
        )
        self.assertEqual(classify_gmail_http_error(400, "Invalid thread_id"), "invalid_gmail_thread_id")
        self.assertEqual(classify_gmail_http_error(400, "other client error"), "http_400")
        self.assertEqual(classify_gmail_http_error(403, "Invalid threadId value"), "http_403")

    def test_http_request_body_does_not_leak_synthetic_thread_id(self) -> None:
        captured: list[dict] = []

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"id": "sent-1", "threadId": "1a09242c087af92c", "labelIds": ["SENT"]}).encode()

        def fake_urlopen(req, timeout=None):
            payload = json.loads(req.data.decode("utf-8"))
            captured.append({"keys": sorted(payload), "has_thread": "threadId" in payload, "threadId": payload.get("threadId")})
            return _Resp()

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        send_path = Path(tmp.name) / "send.json"
        readonly_path = Path(tmp.name) / "readonly.json"
        send_path.write_text("{}", encoding="utf-8")
        readonly_path.write_text("{}", encoding="utf-8")
        with mock.patch("bt_intake_proof.contactus_send.token_path", return_value=readonly_path):
            client = HttpContactusSendGmail("test-token", MAILBOX, [GMAIL_SEND_SCOPE], send_path)
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            sent = client.send_exact(_desk_binding(FRESH_THREAD_ID))
            again = client.send_exact(_desk_binding(DESIGNATED_REPLY_THREAD_ID))
        self.assertTrue(sent.get("ok"), sent)
        self.assertTrue(again.get("ok"), again)
        self.assertEqual(captured[0]["keys"], ["raw"])
        self.assertFalse(captured[0]["has_thread"])
        self.assertEqual(captured[1]["keys"], ["raw", "threadId"])
        self.assertEqual(captured[1]["threadId"], DESIGNATED_REPLY_THREAD_ID)

    def test_http_400_invalid_thread_is_classified_and_not_unknown(self) -> None:
        def fake_urlopen(req, timeout=None):
            payload = json.loads(req.data.decode("utf-8"))
            self.assertNotIn("threadId", payload)
            fp = io.BytesIO(json.dumps({"error": {"message": "Invalid threadId value"}}).encode())
            raise urllib.error.HTTPError(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                400,
                "Bad Request",
                hdrs=None,
                fp=fp,
            )

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        send_path = Path(tmp.name) / "send.json"
        readonly_path = Path(tmp.name) / "readonly.json"
        send_path.write_text("{}", encoding="utf-8")
        readonly_path.write_text("{}", encoding="utf-8")
        with mock.patch("bt_intake_proof.contactus_send.token_path", return_value=readonly_path):
            client = HttpContactusSendGmail("test-token", MAILBOX, [GMAIL_SEND_SCOPE], send_path)
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = client.send_exact(_desk_binding(FRESH_THREAD_ID))
        self.assertFalse(result.get("ok"))
        self.assertFalse(result.get("unknown"))
        self.assertEqual(result.get("reason"), "invalid_gmail_thread_id")
        self.assertNotIn("raw", result)
        self.assertNotIn("Invalid threadId value", json.dumps(result))

    def test_verify_does_not_require_synthetic_thread_match(self) -> None:
        found = {
            "from": PHASEE_FROM,
            "to": [PHASEE_TO],
            "cc": [],
            "bcc": [],
            "subject": DESK_SEND_SUBJECT,
            "body": DESK_SEND_BODY,
            "thread_id": "1a09242c087af92c",
        }
        self.assertEqual(compare_outbound(_desk_binding(FRESH_THREAD_ID), found), [])
        mismatch = compare_outbound(_desk_binding(DESIGNATED_REPLY_THREAD_ID), found)
        self.assertEqual(mismatch, [])
        other = {**found, "thread_id": "1a09242c00000000"}
        self.assertIn("thread", compare_outbound(_desk_binding(DESIGNATED_REPLY_THREAD_ID), other))

    def test_recipient_and_body_checks_still_block(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        send_path = Path(tmp.name) / "send.json"
        readonly_path = Path(tmp.name) / "readonly.json"
        send_path.write_text("{}", encoding="utf-8")
        readonly_path.write_text("{}", encoding="utf-8")
        with mock.patch("bt_intake_proof.contactus_send.token_path", return_value=readonly_path):
            client = HttpContactusSendGmail("test-token", MAILBOX, [GMAIL_SEND_SCOPE], send_path)
        blocked = client.send_exact(
            {
                "from_addr": PHASEE_FROM,
                "to_addr": "someone.else@example.com",
                "subject": PHASEE_SUBJECT,
                "body": PHASEE_BODY,
                "thread_id": DESIGNATED_REPLY_THREAD_ID,
            }
        )
        self.assertEqual(blocked.get("reason"), "payload_not_phasee")


if __name__ == "__main__":
    unittest.main()
