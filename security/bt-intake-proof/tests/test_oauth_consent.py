import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bt_intake_proof.constants import GMAIL_READONLY_SCOPE, MAILBOX
from bt_intake_proof.contactus_send import GMAIL_SEND_SCOPE, send_authorization_url
from bt_intake_proof.oauth_consent import (
    OAuthClientError,
    authorization_url,
    blocked_oauth_url,
    extract_auth_code,
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

    def test_send_url_is_send_only_and_separate(self) -> None:
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
                with mock.patch("bt_intake_proof.contactus_send.project_id", return_value="bt-intake-proof"):
                    installed = load_desktop_client(path)
                    payload = send_authorization_url(installed)
                    readonly = authorization_url(installed)
        url = payload["authorization_url"]
        self.assertEqual(payload["scope"], GMAIL_SEND_SCOPE)
        self.assertIn("gmail.send", url)
        self.assertNotIn("gmail.readonly", url)
        self.assertNotIn("gmail.modify", url)
        self.assertNotIn("gmail.compose", url)
        self.assertFalse(payload["widens_intake_readonly"])
        self.assertNotEqual(payload["token_file"], payload["readonly_token_file"])
        self.assertNotIn("gmail.send", readonly["authorization_url"])

    def test_send_exchange_does_not_call_gmail_profile(self) -> None:
        from bt_intake_proof.contactus_send import exchange_send_code

        token_response = {
            "access_token": "ya29.send-only",
            "refresh_token": "1//refresh",
            "token_type": "Bearer",
            "scope": GMAIL_SEND_SCOPE,
        }
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "contactus_gmail_send_token.json"
            readonly = Path(tmp) / "contactus_gmail_readonly_token.json"
            readonly.write_text(json.dumps({"email": MAILBOX, "scopes": [GMAIL_READONLY_SCOPE]}), encoding="utf-8")
            client = {
                "client_id": "123.apps.googleusercontent.com",
                "client_secret": "secret",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
            with mock.patch("bt_intake_proof.contactus_send.load_desktop_client", return_value=client):
                with mock.patch("bt_intake_proof.contactus_send.redirect_uri", return_value="http://localhost"):
                    with mock.patch("bt_intake_proof.contactus_send._post_form", return_value=token_response):
                        with mock.patch("bt_intake_proof.contactus_send.lookup_token_email", return_value=MAILBOX):
                            with mock.patch("bt_intake_proof.contactus_send.send_token_path", return_value=dest):
                                with mock.patch("bt_intake_proof.contactus_send.token_path", return_value=readonly):
                                    payload = exchange_send_code("http://localhost/?code=4/abc&scope=" + GMAIL_SEND_SCOPE)
                                    stored = json.loads(dest.read_text(encoding="utf-8"))
                                    ro_after = json.loads(readonly.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "PASS")
        self.assertTrue(payload["gmail_profile_not_used"])
        self.assertEqual(stored["scopes"], [GMAIL_SEND_SCOPE])
        self.assertEqual(ro_after["scopes"], [GMAIL_READONLY_SCOPE])

    def test_rejects_web_client(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "client.json"
            path.write_text(json.dumps({"web": {"client_id": "x"}}), encoding="utf-8")
            with self.assertRaises(OAuthClientError):
                load_desktop_client(path)

    def test_extracts_code_from_localhost_redirect(self) -> None:
        code = extract_auth_code("http://localhost/?code=4/0Abc&scope=https://www.googleapis.com/auth/gmail.readonly")
        self.assertEqual(code, "4/0Abc")
        self.assertEqual(extract_auth_code("4/0Abc"), "4/0Abc")
        with self.assertRaises(OAuthClientError):
            extract_auth_code("http://localhost/?error=access_denied")

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
