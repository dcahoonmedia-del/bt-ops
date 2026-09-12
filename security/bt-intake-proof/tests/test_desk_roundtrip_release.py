import inspect
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bt_intake_proof.case_manager import draft_pending_cases
from bt_intake_proof.cases import CaseLayer
from bt_intake_proof.cloud_host import run_once, serve
from bt_intake_proof.constants import (
    ALLOWED_SENDER,
    DESK_SEND_BODY,
    DESK_SEND_SUBJECT,
    DETECTION_EVENT_DRIVEN,
    GMAIL_READONLY_SCOPE,
    MAILBOX,
    MARKER_DESK_RT_CASE,
    MARKER_DESK_SEND,
)
from bt_intake_proof.desk_deploy_env import merge_desk_roundtrip_env, parse_env, protected_unchanged
from bt_intake_proof.desk_fresh_case import (
    FRESH_MESSAGE_ID,
    FRESH_THREAD_ID,
    PHASE_E_CASE_ID,
    assert_not_proof_reply,
    exact_proof_payload,
    fresh_case_id,
    is_desk_roundtrip_receipt,
    prepare_fresh_desk_case,
)
from bt_intake_proof.desk_sent_proof import (
    ExistingDanielSentLookup,
    configured_sent_lookup,
    diagnose_daniel_sent_access,
)
from bt_intake_proof.intake_mode import MODE_ISOLATED_TEST
from bt_intake_proof.send_bind import latest_action
from bt_intake_proof.store import ReceiptStore


class DeskRoundtripReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_helper_token_format_is_ready_and_selects_existing_lookup(self) -> None:
        token = self.root / "daniel_gmail_readonly_token.json"
        token.write_text(
            json.dumps(
                {
                    "email": ALLOWED_SENDER,
                    "account": ALLOWED_SENDER,
                    "scopes": [GMAIL_READONLY_SCOPE],
                    "scope": GMAIL_READONLY_SCOPE,
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "access_token": "not-a-secret-for-tests",
                }
            ),
            encoding="utf-8",
        )
        with mock.patch.dict(os.environ, {"BT_DANIEL_GMAIL_TOKEN": str(token)}):
            access = diagnose_daniel_sent_access()
            self.assertEqual(access["status"], "READY")
            self.assertTrue(access["available"])
            self.assertEqual(access["token_email"], ALLOWED_SENDER)
            self.assertIsInstance(configured_sent_lookup(), ExistingDanielSentLookup)

    def test_boolean_flag_does_not_bypass_sent_lookup(self) -> None:
        from bt_intake_proof.desk_origin import daniel_origin_evidence
        from bt_intake_proof.desk_sent_proof import BlockedSentLookup, authorize_control_sender, inbound_control_view

        inbound = inbound_control_view(
            subject="BT-INTAKE-PROOF-DESK-CTRL-E9A8",
            body="BT-INTAKE-PROOF-DESK-CTRL-E9A8\nINTENT=hold\n",
            rfc_message_id="<no-bypass@bt>",
            recipients=[MAILBOX],
            received_at="2026-09-12T16:00:00+00:00",
            provider_evidence={
                **daniel_origin_evidence("no-bypass"),
                "origin_authenticated": True,
                "origin_already_authenticated": True,
            },
        )
        result = authorize_control_sender(
            None,
            ALLOWED_SENDER,
            inbound["canonical"] and daniel_origin_evidence("no-bypass"),
            inbound,
            sent_lookup=BlockedSentLookup(),
        )
        self.assertFalse(result["accepted"])
        self.assertFalse(result.get("full_identity_pass"))

    def test_host_loop_stays_desk_execute_and_isolated(self) -> None:
        self.assertNotIn("execute_due_sends(", inspect.getsource(run_once))
        self.assertNotIn("execute_due_sends(", inspect.getsource(serve))
        self.assertIn("require_isolated_live_receiver", inspect.getsource(serve))
        self.assertIn("finish_desk_roundtrip", inspect.getsource(run_once))

    def test_env_merge_preserves_tokens_and_forces_isolated(self) -> None:
        existing = parse_env(
            "\n".join(
                [
                    "BT_GMAIL_TOKEN=/opt/bt-intake-proof/secrets/contactus_gmail_readonly_token.json",
                    "BT_GMAIL_SEND_TOKEN=/opt/bt-intake-proof/secrets/contactus_gmail_send_token.json",
                    "BT_INTAKE_MODE=shadow_all",
                    "BT_ALLOW_REAL_CUSTOMER_SENDS=1",
                ]
            )
        )
        merged = merge_desk_roundtrip_env(existing)
        self.assertEqual(merged["BT_GMAIL_TOKEN"], existing["BT_GMAIL_TOKEN"])
        self.assertEqual(merged["BT_GMAIL_SEND_TOKEN"], existing["BT_GMAIL_SEND_TOKEN"])
        self.assertEqual(merged["BT_INTAKE_MODE"], MODE_ISOLATED_TEST)
        self.assertNotIn("BT_ALLOW_REAL_CUSTOMER_SENDS", merged)
        self.assertEqual(
            merged["BT_DANIEL_GMAIL_TOKEN"],
            "/opt/bt-intake-proof/secrets/daniel_gmail_readonly_token.json",
        )

    def test_protected_fingerprint_detects_sqlite_change(self) -> None:
        before = {"sqlite": {"sha256": "aaa"}, "contactus_readonly": {"sha256": "b"}}
        after = {"sqlite": {"sha256": "ccc"}, "contactus_readonly": {"sha256": "b"}}
        self.assertEqual(protected_unchanged(before, after), ["sqlite"])

    def test_prepare_fresh_case_does_not_approve_or_queue(self) -> None:
        store = ReceiptStore(self.root / "receipts.sqlite")
        store.upsert_watch(MAILBOX, history_id="6008029", expiration="9999999999999", topic="topic")
        try:
            result = prepare_fresh_desk_case(store, dest=self.root / "out")
            self.assertTrue(result["ok"])
            self.assertEqual(result["case_id"], fresh_case_id())
            self.assertNotEqual(result["case_id"], PHASE_E_CASE_ID)
            self.assertFalse(result["approve_send_recorded"])
            self.assertFalse(result["send_queued"])
            self.assertFalse(result["proof_reply_sent"])
            layer = CaseLayer(store)
            self.assertIsNone(latest_action(layer, result["case_id"]))
            draft = layer.latest_draft(result["case_id"])
            self.assertEqual(draft["proposed_response"].strip(), DESK_SEND_BODY.strip())
            decisions = layer.conn.execute(
                "SELECT * FROM case_decisions WHERE case_id = ?",
                (result["case_id"],),
            ).fetchall()
            self.assertEqual(decisions, [])
            self.assertEqual(store.get_watch(MAILBOX)["history_id"], "6008029")
            packet = json.loads((self.root / "out" / "DECISION_PACKET.json").read_text(encoding="utf-8"))
            self.assertEqual(packet["exact_internal_send"]["to"], ALLOWED_SENDER)
            self.assertEqual(packet["exact_internal_send"]["subject"], DESK_SEND_SUBJECT)
            self.assertEqual(packet["exact_internal_send"]["body"].strip(), DESK_SEND_BODY.strip())
            self.assertTrue(packet["generic_go_is_not_approval"])
            receipt = store.get_receipt(MAILBOX, FRESH_MESSAGE_ID)
            self.assertEqual(receipt["codex_dispatch_state"], "skipped")
            self.assertTrue(is_desk_roundtrip_receipt(receipt))
        finally:
            store.close()

    def test_case_manager_installs_desk_draft_without_fieldwork(self) -> None:
        store = ReceiptStore(self.root / "cases.sqlite")
        try:
            prepare_fresh_desk_case(store)
            layer = CaseLayer(store)
            layer.conn.execute(
                "UPDATE cases SET stage = 'needs_draft', approval_state = 'none' WHERE case_id = ?",
                (fresh_case_id(),),
            )
            layer.conn.execute("DELETE FROM case_drafts WHERE case_id = ?", (fresh_case_id(),))
            with mock.patch("bt_intake_proof.case_manager.match_and_context") as mocked:
                drafted = draft_pending_cases(store)
            mocked.assert_not_called()
            self.assertEqual(drafted[0]["status"], "PASS")
            self.assertEqual(layer.latest_draft(fresh_case_id())["proposed_response"].strip(), DESK_SEND_BODY.strip())
        finally:
            store.close()

    def test_assert_not_proof_reply(self) -> None:
        assert_not_proof_reply(
            {
                "subject": "BT-INTAKE-PROOF-DESK-CASE-E9A8 BTC-contactus-desk-roundtrip-e9a8-20260912",
                "body": f"BT-INTAKE-PROOF-DESK-CASE-E9A8\n{DESK_SEND_BODY}",
            }
        )
        with self.assertRaises(RuntimeError):
            assert_not_proof_reply({"subject": DESK_SEND_SUBJECT, "body": DESK_SEND_BODY})

    def test_exact_proof_payload_is_internal_only(self) -> None:
        proof = exact_proof_payload()
        self.assertEqual(proof["from"], MAILBOX)
        self.assertEqual(proof["to"], ALLOWED_SENDER)
        self.assertIn(MARKER_DESK_SEND, proof["body"])
        self.assertNotIn("http", proof["body"].lower())
        self.assertEqual(FRESH_THREAD_ID, "desk-roundtrip-e9a8-20260912")


if __name__ == "__main__":
    unittest.main()
