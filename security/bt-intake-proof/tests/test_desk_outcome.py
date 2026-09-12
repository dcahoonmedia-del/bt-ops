import json
import tempfile
import unittest
from pathlib import Path

from bt_intake_proof.bounded_send import MemorySendTransport, execute_desk_queued_sends
from bt_intake_proof.cases import DECISION_APPROVE, CaseLayer
from bt_intake_proof.constants import ALLOWED_SENDER, DESK_SEND_BODY, DESK_SEND_SUBJECT, MAILBOX
from bt_intake_proof.desk_bridge import (
    compute_packet_binding,
    deliver_pending_desk_mail,
    enqueue_on_demand_case,
    enqueue_send_followup,
    enqueue_send_outcome,
    format_control_mail,
    install_desk_send_draft,
    process_control_mail,
)
from bt_intake_proof.desk_control import INTENT_APPROVE_SEND, INTENT_HOLD
from bt_intake_proof.desk_fresh_case import FRESH_THREAD_ID, PHASE_E_CASE_ID, fresh_case_id, prepare_fresh_desk_case
from bt_intake_proof.desk_origin import daniel_origin_evidence
from bt_intake_proof.desk_outcome import STAGE_PROVIDER_ACCEPTED, STAGE_SENT_VERIFIED, action_send_stage, stage_claims
from bt_intake_proof.desk_recover_send import recover_failed_desk_send
from bt_intake_proof.desk_report import report_desk_send_outcome
from bt_intake_proof.desk_runtime import finish_desk_roundtrip
from bt_intake_proof.desk_sent_proof import fixture_sent_lookup, set_test_sent_lookup
from bt_intake_proof.phasee import install_phasee_draft
from bt_intake_proof.phasee_constants import (
    PHASEE_CASE_MARKER,
    STATUS_ATTEMPTED,
    STATUS_FAILED,
    STATUS_RECEIPT_VERIFIED,
    STATUS_SENT_VERIFIED,
)
from bt_intake_proof.send_bind import QUEUED_BY_PHASEE, action_row, ensure_send_tables, mark_action, queue_desk_send, queue_phasee_send
from bt_intake_proof.send_verify import DanielReadonlyInboxVerify, MemoryVerifyTransport, verify_sent
from bt_intake_proof.store import ReceiptStore, body_hash


def _receipt(message_id: str, **extra) -> dict:
    body = extra.pop("body_text", f"Internal desk inbound. {PHASEE_CASE_MARKER}")
    return {
        "eligible": True,
        "mailbox": MAILBOX,
        "gmail_message_id": message_id,
        "thread_id": extra.pop("thread_id", f"thr-{message_id}"),
        "rfc_message_id": f"<{message_id}@bt>",
        "sender": ALLOWED_SENDER,
        "recipients": [MAILBOX],
        "subject": extra.pop("subject", PHASEE_CASE_MARKER),
        "gmail_received_at": "2026-09-12T06:00:00+00:00",
        "detected_at": "2026-09-12T06:00:05+00:00",
        "body_text": body,
        "raw_message": body,
        "body_hash": body_hash(body),
        "labels_before": ["INBOX", "UNREAD"],
        "labels_after": ["INBOX", "UNREAD"],
        "classification": extra.pop("classification", "new_message"),
        "test_marker": extra.pop("test_marker", PHASEE_CASE_MARKER),
        "reasons": [],
    }


class _Http400Transport:
    def send_exact(self, binding):
        return {"ok": False, "unknown": False, "reason": "http_400"}


class DeskOutcomeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "receipts.sqlite"
        self.store = ReceiptStore(self.path)
        self.layer = CaseLayer(self.store)
        ensure_send_tables(self.layer)

    def tearDown(self) -> None:
        set_test_sent_lookup(None)
        self.store.close()
        self.tmp.cleanup()

    def _open_desk(self, message_id: str = "desk-out") -> tuple[str, dict]:
        self.store.commit_notification(
            mailbox=MAILBOX,
            history_id=message_id,
            detection_path="event_driven",
            pubsub_message_id=f"n-{message_id}",
            receipts=[_receipt(message_id, thread_id=f"thr-{message_id}")],
        )
        row = self.store.get_receipt(MAILBOX, message_id)
        opened = self.layer.upsert_from_receipt(row)
        install_desk_send_draft(self.layer, opened["case_id"], f"nonce-{message_id}")
        case = self.layer.get_case(opened["case_id"])
        draft = self.layer.latest_draft(opened["case_id"])
        return opened["case_id"], compute_packet_binding(case, draft)

    def _apply(self, intent: str, binding: dict, **extra) -> dict:
        mail = format_control_mail(intent, binding, owner=extra.get("owner"), note=extra.get("note"))
        mid = extra.get("gmail_message_id", f"ctrl-{intent}-{binding.get('nonce')}")
        body = extra.get("body", mail["body"])
        rfc = extra.get("rfc_message_id", f"<{mid}@desk.btpestcontrol.com>")
        received = extra.get("received_at", "2026-09-12T14:00:00+00:00")
        evidence = extra.get("provider_evidence", daniel_origin_evidence(mid))
        if evidence is not None:
            evidence = {**evidence, "rfc_message_id": rfc, "received_at": received, "recipients": extra.get("recipients", [MAILBOX])}
        lookup = extra.get("sent_lookup")
        if lookup is None and extra.get("sender", ALLOWED_SENDER) == ALLOWED_SENDER:
            lookup = fixture_sent_lookup(mail["subject"], body, rfc_message_id=rfc, received_at=received)
        return process_control_mail(
            self.layer,
            sender=extra.get("sender", ALLOWED_SENDER),
            subject=mail["subject"],
            body=body,
            gmail_message_id=mid,
            provider_evidence=evidence,
            rfc_message_id=rfc,
            recipients=extra.get("recipients", [MAILBOX]),
            received_at=received,
            sent_lookup=lookup,
        )

    def _failed_then_ready(self) -> dict:
        self.store.commit_notification(
            mailbox=MAILBOX,
            history_id="phasee-left",
            detection_path="event_driven",
            pubsub_message_id="n-phasee",
            receipts=[_receipt("phasee-left", thread_id="1a093f8e919b8787")],
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
        leftover = queue_phasee_send(self.layer, opened["case_id"])
        mark_action(self.layer, leftover["action"]["id"], status=STATUS_RECEIPT_VERIFIED, consumed=1)
        prepare_fresh_desk_case(self.store)
        case_id = fresh_case_id()
        self.layer.apply_decision(
            case_id,
            DECISION_APPROVE,
            draft_version=int(self.layer.get_case(case_id)["draft_version"]),
            actor=ALLOWED_SENDER,
        )
        queued = queue_desk_send(self.layer, case_id, control_gmail_id="1a096a36d1051e37")
        from bt_intake_proof.bounded_send import execute_action

        execute_action(self.layer, queued["action"]["id"], _Http400Transport(), owner="desk-sender")
        return action_row(self.layer, 2)

    def test_provider_accept_is_not_recipient_receipt(self) -> None:
        claims = stage_claims(STAGE_PROVIDER_ACCEPTED)
        self.assertTrue(claims["provider_accepted"])
        self.assertFalse(claims["sent_verified"])
        self.assertFalse(claims["recipient_receipt_verified"])
        claims = stage_claims(STAGE_SENT_VERIFIED)
        self.assertTrue(claims["sent_verified"])
        self.assertFalse(claims["recipient_receipt_verified"])

    def test_ordinary_success_one_sent_verified_result_without_receipt_claim(self) -> None:
        _case_id, binding = self._open_desk("desk-ok")
        self.assertTrue(self._apply(INTENT_APPROVE_SEND, binding, gmail_message_id="ctrl-ok")["ok"])
        send = MemorySendTransport()
        verify = MemoryVerifyTransport()

        class Linked(MemoryVerifyTransport):
            def search_sent(self, marker):
                self.sent = list(send.sent)
                return super().search_sent(marker)

        finished = finish_desk_roundtrip(self.store, send_transport=send, verify_transport=Linked())
        self.assertTrue(finished["executed"][0]["ok"])
        self.assertEqual(action_row(self.layer, finished["executed"][0]["action_id"])["status"], STATUS_SENT_VERIFIED)
        rows = [dict(row) for row in self.layer.conn.execute("SELECT kind, status, body FROM desk_result_outbox").fetchall()]
        results = [row for row in rows if row["kind"].startswith("result")]
        self.assertEqual(len(results), 1)
        self.assertNotIn("case", {row["kind"] for row in rows})
        self.assertIn("SEND_STAGE=sent_verified", results[0]["body"])
        self.assertIn("SENT_VERIFIED=yes", results[0]["body"])
        self.assertIn("RECIPIENT_RECEIPT=no", results[0]["body"])
        self.assertIn("not recipient-inbox proof", results[0]["body"])

    def test_ordinary_failed_and_unknown_are_final_and_not_retried(self) -> None:
        _case_id, binding = self._open_desk("desk-fail")
        self.assertTrue(self._apply(INTENT_APPROVE_SEND, binding, gmail_message_id="ctrl-fail")["ok"])
        send = MemorySendTransport(fail=True)
        finished = finish_desk_roundtrip(self.store, send_transport=send, verify_transport=MemoryVerifyTransport())
        self.assertFalse(finished["executed"][0]["ok"])
        body = self.layer.conn.execute("SELECT body FROM desk_result_outbox WHERE kind = 'result'").fetchone()["body"]
        self.assertIn("SEND_STAGE=failed", body)
        self.assertIn("did not complete", body)
        self.assertEqual(execute_desk_queued_sends(self.layer, MemorySendTransport()), [])

        case2, binding2 = self._open_desk("desk-unk")
        self.assertTrue(self._apply(INTENT_APPROVE_SEND, binding2, gmail_message_id="ctrl-unk")["ok"])
        finished2 = finish_desk_roundtrip(self.store, send_transport=MemorySendTransport(timeout=True), verify_transport=MemoryVerifyTransport())
        self.assertTrue(finished2["executed"][0].get("unknown"))
        unknown_body = self.layer.conn.execute(
            "SELECT body FROM desk_result_outbox WHERE control_gmail_id = 'ctrl-unk' AND kind = 'result'"
        ).fetchone()["body"]
        self.assertIn("SEND_STAGE=unknown", unknown_body)
        self.assertEqual(execute_desk_queued_sends(self.layer, MemorySendTransport()), [])

    def test_recovery_success_replaces_stale_failure_and_stays_silent_on_duplicate(self) -> None:
        self._failed_then_ready()
        send = MemorySendTransport()

        class Linked(MemoryVerifyTransport):
            def search_sent(self, marker):
                self.sent = list(send.sent)
                return super().search_sent(marker)

        recovered = recover_failed_desk_send(
            self.layer,
            execute=True,
            send_transport=send,
            verify_transport=Linked(),
        )
        self.assertTrue(recovered["ok"], recovered)
        self.assertEqual(recovered["execute_result"]["send_stage"], STAGE_SENT_VERIFIED)
        self.assertTrue(recovered["execute_result"]["sent_verified"])
        self.assertFalse(recovered["execute_result"]["recipient_receipt_verified"])
        body = self.layer.conn.execute("SELECT body FROM desk_result_outbox WHERE kind LIKE 'result%'").fetchone()["body"]
        self.assertIn("SEND_STAGE=sent_verified", body)
        self.assertNotIn("did not complete", body)
        self.assertIn("RECIPIENT_RECEIPT=no", body)
        first = enqueue_send_outcome(self.layer, 2)
        self.assertTrue(first.get("already_reported") or first.get("updated_pending"))
        before = self.layer.conn.execute("SELECT COUNT(*) FROM desk_result_outbox WHERE kind LIKE 'result%'").fetchone()[0]
        again = enqueue_send_outcome(self.layer, 2)
        after = self.layer.conn.execute("SELECT COUNT(*) FROM desk_result_outbox WHERE kind LIKE 'result%'").fetchone()[0]
        self.assertTrue(again.get("already_reported") or again.get("updated_pending"))
        self.assertEqual(before, after)
        leftover = action_row(self.layer, 1)
        self.assertEqual(leftover["queued_by"], QUEUED_BY_PHASEE)
        self.assertEqual(leftover["status"], STATUS_RECEIPT_VERIFIED)

    def test_recovery_report_does_not_forge_receipt_or_resend(self) -> None:
        self._failed_then_ready()
        send = MemorySendTransport()
        recover_failed_desk_send(self.layer, execute=True, send_transport=send, verify_transport=MemoryVerifyTransport())
        mark_action(self.layer, 2, status=STATUS_SENT_VERIFIED, consumed=1)
        report = report_desk_send_outcome(
            self.layer,
            action_id=2,
            case_id=fresh_case_id(),
            enqueue_result=True,
            sent_transport=MemoryVerifyTransport(sent=list(send.sent)),
            inbox_transport=MemoryVerifyTransport(),
        )
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["send_stage"], STAGE_SENT_VERIFIED)
        self.assertTrue(report["sent_verified"])
        self.assertFalse(report["recipient_receipt_verified"])
        self.assertTrue(report["recipient_receipt_not_claimed_from_api"])
        self.assertFalse(report["would_resend_proof"])
        blocked = report_desk_send_outcome(
            self.layer,
            action_id=2,
            case_id=fresh_case_id(),
            verify_recipient_live=True,
            inbox_transport=None,
        )
        self.assertFalse(blocked["ok"])
        self.assertIn("recipient_verify_unavailable", blocked["blockers"])
        self.assertEqual(action_row(self.layer, 2)["status"], STATUS_SENT_VERIFIED)

    def test_recipient_verify_uses_existing_inbox_verifier_only(self) -> None:
        _case_id, binding = self._open_desk("desk-rcpt")
        self.assertTrue(self._apply(INTENT_APPROVE_SEND, binding, gmail_message_id="ctrl-rcpt")["ok"])
        send = MemorySendTransport()
        executed = execute_desk_queued_sends(self.layer, send)
        enqueue_send_followup(self.layer, executed[0])
        verify_sent(self.layer, executed[0]["action_id"], MemoryVerifyTransport(sent=list(send.sent)))
        self.assertEqual(action_row(self.layer, executed[0]["action_id"])["status"], STATUS_SENT_VERIFIED)
        inbox = MemoryVerifyTransport(
            inbox=[
                {
                    "from": MAILBOX,
                    "to": [ALLOWED_SENDER],
                    "cc": [],
                    "bcc": [],
                    "subject": DESK_SEND_SUBJECT,
                    "body": DESK_SEND_BODY,
                    "label_ids": ["INBOX", "UNREAD"],
                    "id": "daniel-copy",
                }
            ]
        )
        reported = report_desk_send_outcome(
            self.layer,
            action_id=executed[0]["action_id"],
            case_id=_case_id,
            verify_recipient_live=True,
            enqueue_result=True,
            inbox_transport=inbox,
        )
        self.assertTrue(reported["ok"], reported)
        self.assertTrue(reported["recipient_receipt_verified"])
        self.assertEqual(action_row(self.layer, executed[0]["action_id"])["status"], STATUS_RECEIPT_VERIFIED)
        adapter = DanielReadonlyInboxVerify(gmail=type("G", (), {"search_messages": lambda self, q, max_results=10: [], "get_message": lambda self, i, f: {}})())
        self.assertEqual(adapter.search_sent("x"), [])

    def test_restart_delivers_pending_result_once(self) -> None:
        _case_id, binding = self._open_desk("desk-restart")
        self.assertTrue(self._apply(INTENT_APPROVE_SEND, binding, gmail_message_id="ctrl-restart")["ok"])
        send = MemorySendTransport(fail=True)
        finish_desk_roundtrip(self.store, send_transport=send, verify_transport=MemoryVerifyTransport())
        path = self.path
        self.store.close()
        store2 = ReceiptStore(path)
        layer2 = CaseLayer(store2)
        ensure_send_tables(layer2)
        delivered = deliver_pending_desk_mail(layer2, MemorySendTransport())
        self.assertTrue(any(item.get("ok") for item in delivered), delivered)
        again = deliver_pending_desk_mail(layer2, MemorySendTransport())
        self.assertEqual(again, [])
        store2.close()
        self.store = ReceiptStore(path)
        self.layer = CaseLayer(self.store)

    def test_hold_and_ondemand_case_still_available(self) -> None:
        case_id, binding = self._open_desk("desk-hold-out")
        result = self._apply(INTENT_HOLD, binding, gmail_message_id="ctrl-hold-out")
        self.assertTrue(result["ok"])
        kinds = {row["kind"] for row in self.layer.conn.execute("SELECT kind FROM desk_result_outbox").fetchall()}
        self.assertEqual(kinds, {"result", "case"})
        ondemand = enqueue_on_demand_case(self.layer, case_id)
        self.assertTrue(ondemand["ok"])

    def test_stale_failure_mail_does_not_block_accurate_success(self) -> None:
        _case_id, binding = self._open_desk("desk-stale")
        accepted = self._apply(INTENT_APPROVE_SEND, binding, gmail_message_id="ctrl-stale")
        self.assertTrue(accepted["ok"])
        self.layer.conn.execute(
            """
            INSERT INTO desk_result_outbox
                (control_gmail_id, nonce, kind, subject, body, status, created_at, sent_at)
            VALUES (?, ?, 'result', 'old fail', 'SEND_STAGE=failed\n', 'sent', '2026-09-12T17:20:00+00:00', '2026-09-12T17:20:01+00:00')
            """,
            ("ctrl-stale", accepted.get("nonce")),
        )
        send = MemorySendTransport()
        executed = execute_desk_queued_sends(self.layer, send)
        enqueue_send_followup(self.layer, executed[0])
        verify_sent(self.layer, executed[0]["action_id"], MemoryVerifyTransport(sent=list(send.sent)))
        queued = enqueue_send_outcome(self.layer, executed[0]["action_id"])
        self.assertTrue(queued.get("enqueued") or queued.get("updated_pending"), queued)
        bodies = [row["body"] for row in self.layer.conn.execute("SELECT body FROM desk_result_outbox WHERE kind LIKE 'result%'").fetchall()]
        self.assertTrue(any("SEND_STAGE=sent_verified" in body for body in bodies))
        self.assertTrue(any("SEND_STAGE=failed" in body for body in bodies))


if __name__ == "__main__":
    unittest.main()
