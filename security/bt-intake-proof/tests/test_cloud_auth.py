import unittest

import base64
import json

from bt_intake_proof.cloud_auth import cloud_authorization_url, impersonation_possible_without_key, refresh_cloud_token
from bt_intake_proof.constants import CLOUD_OWNER_HINT, CLOUD_PLATFORM_SCOPE, MAILBOX
from bt_intake_proof.oauth_consent import OAuthClientError
from bt_intake_proof.receiver_sa import KeyCreationBlocked, refuse_json_key, summarize_pull


class CloudAuthTests(unittest.TestCase):
    def test_cloud_url_has_no_gmail_scopes(self) -> None:
        try:
            payload = cloud_authorization_url()
        except Exception as exc:  # noqa: BLE001
            if "Desktop OAuth client JSON is not present" in str(exc):
                self.skipTest("client JSON only exists in the live secrets dir")
            raise
        url = payload["authorization_url"]
        self.assertEqual(payload["scope"], CLOUD_PLATFORM_SCOPE)
        self.assertEqual(payload["sign_in_as"], CLOUD_OWNER_HINT)
        self.assertFalse(payload["gmail_scopes_requested"])
        self.assertFalse(payload["service_account_key_will_be_created"])
        self.assertNotIn("gmail.readonly", url)
        self.assertNotIn("gmail.modify", url)
        self.assertNotIn("gmail.send", url)

    def test_refresh_cloud_token_requires_stored_login(self) -> None:
        from unittest import mock

        with mock.patch("bt_intake_proof.cloud_auth.cloud_token_path") as path_fn:
            missing = path_fn.return_value
            missing.exists.return_value = False
            with self.assertRaises(OAuthClientError):
                refresh_cloud_token()

    def test_summarize_pull_keeps_envelope_only(self) -> None:
        payload = json.dumps({"emailAddress": MAILBOX, "historyId": "6008001"}).encode("utf-8")
        pull = {
            "subscription": "projects/bt-intake-proof/subscriptions/bt-intake-proof-contactus-sub",
            "received_count": 1,
            "message_ids": ["mid-1"],
            "ack_ids_present": True,
            "received_messages": [
                {
                    "ackId": "ack-1",
                    "message": {
                        "messageId": "mid-1",
                        "publishTime": "2026-09-12T02:12:00Z",
                        "data": base64.urlsafe_b64encode(payload).decode("ascii"),
                    },
                }
            ],
        }
        summary = summarize_pull(pull)
        self.assertFalse(summary["acked"])
        self.assertEqual(summary["received_count"], 1)
        self.assertEqual(summary["envelopes"][0]["history_id"], "6008001")
        self.assertTrue(summary["envelopes"][0]["mailbox_match"])
        self.assertNotIn("received_messages", summary)

    def test_refuses_json_key_without_source_identity(self) -> None:
        probe = impersonation_possible_without_key()
        self.assertFalse(probe["json_key_required"])
        if not probe["adc_present"] and not probe["cloud_user_token_present"] and not probe["gce_metadata"]:
            with self.assertRaises(KeyCreationBlocked):
                refuse_json_key()


if __name__ == "__main__":
    unittest.main()
