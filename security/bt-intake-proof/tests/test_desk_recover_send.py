import tempfile
import unittest
from pathlib import Path

from bt_intake_proof.bounded_send import MemorySendTransport, execute_desk_queued_sends
from bt_intake_proof.cases import DECISION_APPROVE, CaseLayer
from bt_intake_proof.constants import ALLOWED_SENDER, DESK_SEND_BODY, DESK_SEND_SUBJECT, MAILBOX
from bt_intake_proof.desk_fresh_case import FRESH_THREAD_ID, PHASE_E_CASE_ID, fresh_case_id, prepare_fresh_desk_case
from bt_intake_proof.desk_recover_send import inspect_failed_desk_send, recover_failed_desk_send
from bt_intake_proof.phasee import install_phasee_draft
from bt_intake_proof.phasee_constants import PHASEE_CASE_MARKER, STATUS_FAILED, STATUS_RECEIPT_VERIFIED
from bt_intake_proof.send_bind import (
    QUEUED_BY_DESK,
    QUEUED_BY_PHASEE,
    action_row,
    ensure_send_tables,
    latest_action,
    mark_action,
    queue_desk_send,
    queue_phasee_send,
    record_attempt,
)
from bt_intake_proof.send_verify import MemoryVerifyTransport
from bt_intake_proof.store import ReceiptStore, body_hash


def _phasee_receipt(message_id: str = "phasee-left") -> dict:
    body = f"Internal leftover. {PHASEE_CASE_MARKER}"
    return {
        "eligible": True,
        "mailbox": MAILBOX,
        "gmail_message_id": message_id,
        "thread_id": "1a093f8e919b8787",
        "rfc_message_id": f"<{message_id}@bt>",
        "sender": ALLOWED_SENDER,
        "recipients": [MAILBOX],
        "subject": PHASEE_CASE_MARKER,
        "gmail_received_at": "2026-09-11T12:00:00+00:00",
        "detected_at": "2026-09-11T12:00:05+00:00",
        "body_text": body,
        "raw_message": body,
        "body_hash": body_hash(body),
        "labels_before": ["INBOX"],
        "labels_after": ["INBOX"],
        "classification": "new_message",
        "test_marker": PHASEE_CASE_MARKER,
        "reasons": [],
    }


class _Http400Transport:
    def send_exact(self, binding):
        return {"ok": False, "unknown": False, "reason": "http_400"}


class DeskRecoverSendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ReceiptStore(Path(self.tmp.name) / "receipts.sqlite")
        self.layer = CaseLayer(self.store)
        ensure_send_tables(self.layer)

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _phase_e_verified(self) -> dict:
        self.store.commit_notification(
            mailbox=MAILBOX,
            history_id="phasee-left",
            detection_path="event_driven",
            pubsub_message_id="n-phasee",
            receipts=[_phasee_receipt()],
        )
        row = self.store.get_receipt(MAILBOX, "phasee-left")
        opened = self.layer.upsert_from_receipt(row)
        install_phasee_draft(self.layer, opened["case_id"], "nonce-phasee-left")
        self.layer.apply_decision(
            opened["case_id"],
            DECISION_APPROVE,
            draft_version=int(self.layer.get_case(opened["case_id"])["draft_version"]),
            actor=ALLOWED_SENDER,
        )
        queued = queue_phasee_send(self.layer, opened["case_id"])
        self.assertTrue(queued.get("ok"), queued)
        action = queued["action"]
        mark_action(self.layer, action["id"], status=STATUS_RECEIPT_VERIFIED, consumed=1)
        self.assertEqual(action["id"], 1)
        self.assertEqual(action["queued_by"], QUEUED_BY_PHASEE)
        return action_row(self.layer, 1)

    def _failed_desk_action(self) -> dict:
        leftover = self._phase_e_verified()
        prepared = prepare_fresh_desk_case(self.store)
        self.assertTrue(prepared["ok"])
        case_id = prepared["case_id"]
        self.assertEqual(case_id, fresh_case_id())
        self.assertNotEqual(case_id, PHASE_E_CASE_ID)
        approved = self.layer.apply_decision(
            case_id,
            DECISION_APPROVE,
            draft_version=int(self.layer.get_case(case_id)["draft_version"]),
            actor=ALLOWED_SENDER,
        )
        self.assertTrue(approved["ok"], approved)
        queued = queue_desk_send(self.layer, case_id, control_gmail_id="1a096a36d1051e37")
        self.assertTrue(queued.get("ok"), queued)
        action = queued["action"]
        self.assertEqual(action["id"], 2)
        self.assertEqual(action["queued_by"], QUEUED_BY_DESK)
        self.assertEqual(action["thread_id"], FRESH_THREAD_ID)
        from bt_intake_proof.bounded_send import execute_action

        failed = execute_action(self.layer, action["id"], _Http400Transport(), owner="desk-sender")
        self.assertFalse(failed.get("ok"))
        self.assertEqual(failed.get("reason"), "http_400")
        row = action_row(self.layer, 2)
        self.assertEqual(row["status"], STATUS_FAILED)
        self.assertEqual(int(row["consumed"] or 0), 0)
        self.assertEqual(leftover["status"], STATUS_RECEIPT_VERIFIED)
        return row

    def test_dry_run_does_not_send_or_mutate(self) -> None:
        action = self._failed_desk_action()
        digest = action["payload_sha256"]
        send = MemorySendTransport()
        result = recover_failed_desk_send(
            self.layer,
            execute=False,
            send_transport=send,
            verify_transport=MemoryVerifyTransport(),
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["mode"], "dry_run")
        self.assertFalse(result["executed"])
        self.assertTrue(result["would_execute"])
        self.assertTrue(result["omit_gmail_thread_id"])
        self.assertFalse(result["gmail_request_includes_thread_id"])
        self.assertFalse(result["host_loop_would_select"])
        self.assertFalse(result["rebinding_required"])
        self.assertEqual(send.send_count, 0)
        after = action_row(self.layer, 2)
        self.assertEqual(after["payload_sha256"], digest)
        self.assertEqual(after["thread_id"], FRESH_THREAD_ID)
        self.assertEqual(after["status"], STATUS_FAILED)
        self.assertEqual(int(after["consumed"] or 0), 0)
        self.assertEqual(len(result["attempts"]), 1)

    def test_execute_uses_existing_approval_once_without_requeue(self) -> None:
        action = self._failed_desk_action()
        digest = action["payload_sha256"]
        send = MemorySendTransport()
        result = recover_failed_desk_send(
            self.layer,
            execute=True,
            send_transport=send,
            verify_transport=MemoryVerifyTransport(),
        )
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["executed"])
        self.assertEqual(send.send_count, 1)
        self.assertEqual(send.sent[0]["subject"], DESK_SEND_SUBJECT)
        self.assertEqual(send.sent[0]["body"].strip(), DESK_SEND_BODY.strip())
        self.assertEqual(send.sent[0]["thread_id"], FRESH_THREAD_ID)
        after = action_row(self.layer, 2)
        self.assertEqual(after["payload_sha256"], digest)
        self.assertEqual(after["thread_id"], FRESH_THREAD_ID)
        self.assertNotEqual(after["status"], "queued")
        self.assertEqual(int(after["consumed"] or 0), 1)
        self.assertTrue(result["binding_preserved"])
        self.assertFalse(result["requeued"])
        leftover = action_row(self.layer, 1)
        self.assertEqual(leftover["status"], STATUS_RECEIPT_VERIFIED)
        self.assertEqual(int(leftover["consumed"] or 0), 1)
        again = recover_failed_desk_send(
            self.layer,
            execute=True,
            send_transport=MemorySendTransport(),
            verify_transport=MemoryVerifyTransport(),
        )
        self.assertFalse(again["ok"])
        self.assertIn("recovery_already_authorized", again["blockers"])
        self.assertFalse(again.get("executed"))

    def test_host_loop_does_not_pick_failed_action(self) -> None:
        self._failed_desk_action()
        send = MemorySendTransport()
        self.assertEqual(execute_desk_queued_sends(self.layer, send), [])
        self.assertEqual(send.send_count, 0)
        self.assertEqual(latest_action(self.layer, fresh_case_id())["status"], STATUS_FAILED)

    def test_refuse_unknown_consumed_changed_or_provider_id(self) -> None:
        self._failed_desk_action()
        mark_action(self.layer, 2, status="unknown", consumed=1)
        unknown = inspect_failed_desk_send(self.layer)
        self.assertFalse(unknown["ok"])
        self.assertTrue({"status_not_failed", "already_consumed"} & set(unknown["blockers"]))

        mark_action(self.layer, 2, status=STATUS_FAILED, consumed=0)
        record_attempt(self.layer, 2, "failed", provider_message_id="gmail-should-not-exist", detail="http_400")
        provider = inspect_failed_desk_send(self.layer)
        self.assertIn("provider_message_id_present", provider["blockers"])

        self.layer.conn.execute(
            "UPDATE case_send_actions SET body = ? WHERE id = 2",
            (DESK_SEND_BODY + "\nchanged",),
        )
        changed = inspect_failed_desk_send(self.layer)
        self.assertIn("body_changed", changed["blockers"])

    def test_refuse_phase_e_and_missing_verify_and_existing_sent(self) -> None:
        self._failed_desk_action()
        leftover = recover_failed_desk_send(
            self.layer,
            action_id=1,
            case_id=PHASE_E_CASE_ID,
            execute=False,
        )
        self.assertFalse(leftover["ok"])
        self.assertIn("phase_e_leftover_forbidden", leftover["blockers"])
        self.assertEqual(action_row(self.layer, 1)["status"], STATUS_RECEIPT_VERIFIED)

        missing = recover_failed_desk_send(
            self.layer,
            execute=True,
            send_transport=MemorySendTransport(),
            verify_transport=None,
        )
        self.assertFalse(missing["ok"])
        self.assertIn("verify_unavailable", missing["blockers"])
        self.assertEqual(int(action_row(self.layer, 2)["consumed"] or 0), 0)

        already = recover_failed_desk_send(
            self.layer,
            execute=True,
            send_transport=MemorySendTransport(),
            verify_transport=MemoryVerifyTransport(
                sent=[
                    {
                        "from": MAILBOX,
                        "to": [ALLOWED_SENDER],
                        "cc": [],
                        "bcc": [],
                        "subject": DESK_SEND_SUBJECT,
                        "body": DESK_SEND_BODY,
                        "thread_id": "1a09242c087af92c",
                    }
                ]
            ),
        )
        self.assertFalse(already["ok"])
        self.assertIn("provider_send_or_unknown_outbound", already["blockers"])
        self.assertFalse(already.get("executed"))
        self.assertEqual(int(action_row(self.layer, 2)["consumed"] or 0), 0)


if __name__ == "__main__":
    unittest.main()
