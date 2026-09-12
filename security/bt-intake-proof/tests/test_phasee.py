import inspect
import tempfile
import unittest
from pathlib import Path

from bt_intake_proof.bounded_send import (
    MemorySendTransport,
    MissingContactusSendTransport,
    execute_action,
    execute_due_sends,
)
from bt_intake_proof.case_manager import draft_pending_cases, process_cases
from bt_intake_proof.cases import APPROVAL_APPROVED, CaseLayer, DECISION_APPROVE
from bt_intake_proof.cloud_host import run_once, serve
from bt_intake_proof.constants import CLASS_NEW, DETECTION_EVENT_DRIVEN, MAILBOX
from bt_intake_proof.phasee import exact_phasee_draft
from bt_intake_proof.phasee_constants import (
    PHASEE_BODY,
    PHASEE_CASE_MARKER,
    PHASEE_SEND_MARKER,
    PHASEE_SUBJECT,
    PHASEE_TO,
    STATUS_ATTEMPTED,
    STATUS_QUEUED,
    STATUS_UNKNOWN,
)
from bt_intake_proof.review import format_review_email
from bt_intake_proof.send_bind import (
    ensure_send_tables,
    latest_action,
    payload_sha256,
    queue_phasee_send,
    reject_reasons,
)
from bt_intake_proof.send_verify import MemoryVerifyTransport, verify_recipient, verify_sent
from bt_intake_proof.store import ReceiptStore, body_hash


def _receipt(message_id: str, **extra) -> dict:
    body = extra.pop("body_text", f"Internal Phase E inbound. {PHASEE_CASE_MARKER}")
    return {
        "eligible": True,
        "mailbox": MAILBOX,
        "gmail_message_id": message_id,
        "thread_id": extra.pop("thread_id", "thr-phasee"),
        "rfc_message_id": f"<{message_id}@bt>",
        "sender": "daniel@btpestcontrol.com",
        "recipients": [MAILBOX],
        "subject": extra.pop("subject", PHASEE_CASE_MARKER),
        "gmail_received_at": "2026-09-12T06:00:00+00:00",
        "detected_at": "2026-09-12T06:00:05+00:00",
        "body_text": body,
        "raw_message": body,
        "body_hash": body_hash(body),
        "labels_before": ["INBOX", "UNREAD"],
        "labels_after": ["INBOX", "UNREAD"],
        "classification": extra.pop("classification", CLASS_NEW),
        "test_marker": extra.pop("test_marker", PHASEE_CASE_MARKER),
        "reasons": [],
    }


