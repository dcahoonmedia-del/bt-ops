import unittest

from bt_intake_proof.cloud_auth import cloud_authorization_url, impersonation_possible_without_key
from bt_intake_proof.constants import CLOUD_OWNER_HINT, CLOUD_PLATFORM_SCOPE
from bt_intake_proof.receiver_sa import KeyCreationBlocked, refuse_json_key


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

    def test_refuses_json_key_without_source_identity(self) -> None:
        probe = impersonation_possible_without_key()
        self.assertFalse(probe["json_key_required"])
        if not probe["adc_present"] and not probe["cloud_user_token_present"] and not probe["gce_metadata"]:
            with self.assertRaises(KeyCreationBlocked):
                refuse_json_key()


if __name__ == "__main__":
    unittest.main()
