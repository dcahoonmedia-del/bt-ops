import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bt_intake_proof.constants import CODEX_NAMESPACE, CODEX_TOOL_NAME, MAILBOX
from bt_intake_proof.dispatch import build_constructor, build_external_content
from bt_intake_proof.gates import diagnose_google, is_usable_project_id
from bt_intake_proof.setup_google import blocked_setup


class DispatchTests(unittest.TestCase):
    def test_payload_is_external_and_unauthorized(self) -> None:
        receipt = {
            "eligible": True,
            "mailbox": MAILBOX,
            "gmail_message_id": "mid-1",
            "thread_id": "thr-1",
            "rfc_message_id": "<mid-1@bt>",
            "sender": "daniel@btpestcontrol.com",
            "recipients": [MAILBOX],
            "subject": "BT-INTAKE-PROOF-NEW-E9A8-7F3C",
            "gmail_received_at": "2026-09-12T00:00:00+00:00",
            "detected_at": "2026-09-12T00:00:05+00:00",
            "detection_path": "event_driven",
            "classification": "new_message",
            "test_marker": "BT-INTAKE-PROOF-NEW-E9A8-7F3C",
            "body_hash": "abc",
            "body_text": "Internal proof body",
        }
        ctor = build_constructor(receipt, "nonce-1")
        self.assertEqual(ctor["tool_name"], CODEX_TOOL_NAME)
        self.assertEqual(ctor["namespace"], CODEX_NAMESPACE)
        self.assertFalse(ctor["authorization"])
        self.assertIn("NONCE=nonce-1", ctor["content"])
        self.assertIn("AUTHORIZATION=false", ctor["content"])
        self.assertIn("Internal proof body", ctor["content"])
        self.assertIn("external_untrusted_tool_output", ctor["content"])

    def test_refuses_ineligible_receipt(self) -> None:
        with self.assertRaises(ValueError):
            build_external_content({"eligible": False, "body_text": "customer"}, "n")


class GateTests(unittest.TestCase):
    def test_missing_project_is_blocked_not_chosen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "secrets"
            secrets.mkdir()
            with mock.patch.dict(os.environ, {}, clear=True):
                os.environ.pop("BT_GCP_PROJECT_ID", None)
                os.environ.pop("BT_GCP_ALLOW_RESOURCE_CREATE", None)
                os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
                os.environ.pop("CLOUDSDK_CORE_PROJECT", None)
                with mock.patch("bt_intake_proof.gates.SECRETS", secrets):
                    with mock.patch("bt_intake_proof.gates.CONFIG_PATH", Path(tmp) / "missing.toml"):
                        diagnosis = diagnose_google()
        self.assertEqual(diagnosis["status"], "BLOCKED")
        self.assertIsNone(diagnosis["project_id"])
        ids = {item["id"] for item in diagnosis["decisions_required"]}
        self.assertIn("gcp_project_id", ids)
        self.assertIn("contactus_readonly_consent", ids)
        setup = blocked_setup(diagnosis)
        self.assertTrue(setup["stop"])
        self.assertFalse(setup["watch_registered"])

    def test_placeholder_project_id_is_rejected(self) -> None:
        self.assertFalse(is_usable_project_id("<PUT_PROJECT_ID_HERE>"))
        self.assertFalse(is_usable_project_id("PUT_PROJECT_ID_HERE"))
        self.assertTrue(is_usable_project_id("bt-intake-proof-2026"))
        with tempfile.TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "secrets"
            secrets.mkdir()
            env = {"BT_GCP_PROJECT_ID": "<PUT_PROJECT_ID_HERE>"}
            with mock.patch.dict(os.environ, env, clear=False):
                with mock.patch("bt_intake_proof.gates.SECRETS", secrets):
                    with mock.patch("bt_intake_proof.gates.CONFIG_PATH", Path(tmp) / "missing.toml"):
                        diagnosis = diagnose_google()
        self.assertEqual(diagnosis["status"], "BLOCKED")
        self.assertIsNone(diagnosis["project_id"])
        self.assertEqual(diagnosis["rejected_project_id"], "<PUT_PROJECT_ID_HERE>")

    def test_write_scope_token_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            secrets = Path(tmp)
            token = secrets / "contactus_gmail_readonly_token.json"
            token.write_text(
                json.dumps(
                    {
                        "email": MAILBOX,
                        "scopes": [
                            "https://www.googleapis.com/auth/gmail.readonly",
                            "https://www.googleapis.com/auth/gmail.send",
                        ],
                    }
                ),
                encoding="utf-8",
            )
            client = secrets / "gmail_oauth_client.json"
            client.write_text("{}", encoding="utf-8")
            env = {
                "BT_GCP_PROJECT_ID": "example-not-used",
                "BT_GCP_ALLOW_RESOURCE_CREATE": "yes",
                "BT_GMAIL_OAUTH_CLIENT": str(client),
                "BT_GMAIL_TOKEN": str(token),
            }
            with mock.patch.dict(os.environ, env, clear=False):
                with mock.patch("bt_intake_proof.gates.SECRETS", secrets):
                    diagnosis = diagnose_google()
        self.assertEqual(diagnosis["status"], "FAIL")
        self.assertTrue(diagnosis["scope_violations"])


if __name__ == "__main__":
    unittest.main()
