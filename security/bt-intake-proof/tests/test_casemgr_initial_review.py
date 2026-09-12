"""Initial CASEMGR review delivery through process_cases. No live mail."""

from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bt_intake_proof.bounded_send import MemorySendTransport
from bt_intake_proof.case_manager import process_cases
from bt_intake_proof.cases import CaseLayer, case_id_for
from bt_intake_proof.cli import main as cli_main
from bt_intake_proof.constants import (
    ALLOWED_SENDER,
    CLASS_NEW,
    DETECTION_EVENT_DRIVEN,
    MAILBOX,
    MARKER_DESK_BIND,
    MARKER_DESK_CASE,
)
from bt_intake_proof.desk_bridge import (
    ALLOWED_INITIAL_REVIEW_RECOVERY_IDS,
    KIND_CASE_INITIAL,
    enqueue_control_deliveries,
    ensure_bridge_tables,
    format_result_email,
    recover_initial_review_for_inbound,
    recover_pending_initial_reviews,
    record_initial_review_intent,
)
from bt_intake_proof.desk_runtime import finish_desk_roundtrip
from bt_intake_proof.eligibility import evaluate_message
from bt_intake_proof.phasee_constants import PHASEE_CASE_MARKER
from bt_intake_proof.send_bind import ensure_send_tables
from bt_intake_proof.store import ReceiptStore, body_hash, utc_now

PHONE_MARKER = "BT-INTAKE-PROOF-CASEMGR-PHONE-7C92"
PHONE_INBOUND = "1a096ffa404426f1"
BRENDA_THREAD = "1a096d60643b3b1a"
BRENDA_CASE = "BTC-contactus-1a096d60643b3b1a"


def _receipt(message_id: str, **extra) -> dict:
    marker = extra.pop("test_marker", "BT-INTAKE-PROOF-CASEMGR-NEW-E9A8")
    body = extra.pop("body_text", f"Internal CASEMGR draft test. {marker}")
    return {
        "eligible": True,
        "mailbox": MAILBOX,
        "gmail_message_id": message_id,
        "thread_id": extra.pop("thread_id", f"thr-{message_id}"),
        "rfc_message_id": f"<{message_id}@bt>",
        "sender": ALLOWED_SENDER,
        "recipients": [MAILBOX],
        "subject": extra.pop("subject", marker),
        "gmail_received_at": extra.pop("gmail_received_at", "2026-09-12T19:00:00+00:00"),
        "detected_at": "2026-09-12T19:00:05+00:00",
        "body_text": body,
        "raw_message": body,
        "body_hash": body_hash(body),
        "labels_before": ["INBOX", "UNREAD"],
        "labels_after": ["INBOX", "UNREAD"],
        "classification": extra.pop("classification", CLASS_NEW),
        "test_marker": marker,
        "reasons": [],
    }


def _draft() -> dict:
    return {
        "classification": "internal_casemgr_review",
        "known_facts": ["internal kitchen ants note"],
        "missing_info": ["callback number"],
        "recommended_next_step": "ask for address and phone",
        "proposed_response": "DRAFT - NOT SENT\n\nThanks for writing. Please share the service address.\n",
        "channel": "email",
        "judgment_needed": "review wording",
        "reasoning_summary": "fixture draft",
    }


def _fieldwork() -> dict:
    return {
        "status": "not_run",
        "source_label": "FIELDWORK_FIXTURE",
        "live": False,
        "read_only": True,
        "writes_allowed": False,
        "reason": "unit_test",
    }


class CaseMgrInitialReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "receipts.sqlite"
        self.store = ReceiptStore(self.path)
        self.layer = CaseLayer(self.store)
        ensure_send_tables(self.layer)
        ensure_bridge_tables(self.layer)
        self._seed_consumed_actions()

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _seed_consumed_actions(self) -> None:
        now = utc_now()
        for action_id, case_id in ((1, "BTC-consumed-action-1"), (2, "BTC-consumed-action-2")):
            self.layer.conn.execute(
                """
                INSERT INTO case_send_actions (
                    id, case_id, draft_version, created_at, mailbox, from_addr, to_addr,
                    cc_json, bcc_json, thread_id, subject, body, attachments_json,
                    latest_inbound_message_id, payload_sha256, send_timing, status, consumed
                ) VALUES (?, ?, 1, ?, ?, ?, ?, '[]', '[]', ?, 'kept', 'kept', '[]', 'kept', 'kept', 'immediate', 'recipient_receipt_verified', 1)
                """,
                (action_id, case_id, now, MAILBOX, MAILBOX, ALLOWED_SENDER, f"thr-{case_id}"),
            )

    def _assert_actions_untouched(self) -> None:
        rows = [dict(row) for row in self.layer.conn.execute("SELECT id, status, consumed FROM case_send_actions WHERE id IN (1, 2) ORDER BY id")]
        self.assertEqual(
            rows,
            [
                {"id": 1, "status": "recipient_receipt_verified", "consumed": 1},
                {"id": 2, "status": "recipient_receipt_verified", "consumed": 1},
            ],
        )

    def _commit(self, *receipts: dict) -> None:
        self.store.commit_notification(
            mailbox=MAILBOX,
            history_id="1",
            detection_path=DETECTION_EVENT_DRIVEN,
            pubsub_message_id=None,
            receipts=list(receipts),
        )

    def _process_normal(self, *, draft_ok: bool = True) -> dict:
        ran = {
            "ok": draft_ok,
            "draft": _draft(),
            "empty_user_input": True,
            "content_in_user_input": False,
            "reason": None if draft_ok else "codex_draft_failed",
        }
        with mock.patch("bt_intake_proof.case_manager.match_and_context", return_value=_fieldwork()):
            with mock.patch("bt_intake_proof.case_manager.run_codex_draft", return_value=ran) as mocked:
                result = process_cases(self.store)
        result["_draft_mock"] = mocked
        return result

    def _outbox(self, *, kind: str = KIND_CASE_INITIAL) -> list[dict]:
        return [
            dict(row)
            for row in self.layer.conn.execute(
                "SELECT * FROM desk_result_outbox WHERE kind = ? ORDER BY id",
                (kind,),
            )
        ]

    def test_eligibility_accepts_phone_marker(self) -> None:
        verdict = evaluate_message(
            mailbox=MAILBOX,
            sender=ALLOWED_SENDER,
            recipients=[MAILBOX],
            subject=PHONE_MARKER,
            body=f"Internal inquiry. {PHONE_MARKER}",
            gmail_message_id=PHONE_INBOUND,
        )
        self.assertTrue(verdict["eligible"])
        self.assertEqual(verdict["marker"], PHONE_MARKER)

    def test_process_cases_enqueues_one_current_case_packet(self) -> None:
        self._commit(_receipt(" inbound-new ".strip(), test_marker="BT-INTAKE-PROOF-CASEMGR-NEW-E9A8"))
        first = self._process_normal()
        self.assertEqual(first["drafted"][0]["status"], "PASS")
        rows = self._outbox()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "pending")
        self.assertEqual(rows[0]["control_gmail_id"], "inbound-new")
        self.assertIn(MARKER_DESK_CASE, rows[0]["subject"])
        self.assertIn(MARKER_DESK_BIND, rows[0]["body"])
        self.assertIn("PACKET_HASH=", rows[0]["body"])
        self.assertIn("DRAFT - NOT SENT", rows[0]["body"])
        self.assertIn("Please share the service address.", rows[0]["body"])
        self.assertEqual(self.layer.latest_draft(first["drafted"][0]["case_id"])["proposed_response"].count("Please share the service address."), 1)
        self._assert_actions_untouched()

    def test_repeat_and_restart_do_not_queue_extra(self) -> None:
        self._commit(_receipt(" inbound-repeat ".strip()))
        self._process_normal()
        self._process_normal()
        self.store.close()
        store2 = ReceiptStore(self.path)
        try:
            with mock.patch("bt_intake_proof.case_manager.match_and_context", return_value=_fieldwork()):
                with mock.patch("bt_intake_proof.case_manager.run_codex_draft", return_value={"ok": True, "draft": _draft()}):
                    process_cases(store2)
            rows = list(store2.conn.execute("SELECT id, status FROM desk_result_outbox WHERE kind = ?", (KIND_CASE_INITIAL,)))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "pending")
        finally:
            store2.close()
        self.store = ReceiptStore(self.path)
        self.layer = CaseLayer(self.store)
        self._assert_actions_untouched()

    def test_interrupted_enqueue_recovers_on_process_cases(self) -> None:
        self._commit(_receipt("inbound-crash"))
        self._process_normal()
        self.layer.conn.execute("DELETE FROM desk_result_outbox WHERE kind = ?", (KIND_CASE_INITIAL,))
        self.layer.conn.execute(
            "UPDATE case_initial_reviews SET status = 'pending_enqueue', queued_at = NULL WHERE inbound_message_id = ?",
            ("inbound-crash",),
        )
        self.assertEqual(self._outbox(), [])
        recovered = process_cases(self.store)
        self.assertTrue(recovered["initial_reviews"][0]["ok"])
        rows = self._outbox()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "pending")
        self.assertIn(MARKER_DESK_CASE, rows[0]["subject"])

    def test_failed_drafting_produces_no_packet(self) -> None:
        self._commit(_receipt("inbound-fail"))
        result = self._process_normal(draft_ok=False)
        self.assertEqual(result["drafted"][0]["status"], "FAIL")
        self.assertEqual(self._outbox(), [])
        self.assertEqual(list(self.layer.conn.execute("SELECT * FROM case_initial_reviews")), [])
        self._assert_actions_untouched()

    def test_delivered_and_unknown_are_not_retried(self) -> None:
        self._commit(_receipt("inbound-sent"))
        self._process_normal()
        self.layer.conn.execute(
            "UPDATE desk_result_outbox SET status = 'sent' WHERE kind = ?",
            (KIND_CASE_INITIAL,),
        )
        process_cases(self.store)
        sent = self._outbox()
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["status"], "sent")
        self.layer.conn.execute(
            "UPDATE desk_result_outbox SET status = 'unknown' WHERE kind = ?",
            (KIND_CASE_INITIAL,),
        )
        process_cases(self.store)
        unknown = self._outbox()
        self.assertEqual(len(unknown), 1)
        self.assertEqual(unknown[0]["status"], "unknown")

    def test_historical_completed_brenda_case_is_not_backfilled(self) -> None:
        self._commit(
            _receipt(
                BRENDA_THREAD,
                thread_id=BRENDA_THREAD,
                test_marker="BT-INTAKE-PROOF-CASEMGR-DRAFT-E9A8",
                subject="BT-INTAKE-PROOF-CASEMGR-DRAFT-E9A8 completed fixture",
            )
        )
        row = self.store.get_receipt(MAILBOX, BRENDA_THREAD)
        opened = self.layer.upsert_from_receipt(row)
        self.assertEqual(opened["case_id"], BRENDA_CASE)
        self.layer.save_draft(BRENDA_CASE, _draft(), f"bt-case-{BRENDA_CASE}-r{BRENDA_THREAD}")
        self.layer.conn.execute("UPDATE cases SET owner = 'brenda' WHERE case_id = ?", (BRENDA_CASE,))
        process_cases(self.store)
        self.assertEqual(self._outbox(), [])
        case = self.layer.get_case(BRENDA_CASE)
        assert case is not None
        self.assertEqual(case["owner"], "brenda")
        self.assertEqual(case["draft_version"], 1)
        self.assertEqual(self.layer.conn.execute("SELECT COUNT(*) FROM case_send_actions WHERE case_id = ?", (BRENDA_CASE,)).fetchone()[0], 0)
        self._assert_actions_untouched()

    def test_phasee_and_stale_intent_do_not_fake_or_backfill(self) -> None:
        self._commit(_receipt("pe-in", test_marker=PHASEE_CASE_MARKER, subject=PHASEE_CASE_MARKER, body_text=f"Phase E {PHASEE_CASE_MARKER}"))
        process_cases(self.store)
        self.assertEqual(self._outbox(), [])
        self._commit(_receipt("inbound-stale"))
        self._process_normal()
        case_id = case_id_for(MAILBOX, "thr-inbound-stale")
        self.layer.conn.execute("DELETE FROM desk_result_outbox WHERE kind = ?", (KIND_CASE_INITIAL,))
        self.layer.conn.execute(
            "UPDATE case_initial_reviews SET status = 'pending_enqueue', queued_at = NULL WHERE inbound_message_id = ?",
            ("inbound-stale",),
        )
        self.layer.save_draft(case_id, {**_draft(), "proposed_response": "DRAFT - NOT SENT\n\nNewer text.\n"}, "nonce-v2")
        recovered = recover_pending_initial_reviews(self.layer)
        self.assertTrue(recovered[0].get("stale"))
        self.assertEqual(self._outbox(), [])

    def test_runtime_delivers_once_then_none(self) -> None:
        self._commit(_receipt("inbound-deliver"))
        self._process_normal()
        send = MemorySendTransport()
        first = finish_desk_roundtrip(self.store, send_transport=send)
        self.assertEqual(len([item for item in first["delivered"] if item.get("ok")]), 1)
        self.assertEqual(len(send.sent), 1)
        self.assertIn(MARKER_DESK_CASE, send.sent[0]["subject"])
        second = finish_desk_roundtrip(self.store, send_transport=send)
        extra = [item for item in second["delivered"] if item.get("ok")]
        self.assertEqual(extra, [])
        self.assertEqual(len(send.sent), 1)
        process_cases(self.store)
        third = finish_desk_roundtrip(self.store, send_transport=send)
        self.assertEqual([item for item in third["delivered"] if item.get("ok")], [])
        self.assertEqual(len(send.sent), 1)

    def test_control_case_supersedes_pending_initial(self) -> None:
        self._commit(_receipt("inbound-ctrl"))
        self._process_normal()
        case_id = case_id_for(MAILBOX, "thr-inbound-ctrl")
        enqueue_control_deliveries(
            self.layer,
            {
                "ok": True,
                "control_gmail_id": "ctrl-later",
                "case_id": case_id,
                "nonce": "ctrl-nonce",
                "result_email": format_result_email({"ok": True, "intent": "revise_draft", "case_id": case_id}),
            },
        )
        initial = self._outbox()[0]
        self.assertEqual(initial["status"], "superseded")
        case_rows = [
            dict(row)
            for row in self.layer.conn.execute("SELECT kind, status FROM desk_result_outbox WHERE kind LIKE 'case%' ORDER BY id")
        ]
        self.assertIn({"kind": "case", "status": "pending"}, case_rows)

    def test_explicit_recovery_is_bounded_and_does_not_redraft(self) -> None:
        self.assertEqual(ALLOWED_INITIAL_REVIEW_RECOVERY_IDS, frozenset({PHONE_INBOUND}))
        self._commit(
            _receipt(
                PHONE_INBOUND,
                thread_id="phone-7c92-thread",
                test_marker=PHONE_MARKER,
                subject=PHONE_MARKER,
                body_text=f"Internal inquiry only. {PHONE_MARKER}",
            )
        )
        row = self.store.get_receipt(MAILBOX, PHONE_INBOUND)
        opened = self.layer.upsert_from_receipt(row)
        saved = self.layer.save_draft(opened["case_id"], _draft(), f"bt-case-{opened['case_id']}-r{PHONE_INBOUND}")
        blocked = recover_initial_review_for_inbound(self.layer, BRENDA_THREAD, enqueue=True)
        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["reason"], "recovery_id_not_allowed")
        dry = recover_initial_review_for_inbound(self.layer, PHONE_INBOUND, enqueue=False)
        self.assertTrue(dry["ok"])
        self.assertFalse(dry["execute"])
        self.assertFalse(dry["model_rerun"])
        self.assertEqual(self._outbox(), [])
        with mock.patch("bt_intake_proof.case_manager.run_codex_draft") as mocked_draft:
            queued = recover_initial_review_for_inbound(self.layer, PHONE_INBOUND, enqueue=True)
        mocked_draft.assert_not_called()
        self.assertTrue(queued["ok"])
        self.assertEqual(self.layer.latest_draft(opened["case_id"])["proposed_response"], saved["proposed_response"])
        rows = self._outbox()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["control_gmail_id"], PHONE_INBOUND)
        self.assertEqual(self.layer.conn.execute("SELECT COUNT(*) FROM desk_control_consumed").fetchone()[0], 0)
        again = recover_initial_review_for_inbound(self.layer, PHONE_INBOUND, enqueue=True)
        self.assertTrue(again["queued"]["skipped"])
        self.assertEqual(len(self._outbox()), 1)

    def test_cli_dry_run_does_not_enqueue(self) -> None:
        self._commit(
            _receipt(
                PHONE_INBOUND,
                thread_id="phone-cli-thread",
                test_marker=PHONE_MARKER,
                subject=PHONE_MARKER,
            )
        )
        row = self.store.get_receipt(MAILBOX, PHONE_INBOUND)
        opened = self.layer.upsert_from_receipt(row)
        self.layer.save_draft(opened["case_id"], _draft(), f"bt-case-{opened['case_id']}-r{PHONE_INBOUND}")
        code = cli_main(["recover-initial-case-review", "--gmail-id", PHONE_INBOUND, "--store", str(self.path)])
        self.assertEqual(code, 0)
        self.assertEqual(self._outbox(), [])

    def test_process_cases_still_does_not_execute_sends(self) -> None:
        source = inspect.getsource(process_cases)
        self.assertNotIn("execute_action", source)
        self.assertNotIn("execute_due_sends", source)
        self.assertIn("recover_pending_initial_reviews", source)


if __name__ == "__main__":
    unittest.main()