class PhaseETests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ReceiptStore(Path(self.tmp.name) / "receipts.sqlite")
        self.layer = CaseLayer(self.store)
        ensure_send_tables(self.layer)

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _open_approved(self) -> dict:
        self.store.commit_notification(
            mailbox=MAILBOX,
            history_id="1",
            detection_path=DETECTION_EVENT_DRIVEN,
            pubsub_message_id=None,
            receipts=[_receipt("pe1")],
        )
        row = self.store.get_receipt(MAILBOX, "pe1")
        opened = self.layer.upsert_from_receipt(row)
        drafted = draft_pending_cases(self.store)
        self.assertEqual(drafted[0]["status"], "PASS")
        approved = self.layer.apply_decision(
            opened["case_id"],
            DECISION_APPROVE,
            draft_version=1,
            actor="daniel@btpestcontrol.com",
        )
        self.assertTrue(approved["ok"])
        self.assertFalse(approved["send_triggered"])
        queued = queue_phasee_send(self.layer, opened["case_id"])
        self.assertTrue(queued["ok"])
        return queued["action"]

    def test_exact_approval_binding_and_review_packet(self) -> None:
        action = self._open_approved()
        self.assertEqual(action["from_addr"], MAILBOX)
        self.assertEqual(action["to_addr"], PHASEE_TO)
        self.assertEqual(action["subject"], PHASEE_SUBJECT)
        self.assertEqual(action["body"], PHASEE_BODY)
        self.assertNotIn("DRAFT - NOT SENT", action["body"])
        self.assertEqual(action["status"], STATUS_QUEUED)
        self.assertIn(PHASEE_SEND_MARKER, action["body"])
        email = format_review_email(self.layer.review_packet(action["case_id"]))
        self.assertIn("Exact Phase E send packet", email["body"])
        self.assertIn("CC: (none)", email["body"])
        self.assertIn("Exact body:", email["body"])
        self.assertIn(PHASEE_BODY.strip(), email["body"])
        self.assertIn("authorizes one bounded send", email["body"])
        self.assertIn("FIELDWORK_NOT_ACCESSED", email["body"])

    def test_superseded_draft_cannot_send(self) -> None:
        action = self._open_approved()
        self.layer.save_draft(action["case_id"], exact_phasee_draft(), "nonce-v2")
        transport = MemorySendTransport()
        result = execute_action(self.layer, action["id"], transport)
        self.assertFalse(result["ok"])
        self.assertIn("superseded_draft", result["reasons"])
        self.assertEqual(transport.send_count, 0)

    def test_altered_body_after_approval_cannot_send(self) -> None:
        action = self._open_approved()
        self.layer.conn.execute(
            "UPDATE case_drafts SET proposed_response = ? WHERE case_id = ? AND version = 1",
            (PHASEE_BODY + "\nchanged", action["case_id"]),
        )
        transport = MemorySendTransport()
        result = execute_action(self.layer, action["id"], transport)
        self.assertFalse(result["ok"])
        self.assertIn("body_changed", result["reasons"])
        self.assertEqual(transport.send_count, 0)

    def test_changed_recipient_cannot_send(self) -> None:
        action = self._open_approved()
        binding = {
            "from_addr": MAILBOX,
            "to_addr": "someone.else@example.com",
            "cc": [],
            "bcc": [],
            "attachments": [],
            "body": PHASEE_BODY,
            "subject": PHASEE_SUBJECT,
            "mailbox": MAILBOX,
            "case_id": action["case_id"],
            "draft_version": 1,
        }
        self.assertIn("to_not_daniel", reject_reasons(binding))
        self.layer.conn.execute("UPDATE case_send_actions SET to_addr = ? WHERE id = ?", ("someone.else@example.com", action["id"]))
        transport = MemorySendTransport()
        result = execute_action(self.layer, action["id"], transport)
        self.assertFalse(result["ok"])
        self.assertIn("to_not_daniel", result["reasons"])
        self.assertEqual(transport.send_count, 0)

    def test_new_inbound_invalidates_old_approval(self) -> None:
        action = self._open_approved()
        self.store.commit_notification(
            mailbox=MAILBOX,
            history_id="2",
            detection_path=DETECTION_EVENT_DRIVEN,
            pubsub_message_id=None,
            receipts=[_receipt("pe2", thread_id="thr-phasee", classification="reply", body_text=f"Newer inbound {PHASEE_CASE_MARKER}")],
        )
        reply = self.store.get_receipt(MAILBOX, "pe2")
        reopened = self.layer.upsert_from_receipt(reply)
        self.assertTrue(reopened["approval_superseded"])
        transport = MemorySendTransport()
        result = execute_action(self.layer, action["id"], transport)
        self.assertFalse(result["ok"])
        self.assertTrue({"not_approved", "inbound_changed"} & set(result["reasons"]))
        self.assertEqual(transport.send_count, 0)

    def test_consumed_approval_cannot_send_twice(self) -> None:
        action = self._open_approved()
        transport = MemorySendTransport()
        first = execute_action(self.layer, action["id"], transport)
        second = execute_action(self.layer, action["id"], transport)
        self.assertTrue(first["ok"])
        self.assertTrue(first["consumed"])
        self.assertFalse(second["ok"])
        self.assertEqual(second["reason"], "already_consumed")
        self.assertEqual(transport.send_count, 1)

    def test_timeout_unknown_does_not_resend(self) -> None:
        action = self._open_approved()
        transport = MemorySendTransport(timeout=True)
        result = execute_action(self.layer, action["id"], transport)
        self.assertTrue(result.get("unknown"))
        self.assertTrue(result.get("consumed"))
        self.assertFalse(result.get("resent"))
        self.assertEqual(latest_action(self.layer, action["case_id"])["status"], STATUS_UNKNOWN)
        again = execute_due_sends(self.layer, MemorySendTransport())
        self.assertEqual(again, [])

    def test_independent_verification_not_sender_claim(self) -> None:
        action = self._open_approved()
        transport = MemorySendTransport()
        sent = execute_action(self.layer, action["id"], transport)
        self.assertEqual(sent["status"], STATUS_ATTEMPTED)
        outbound = {
            "id": sent["provider_message_id"],
            "from": MAILBOX,
            "to": [PHASEE_TO],
            "cc": [],
            "bcc": [],
            "subject": PHASEE_SUBJECT,
            "body": PHASEE_BODY,
            "thread_id": action["thread_id"],
            "label_ids": ["SENT"],
        }
        self.assertEqual(transport.sent[0]["body"], PHASEE_BODY)
        self.assertEqual(transport.sent[0]["to_addr"], PHASEE_TO)
        self.assertEqual(transport.sent[0]["subject"], PHASEE_SUBJECT)
        verified = verify_sent(self.layer, action["id"], MemoryVerifyTransport(sent=[outbound]))
        self.assertTrue(verified["ok"])
        receipt = verify_recipient(
            self.layer,
            action["id"],
            MemoryVerifyTransport(inbox=[{**outbound, "id": "inbox-1", "label_ids": ["INBOX", "UNREAD"]}]),
        )
        self.assertTrue(receipt["ok"])
        self.assertTrue(receipt["unread_preserved"])

    def test_phase_c_approve_does_not_queue_send(self) -> None:
        self.store.commit_notification(
            mailbox=MAILBOX,
            history_id="9",
            detection_path=DETECTION_EVENT_DRIVEN,
            pubsub_message_id=None,
            receipts=[
                {
                    **_receipt("c1"),
                    "subject": "BT-INTAKE-PROOF-CASEMGR-NEW-E9A8",
                    "test_marker": "BT-INTAKE-PROOF-CASEMGR-NEW-E9A8",
                    "body_text": "Ordinary Phase C inbound BT-INTAKE-PROOF-CASEMGR-NEW-E9A8",
                    "thread_id": "thr-c",
                }
            ],
        )
        row = self.store.get_receipt(MAILBOX, "c1")
        opened = self.layer.upsert_from_receipt(row)
        self.layer.save_draft(
            opened["case_id"],
            {
                "classification": "ants",
                "known_facts": [],
                "missing_info": [],
                "recommended_next_step": "review",
                "proposed_response": "DRAFT - NOT SENT\n\nThanks.",
                "channel": "email",
            },
            "nonce-c",
        )
        self.layer.apply_decision(opened["case_id"], DECISION_APPROVE, draft_version=1, actor="daniel@btpestcontrol.com")
        queued = queue_phasee_send(self.layer, opened["case_id"])
        self.assertFalse(queued["ok"])
        self.assertEqual(self.layer.get_case(opened["case_id"])["approval_state"], APPROVAL_APPROVED)

    def test_restart_keeps_consumed_and_does_not_resend(self) -> None:
        action = self._open_approved()
        execute_action(self.layer, action["id"], MemorySendTransport())
        path = self.store.path
        self.store.close()
        store2 = ReceiptStore(path)
        layer2 = CaseLayer(store2)
        ensure_send_tables(layer2)
        stored = latest_action(layer2, action["case_id"])
        assert stored is not None
        self.assertEqual(stored["consumed"], 1)
        self.assertEqual(execute_due_sends(layer2, MemorySendTransport()), [])
        store2.close()

    def test_payload_hash_is_stable(self) -> None:
        action = self._open_approved()
        again = payload_sha256(
            {
                "case_id": action["case_id"],
                "draft_version": action["draft_version"],
                "mailbox": action["mailbox"],
                "from_addr": action["from_addr"],
                "to_addr": action["to_addr"],
                "cc": [],
                "bcc": [],
                "thread_id": action["thread_id"],
                "subject": action["subject"],
                "body": action["body"],
                "attachments": [],
                "latest_inbound_message_id": action["latest_inbound_message_id"],
                "send_timing": action["send_timing"],
            }
        )
        self.assertEqual(again, action["payload_sha256"])

    def test_blocked_send_token_does_not_consume(self) -> None:
        action = self._open_approved()
        result = execute_action(self.layer, action["id"], MissingContactusSendTransport())
        self.assertTrue(result.get("blocked"))
        stored = latest_action(self.layer, action["case_id"])
        assert stored is not None
        self.assertEqual(int(stored["consumed"]), 0)

    def test_host_loop_does_not_execute_sends(self) -> None:
        self.assertNotIn("execute_action", inspect.getsource(process_cases))
        self.assertNotIn("execute_due_sends", inspect.getsource(process_cases))
        self.assertNotIn("execute_action", inspect.getsource(run_once))
        self.assertNotIn("execute_due_sends", inspect.getsource(serve))

    def test_phase_c_review_still_says_approval_does_not_send(self) -> None:
        self.store.commit_notification(
            mailbox=MAILBOX,
            history_id="8",
            detection_path=DETECTION_EVENT_DRIVEN,
            pubsub_message_id=None,
            receipts=[
                {
                    **_receipt("c2"),
                    "subject": "BT-INTAKE-PROOF-CASEMGR-NEW-E9A8",
                    "test_marker": "BT-INTAKE-PROOF-CASEMGR-NEW-E9A8",
                    "body_text": "Ordinary Phase C inbound BT-INTAKE-PROOF-CASEMGR-NEW-E9A8",
                    "thread_id": "thr-c-review",
                }
            ],
        )
        row = self.store.get_receipt(MAILBOX, "c2")
        opened = self.layer.upsert_from_receipt(row)
        self.layer.save_draft(
            opened["case_id"],
            {
                "classification": "ants",
                "known_facts": [],
                "missing_info": [],
                "recommended_next_step": "review",
                "proposed_response": "DRAFT - NOT SENT\n\nThanks.",
                "channel": "email",
            },
            "nonce-c2",
        )
        email = format_review_email(self.layer.review_packet(opened["case_id"]))
        self.assertIn("Approval is recorded only", email["body"])
        self.assertIn("Approval does not send anything to a customer", email["body"])
        self.assertNotIn("Exact Phase E send packet", email["body"])


if __name__ == "__main__":
    unittest.main()
