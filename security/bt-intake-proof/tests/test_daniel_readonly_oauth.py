import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bt_intake_proof.constants import ALLOWED_SENDER, GMAIL_READONLY_SCOPE, MAILBOX
from bt_intake_proof.oauth_consent import authorization_url

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "daniel_readonly_oauth.py"


def _load():
    spec = importlib.util.spec_from_file_location("daniel_readonly_oauth", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


mod = _load()


def _client_json(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "123.apps.googleusercontent.com",
                    "client_secret": "desktop-secret",
                    "project_id": "bt-intake-proof",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://127.0.0.1", "http://localhost"],
                }
            }
        ),
        encoding="utf-8",
    )


class DanielReadonlyOauthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.secrets = root / "secrets"
        self.state = root / "state"
        self.secrets.mkdir()
        self.state.mkdir()
        _client_json(self.secrets / "gmail_oauth_client.json")
        self.contactus_ro = self.secrets / "contactus_gmail_readonly_token.json"
        self.contactus_send = self.secrets / "contactus_gmail_send_token.json"
        self.contactus_ro.write_text(json.dumps({"email": MAILBOX, "marker": "readonly-preserve"}), encoding="utf-8")
        self.contactus_send.write_text(json.dumps({"email": MAILBOX, "marker": "send-preserve"}), encoding="utf-8")
        self.paths = {
            "secrets_dir": self.secrets,
            "state_dir": self.state,
            "client": self.secrets / "gmail_oauth_client.json",
            "token": self.secrets / "daniel_gmail_readonly_token.json",
            "setup": self.state / "daniel-oauth-setup.json",
            "auth_url": self.state / "daniel-readonly-auth-url.txt",
            "redirect": self.state / "daniel-oauth-redirect.url",
            "contactus_readonly": self.contactus_ro,
            "contactus_send": self.contactus_send,
            "oauth_client": self.secrets / "gmail_oauth_client.json",
        }
        self.before = mod.contactus_fingerprints(self.paths)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _hash(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_contactus_helper_still_binds_contactus(self) -> None:
        installed = {
            "client_id": "123.apps.googleusercontent.com",
            "project_id": "bt-intake-proof",
            "redirect_uris": ["http://localhost"],
        }
        with mock.patch("bt_intake_proof.oauth_consent.project_id", return_value="bt-intake-proof"):
            payload = authorization_url(installed)
        self.assertEqual(payload["mailbox_required"], MAILBOX)
        self.assertIn("login_hint=" + MAILBOX.replace("@", "%40"), payload["authorization_url"])
        self.assertNotIn("login_hint=" + ALLOWED_SENDER.replace("@", "%40"), payload["authorization_url"])

    def test_start_binds_daniel_readonly_pkce_and_no_listener(self) -> None:
        payload = mod.start(self.paths)
        self.assertEqual(payload["status"], "READY_FOR_DANIEL_READONLY_CONSENT")
        self.assertEqual(payload["mailbox_required"], ALLOWED_SENDER)
        self.assertEqual(payload["scope"], GMAIL_READONLY_SCOPE)
        self.assertEqual(payload["listener"], "none")
        self.assertFalse(payload["authorization_url_printed"])
        url = self.paths["auth_url"].read_text(encoding="utf-8").strip()
        self.assertIn("login_hint=" + ALLOWED_SENDER.replace("@", "%40"), url)
        self.assertNotIn("login_hint=" + MAILBOX.replace("@", "%40"), url)
        self.assertIn("code_challenge_method=S256", url)
        self.assertIn("code_challenge=", url)
        self.assertIn("state=", url)
        self.assertNotIn("gmail.send", url)
        self.assertNotIn("gmail.modify", url)
        setup = json.loads(self.paths["setup"].read_text(encoding="utf-8"))
        self.assertIn("code_verifier", setup)
        self.assertEqual(setup["mailbox_required"], ALLOWED_SENDER)
        self.assertEqual(self._hash(self.contactus_ro), self.before["contactus_readonly"]["sha256"])
        self.assertEqual(self._hash(self.contactus_send), self.before["contactus_send"]["sha256"])

    def test_wrong_state_does_not_write_token_or_touch_contactus(self) -> None:
        started = mod.start(self.paths)
        self.assertTrue(started["setup_file"])
        self.paths["redirect"].write_text("http://127.0.0.1/?code=4/abc&state=wrong-state\n", encoding="utf-8")
        with self.assertRaises(mod.BootstrapError):
            mod.complete(paths=self.paths)
        self.assertFalse(self.paths["token"].exists())
        self.assertEqual(self._hash(self.contactus_ro), self.before["contactus_readonly"]["sha256"])
        self.assertEqual(self._hash(self.contactus_send), self.before["contactus_send"]["sha256"])
        self.assertEqual(self._hash(self.paths["client"]), self.before["oauth_client"]["sha256"])

    def test_wrong_account_refuses(self) -> None:
        setup = json.loads(mod.start(self.paths) and self.paths["setup"].read_text(encoding="utf-8"))
        self.paths["redirect"].write_text(
            f"http://127.0.0.1/?code=4/abc&state={setup['state']}\n", encoding="utf-8"
        )
        token = {
            "access_token": "ya29.daniel",
            "refresh_token": "1//r",
            "scope": GMAIL_READONLY_SCOPE,
            "token_type": "Bearer",
        }
        profile = {"emailAddress": MAILBOX}
        info = {"email": MAILBOX, "scope": GMAIL_READONLY_SCOPE}

        def get_json(url, access_token=None):
            return info if "tokeninfo" in url else profile

        with self.assertRaises(mod.BootstrapError) as raised:
            mod.complete(paths=self.paths, post_form=lambda url, data: token, get_json=get_json)
        self.assertIn(MAILBOX, str(raised.exception))
        self.assertFalse(self.paths["token"].exists())
        self.assertEqual(self._hash(self.contactus_ro), self.before["contactus_readonly"]["sha256"])

    def test_wrong_scope_refuses(self) -> None:
        setup = json.loads(mod.start(self.paths) and self.paths["setup"].read_text(encoding="utf-8"))
        self.paths["redirect"].write_text(
            f"http://127.0.0.1/?code=4/abc&state={setup['state']}\n", encoding="utf-8"
        )
        token = {
            "access_token": "ya29.bad",
            "refresh_token": "1//r",
            "scope": "https://www.googleapis.com/auth/gmail.send",
            "token_type": "Bearer",
        }
        with self.assertRaises(mod.BootstrapError):
            mod.complete(paths=self.paths, post_form=lambda url, data: token, get_json=lambda *a, **k: {})
        self.assertFalse(self.paths["token"].exists())
        self.assertEqual(self._hash(self.contactus_send), self.before["contactus_send"]["sha256"])

    def test_success_writes_daniel_token_only(self) -> None:
        setup = json.loads(mod.start(self.paths) and self.paths["setup"].read_text(encoding="utf-8"))
        self.paths["redirect"].write_text(
            f"http://127.0.0.1/?code=4/abc&state={setup['state']}\n", encoding="utf-8"
        )
        token = {
            "access_token": "ya29.daniel",
            "refresh_token": "1//r",
            "scope": GMAIL_READONLY_SCOPE,
            "token_type": "Bearer",
        }

        def get_json(url, access_token=None):
            if "tokeninfo" in url:
                return {"email": ALLOWED_SENDER, "scope": GMAIL_READONLY_SCOPE}
            return {"emailAddress": ALLOWED_SENDER}

        posted = {}

        def post_form(url, data):
            posted.update(data)
            return token

        payload = mod.complete(paths=self.paths, post_form=post_form, get_json=get_json)
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["email"], ALLOWED_SENDER)
        self.assertTrue(payload["contactus_tokens_unchanged"])
        self.assertFalse(payload["full_identity_pass"])
        stored = json.loads(self.paths["token"].read_text(encoding="utf-8"))
        self.assertEqual(stored["email"], ALLOWED_SENDER)
        self.assertEqual(stored["scopes"], [GMAIL_READONLY_SCOPE])
        self.assertEqual(self.paths["token"].stat().st_mode & 0o777, 0o600)
        self.assertEqual(self._hash(self.contactus_ro), self.before["contactus_readonly"]["sha256"])
        self.assertEqual(self._hash(self.contactus_send), self.before["contactus_send"]["sha256"])
        self.assertEqual(self._hash(self.paths["client"]), self.before["oauth_client"]["sha256"])
        self.assertFalse(self.paths["setup"].exists())
        self.assertFalse(self.paths["auth_url"].exists())
        self.assertFalse(self.paths["redirect"].exists())
        self.assertIn("code_verifier", posted)
        self.assertEqual(posted["code"], "4/abc")

    def test_expired_state_refuses(self) -> None:
        mod.start(self.paths)
        setup = json.loads(self.paths["setup"].read_text(encoding="utf-8"))
        setup["expires_unix"] = 1
        self.paths["setup"].write_text(json.dumps(setup), encoding="utf-8")
        self.paths["redirect"].write_text(
            f"http://127.0.0.1/?code=4/abc&state={setup['state']}\n", encoding="utf-8"
        )
        with self.assertRaises(mod.BootstrapError):
            mod.complete(paths=self.paths)
        self.assertFalse(self.paths["token"].exists())


if __name__ == "__main__":
    unittest.main()
