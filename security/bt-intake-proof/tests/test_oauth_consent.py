import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bt_intake_proof.constants import GMAIL_READONLY_SCOPE, MAILBOX
from bt_intake_proof.oauth_consent import (
    OAuthClientError,
    authorization_url,
    blocked_oauth_url,
    load_desktop_client,
)


class OAuthConsentTests(unittest.TestCase):
    def test_blocked_without_client_json(self) -> None:
        payload = blocked_oauth_url()
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertIsNone(payload["authorization_url"])
        self.assertEqual(payload["scope"], GMAIL_READONLY_SCOPE)
        self.assertEqual(payload["mailbox_required"], MAILBOX)

    def test_desktop_url_is_readonly_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "client.json"
            path.write_text(
                json.dumps(
                    {
                        "installed": {
                            "client_id": "123.apps.googleusercontent.com",
                            "project_id": "bt-intake-proof",
                            "redirect_uris": ["http://localhost"],
                        }
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch("bt_intake_proof.oauth_consent.project_id", return_value="bt-intake-proof"):
                installed = load_desktop_client(path)
                payload = authorization_url(installed)
        self.assertEqual(payload["status"], "READY_FOR_CONTACTUS_CONSENT")
        url = payload["authorization_url"]
        self.assertIn("scope=" + GMAIL_READONLY_SCOPE.replace(":", "%3A").replace("/", "%2F"), url)
        self.assertNotIn("gmail.modify", url)
        self.assertNotIn("gmail.send", url)
        self.assertNotIn("gmail.compose", url)
        self.assertIn("login_hint=" + MAILBOX.replace("@", "%40"), url)
        self.assertIn("include_granted_scopes=false", url)

    def test_rejects_web_client(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "client.json"
            path.write_text(json.dumps({"web": {"client_id": "x"}}), encoding="utf-8")
            with self.assertRaises(OAuthClientError):
                load_desktop_client(path)

    def test_rejects_wrong_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "client.json"
            path.write_text(
                json.dumps({"installed": {"client_id": "x", "project_id": "some-other-project"}}),
                encoding="utf-8",
            )
            with mock.patch("bt_intake_proof.oauth_consent.project_id", return_value="bt-intake-proof"):
                with self.assertRaises(OAuthClientError):
                    load_desktop_client(path)


if __name__ == "__main__":
    unittest.main()
