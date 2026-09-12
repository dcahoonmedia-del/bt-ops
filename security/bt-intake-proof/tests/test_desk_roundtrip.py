import json
import threading
import tempfile
import unittest
from pathlib import Path

from bt_intake_proof.bounded_send import (
    CrashAfterAccept,
    CrashAfterAcceptTransport,
    MemorySendTransport,
    execute_desk_queued_sends,
    execute_due_sends,
    reconcile_incomplete_desk_sends,
)
from bt_intake_proof.cases import CaseLayer
from bt_intake_proof.constants import (
    ALLOWED_SENDER,
    CLASS_DESK_TRANSPORT,
    DESK_SEND_BODY,
    DETECTION_EVENT_DRIVEN,
    MAILBOX,
    MARKER_DESK_CASE,
    MARKER_DESK_CTRL,
    MARKER_DESK_RESULT,
    MARKER_DESK_SEND,
)
from bt_intake_proof.desk_bridge import (
    compute_packet_binding,
    deliver_pending_desk_mail,
    enqueue_on_demand_case,
    enqueue_send_followup,
    format_control_mail,
    inspect_inbound,
    install_desk_send_draft,
    process_control_mail,
    reconcile_sending_outbox,
)
from bt_intake_proof.desk_control import INTENT_APPROVE_SEND, INTENT_HOLD, INTENT_REVISE
from bt_intake_proof.desk_origin import authenticate_control_origin, daniel_origin_evidence, unquoted_control_text
from bt_intake_proof.desk_sent_proof import fixture_sent_lookup, set_test_sent_lookup
from bt_intake_proof.desk_runtime import finish_desk_roundtrip
from bt_intake_proof.phasee import install_phasee_draft
from bt_intake_proof.phasee_constants import PHASEE_CASE_MARKER, STATUS_ATTEMPTED, STATUS_QUEUED, STATUS_UNKNOWN
from bt_intake_proof.receiver import hydrate_receipt
from bt_intake_proof.send_bind import QUEUED_BY_DESK, QUEUED_BY_PHASEE, ensure_send_tables, latest_action, queue_phasee_send
from bt_intake_proof.send_verify import MemoryVerifyTransport, verify_sent
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


class DeskRoundtripTests(unittest.TestCase):
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

    def _open_desk(self, message_id: str = "desk-1") -> tuple[str, dict]:
        self.store.commit_notification(
            mailbox=MAILBOX,
            history_id=message_id,
            detection_path=DETECTION_EVENT_DRIVEN,
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
            evidence = {
                **evidence,
                "rfc_message_id": rfc,
                "received_at": received,
                "recipients": extra.get("recipients", [MAILBOX]),
            }
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

    def test_from_alone_and_forged_ar_fail_closed(self) -> None:
        _case_id, binding = self._open_desk()
        mail = format_control_mail(INTENT_HOLD, binding)
        bare = inspect_inbound(ALLOWED_SENDER, mail["subject"], mail["body"])
        self.assertFalse(bare["sender_ok"])
        forged = authenticate_control_origin(
            [("Authentication-Results", "evil.example; dkim=pass header.i=@btpestcontrol.com")],
            ALLOWED_SENDER,
            {"fetched_via": "contactus_gmail_api", "gmail_message_id": "x"},
        )
        self.assertFalse(forged["accepted"])
        self.assertEqual(forged["reason"], "authentication_results_not_gmail")
        spoofed = self._apply(
            INTENT_HOLD,
            binding,
            gmail_message_id="spoof-from",
            provider_evidence={
                "fetched_via": "contactus_gmail_api",
                "gmail_message_id": "spoof-from",
                "headers": [
                    (
                        "Authentication-Results",
                        "mx.google.com; dkim=pass header.i=@attacker.test; spf=pass smtp.mailfrom=attacker@attacker.test",
                    ),
                    ("From", ALLOWED_SENDER),
                ],
            },
        )
        self.assertFalse(spoofed["ok"])
        self.assertEqual(spoofed["reason"], "provider_auth_failed")
        self.assertEqual(int(self.layer.get_case(_case_id)["hold"] or 0), 0)

    def test_quoted_control_syntax_does_not_authorize(self) -> None:
        case_id, binding = self._open_desk("desk-quote")
        mail = format_control_mail(INTENT_HOLD, binding)
        quoted = "Thanks, we will wait.\n\n" + "\n".join(f"> {line}" for line in mail["body"].splitlines())
        self.assertNotIn("INTENT=hold", unquoted_control_text(quoted))
        result = self._apply(INTENT_HOLD, binding, gmail_message_id="quoted-1", body=quoted)
        self.assertFalse(result["ok"])
        self.assertEqual(int(self.layer.get_case(case_id)["hold"] or 0), 0)

    def test_malformed_and_bad_binding(self) -> None:
        case_id, binding = self._open_desk("desk-malformed")
        bad = self._apply(INTENT_HOLD, {**binding, "packet_hash": "0" * 64}, gmail_message_id="bad-bind")
        self.assertFalse(bad["ok"])
        self.assertIn("packet_hash_invalid", bad.get("blocks") or [])
        mail = format_control_mail("not_an_intent", binding)
        mid = "bad-intent"
        rfc = f"<{mid}@desk.btpestcontrol.com>"
        received = "2026-09-12T14:00:00+00:00"
        result = process_control_mail(
            self.layer,
            sender=ALLOWED_SENDER,
            subject=mail["subject"],
            body=mail["body"],
            gmail_message_id=mid,
            provider_evidence={
                **daniel_origin_evidence(mid),
                "rfc_message_id": rfc,
                "received_at": received,
                "recipients": [MAILBOX],
            },
            rfc_message_id=rfc,
            recipients=[MAILBOX],
            received_at=received,
            sent_lookup=fixture_sent_lookup(mail["subject"], mail["body"], rfc_message_id=rfc, received_at=received),
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "unsupported_bridge_intent")
        self.assertEqual(int(self.layer.get_case(case_id)["hold"] or 0), 0)

    def test_result_delivery_and_fresh_case_packet(self) -> None:
        case_id, binding = self._open_desk("desk-deliver")
        result = self._apply(INTENT_HOLD, binding, gmail_message_id="ctrl-deliver")
        self.assertTrue(result["ok"], result)
        transport = MemorySendTransport()
        delivered = deliver_pending_desk_mail(self.layer, transport)
        kinds = {row["kind"] for row in self.layer.conn.execute("SELECT kind FROM desk_result_outbox").fetchall()}
        self.assertIn("result", kinds)
        self.assertIn("case", kinds)
        self.assertTrue(all(item.get("ok") for item in delivered), delivered)
        subjects = [item["subject"] for item in transport.sent]
        self.assertTrue(any(MARKER_DESK_RESULT in subject for subject in subjects))
        self.assertTrue(any(MARKER_DESK_CASE in subject for subject in subjects))
        again = deliver_pending_desk_mail(self.layer, transport)
        self.assertEqual(again, [])
        self.assertEqual(int(self.layer.get_case(case_id)["hold"] or 0), 1)

    def test_rejected_action_still_enqueues_result(self) -> None:
        _case_id, binding = self._open_desk("desk-reject")
        result = self._apply(INTENT_HOLD, {**binding, "nonce": "wrong"}, gmail_message_id="ctrl-reject")
        self.assertFalse(result["ok"])
        rows = self.layer.conn.execute("SELECT kind, status FROM desk_result_outbox").fetchall()
        self.assertTrue(rows)
        self.assertTrue(any(row["kind"] == "result" for row in rows))

    def test_execute_verify_and_phasee_leftover_ignored(self) -> None:
        case_id, binding = self._open_desk("desk-exec")
        accepted = self._apply(INTENT_APPROVE_SEND, binding, gmail_message_id="ctrl-exec")
        self.assertTrue(accepted["ok"], accepted)
        action = latest_action(self.layer, case_id)
        self.assertEqual(action["queued_by"], QUEUED_BY_DESK)
        self.assertEqual(action["status"], STATUS_QUEUED)

        leftover_id, _ = self._open_desk("phasee-left")
        install_phasee_draft(self.layer, leftover_id, "nonce-phasee-left")
        self.layer.apply_decision(leftover_id, "approve", draft_version=int(self.layer.get_case(leftover_id)["draft_version"]), actor=ALLOWED_SENDER)
        queued = queue_phasee_send(self.layer, leftover_id)
        self.assertTrue(queued.get("ok"), queued)
        self.assertEqual(queued["action"]["queued_by"], QUEUED_BY_PHASEE)

        send = MemorySendTransport()
        executed = execute_desk_queued_sends(self.layer, send)
        self.assertEqual(len(executed), 1)
        self.assertTrue(executed[0]["ok"], executed)
        self.assertEqual(executed[0]["status"], STATUS_ATTEMPTED)
        leftover = latest_action(self.layer, leftover_id)
        self.assertEqual(int(leftover["consumed"] or 0), 0)
        self.assertEqual(leftover["status"], STATUS_QUEUED)

        verify = MemoryVerifyTransport(sent=list(send.sent))
        checked = verify_sent(self.layer, executed[0]["action_id"], verify)
        self.assertTrue(checked["ok"], checked)
        self.assertEqual(latest_action(self.layer, case_id)["status"], "sent_verified")

    def test_freshness_hold_and_revision_block_before_execute(self) -> None:
        case_id, binding = self._open_desk("desk-fresh")
        accepted = self._apply(INTENT_APPROVE_SEND, binding, gmail_message_id="ctrl-fresh")
        self.assertTrue(accepted["ok"], accepted)
        self.layer.conn.execute("UPDATE cases SET hold = 1 WHERE case_id = ?", (case_id,))
        send = MemorySendTransport()
        executed = execute_desk_queued_sends(self.layer, send)
        self.assertEqual(len(executed), 1)
        self.assertFalse(executed[0]["ok"])
        self.assertEqual(executed[0]["reason"], "invalid_approval")
        self.assertIn("hold", executed[0]["reasons"])
        self.assertEqual(send.send_count, 0)

        case_id2, binding2 = self._open_desk("desk-rev")
        queued = self._apply(INTENT_APPROVE_SEND, binding2, gmail_message_id="ctrl-rev-q")
        self.assertTrue(queued["ok"], queued)
        self.layer.save_draft(
            case_id2,
            {
                "classification": "revised",
                "proposed_response": DESK_SEND_BODY + "\nchanged",
                "channel": "email",
            },
            nonce="nonce-changed",
            label_not_sent=False,
        )
        executed2 = execute_desk_queued_sends(self.layer, MemorySendTransport())
        self.assertFalse(executed2[0]["ok"])
        self.assertTrue({"superseded_draft", "stale_draft_version", "body_changed"} & set(executed2[0]["reasons"]))

    def test_sequential_replay_and_reopen(self) -> None:
        case_id, binding = self._open_desk("desk-replay")
        first = self._apply(INTENT_APPROVE_SEND, binding, gmail_message_id="ctrl-replay-1")
        self.assertTrue(first["ok"], first)
        replay_same = self._apply(INTENT_APPROVE_SEND, binding, gmail_message_id="ctrl-replay-1")
        self.assertTrue(replay_same.get("replayed"))
        replay_new = self._apply(INTENT_APPROVE_SEND, binding, gmail_message_id="ctrl-replay-2")
        self.assertFalse(replay_new["ok"])
        self.assertIn("nonce_consumed", replay_new.get("blocks") or [])
        self.assertEqual(self.layer.conn.execute("SELECT COUNT(*) FROM case_send_actions").fetchone()[0], 1)

        path = self.store.path
        self.store.close()
        store2 = ReceiptStore(path)
        layer2 = CaseLayer(store2)
        ensure_send_tables(layer2)
        send = MemorySendTransport()
        executed = execute_desk_queued_sends(layer2, send)
        self.assertTrue(executed[0]["ok"], executed)
        store2.close()
        store3 = ReceiptStore(path)
        layer3 = CaseLayer(store3)
        ensure_send_tables(layer3)
        verify = MemoryVerifyTransport(sent=list(send.sent))
        checked = verify_sent(layer3, executed[0]["action_id"], verify)
        self.assertTrue(checked["ok"], checked)
        self.assertEqual(execute_desk_queued_sends(layer3, MemorySendTransport()), [])
        store3.close()
        self.store = ReceiptStore(path)
        self.layer = CaseLayer(self.store)

    def test_unknown_send_does_not_retry(self) -> None:
        case_id, binding = self._open_desk("desk-unknown")
        self.assertTrue(self._apply(INTENT_APPROVE_SEND, binding, gmail_message_id="ctrl-unknown")["ok"])
        timed_out = execute_desk_queued_sends(self.layer, MemorySendTransport(timeout=True))
        self.assertTrue(timed_out[0].get("unknown"))
        self.assertEqual(latest_action(self.layer, case_id)["status"], STATUS_UNKNOWN)
        again = execute_desk_queued_sends(self.layer, MemorySendTransport())
        self.assertEqual(again, [])
        leftovers = execute_due_sends(self.layer, MemorySendTransport())
        self.assertEqual(leftovers, [])

    def test_host_finish_delivers_and_executes_only_desk(self) -> None:
        case_id, binding = self._open_desk("desk-host")
        self.assertTrue(self._apply(INTENT_APPROVE_SEND, binding, gmail_message_id="ctrl-host")["ok"])
        send = MemorySendTransport()
        verify = MemoryVerifyTransport()
        finished = finish_desk_roundtrip(self.store, send_transport=send, verify_transport=verify)
        self.assertTrue(any(item.get("ok") for item in finished["executed"]))
        verify.sent.extend(send.sent)
        finished2 = finish_desk_roundtrip(self.store, send_transport=send, verify_transport=verify)
        self.assertEqual(finished2["executed"], [])
        self.assertTrue(any(item.get("ok") for item in finished2["verified"] or finished["verified"]))
        self.assertGreaterEqual(len(send.sent), 2)
        self.assertEqual(latest_action(self.layer, case_id)["queued_by"], QUEUED_BY_DESK)

    def test_stale_inbound_rejects_send(self) -> None:
        case_id, binding = self._open_desk("desk-inbound")
        self.layer.conn.execute(
            "UPDATE cases SET latest_inbound_message_id = ? WHERE case_id = ?",
            ("newer-inbound", case_id),
        )
        result = self._apply(INTENT_APPROVE_SEND, binding, gmail_message_id="ctrl-inbound")
        self.assertFalse(result["ok"])
        self.assertTrue({"inbound_changed", "packet_hash_invalid"} & set(result.get("blocks") or []))
        self.assertIsNone(latest_action(self.layer, case_id))

    def test_desk_transport_is_not_a_case(self) -> None:
        receipt = hydrate_receipt(
            MAILBOX,
            {
                "id": "pkt-1",
                "threadId": "thr-pkt",
                "labelIds": ["INBOX"],
                "raw": __import__("base64").urlsafe_b64encode(
                    (
                        "From: contactus@btpestcontrol.com\r\n"
                        "To: daniel@btpestcontrol.com\r\n"
                        f"Subject: {MARKER_DESK_RESULT}\r\n\r\n"
                        f"{MARKER_DESK_RESULT}\r\nSTATUS=ok\r\n"
                    ).encode("utf-8")
                ).decode("ascii"),
            },
            ["pkt-1"],
            DETECTION_EVENT_DRIVEN,
        )
        self.assertEqual(receipt["classification"], CLASS_DESK_TRANSPORT)
        self.assertFalse(receipt["eligible"])

    def test_control_loop_forbidden_on_result_sender(self) -> None:
        from bt_intake_proof.contactus_send import HttpContactusSendGmail

        class Fake(HttpContactusSendGmail):
            def __init__(self) -> None:  # noqa: D107
                pass

            def _submit_raw(self, binding):
                raise AssertionError("must not submit CTRL")

        fake = Fake()
        blocked = HttpContactusSendGmail.send_internal_desk(
            fake,
            {"from_addr": MAILBOX, "to": ALLOWED_SENDER, "subject": MARKER_DESK_CTRL, "body": MARKER_DESK_CTRL},
        )
        self.assertEqual(blocked["reason"], "desk_ctrl_loop_forbidden")

    def test_simultaneous_nonce_consume_two_connections(self) -> None:
        _case_id, binding = self._open_desk("desk-conc-nonce")
        path = self.path
        barrier = threading.Barrier(2)
        results: list[dict | BaseException | None] = [None, None]

        def worker(index: int, mid: str) -> None:
            store = ReceiptStore(path)
            layer = CaseLayer(store)
            ensure_send_tables(layer)
            mail = format_control_mail(INTENT_HOLD, binding)
            rfc = f"<{mid}@desk.btpestcontrol.com>"
            received = "2026-09-12T14:00:00+00:00"
            barrier.wait()
            try:
                results[index] = process_control_mail(
                    layer,
                    sender=ALLOWED_SENDER,
                    subject=mail["subject"],
                    body=mail["body"],
                    gmail_message_id=mid,
                    provider_evidence={
                        **daniel_origin_evidence(mid),
                        "rfc_message_id": rfc,
                        "received_at": received,
                        "recipients": [MAILBOX],
                    },
                    rfc_message_id=rfc,
                    recipients=[MAILBOX],
                    received_at=received,
                    sent_lookup=fixture_sent_lookup(
                        mail["subject"], mail["body"], rfc_message_id=rfc, received_at=received
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                results[index] = exc
            finally:
                store.close()

        threads = [
            threading.Thread(target=worker, args=(0, "ctrl-conc-a")),
            threading.Thread(target=worker, args=(1, "ctrl-conc-b")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        ended = results
        self.assertTrue(all(not isinstance(item, Exception) for item in ended), ended)
        oks = [item for item in ended if isinstance(item, dict) and item.get("ok")]
        blocks = [item for item in ended if isinstance(item, dict) and not item.get("ok")]
        self.assertEqual(len(oks), 1, ended)
        self.assertEqual(len(blocks), 1, ended)
        self.assertIn("nonce_consumed", (blocks[0].get("blocks") or []))
        self.store = ReceiptStore(path)
        self.layer = CaseLayer(self.store)
        self.assertEqual(self.layer.conn.execute("SELECT COUNT(*) FROM desk_control_consumed").fetchone()[0], 1)

    def test_simultaneous_execute_and_result_delivery(self) -> None:
        case_id, binding = self._open_desk("desk-conc-exec")
        queued = self._apply(INTENT_APPROVE_SEND, binding, gmail_message_id="ctrl-conc-exec")
        self.assertTrue(queued["ok"], queued)
        path = self.path
        barrier = threading.Barrier(2)
        exec_results: list = [None, None]
        send = MemorySendTransport()
        send_lock = threading.Lock()

        class LockedSend(MemorySendTransport):
            def send_exact(self, binding):  # noqa: ANN001
                with send_lock:
                    return send.send_exact(binding)

            def send_internal_desk(self, mail):  # noqa: ANN001
                with send_lock:
                    return send.send_internal_desk(mail)

        def exec_worker(index: int) -> None:
            store = ReceiptStore(path)
            layer = CaseLayer(store)
            ensure_send_tables(layer)
            barrier.wait()
            try:
                exec_results[index] = execute_desk_queued_sends(layer, LockedSend())
            finally:
                store.close()

        threads = [threading.Thread(target=exec_worker, args=(i,)) for i in (0, 1)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        accepted = [item for batch in exec_results if batch for item in batch if item.get("ok")]
        self.assertEqual(len(accepted), 1, exec_results)
        self.assertEqual(send.send_count, 1)
        self.store = ReceiptStore(path)
        self.layer = CaseLayer(self.store)
        self.assertEqual(int(latest_action(self.layer, case_id)["consumed"] or 0), 1)
        enqueue_send_followup(self.layer, accepted[0])

        barrier2 = threading.Barrier(2)
        deliver_hits: list = [None, None]

        def deliver_worker(index: int) -> None:
            store = ReceiptStore(path)
            layer = CaseLayer(store)
            barrier2.wait()
            try:
                deliver_hits[index] = deliver_pending_desk_mail(layer, LockedSend())
            finally:
                store.close()

        threads = [threading.Thread(target=deliver_worker, args=(i,)) for i in (0, 1)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        sent_ok = [item for batch in deliver_hits if batch for item in batch if item.get("ok")]
        self.assertGreaterEqual(len(sent_ok), 1)
        pending = self.layer.conn.execute(
            "SELECT COUNT(*) FROM desk_result_outbox WHERE status = 'pending'"
        ).fetchone()[0]
        sending = self.layer.conn.execute(
            "SELECT COUNT(*) FROM desk_result_outbox WHERE status = 'sending'"
        ).fetchone()[0]
        self.assertEqual(pending, 0)
        self.assertEqual(sending, 0)

    def test_crash_after_accept_before_persist_reconciles(self) -> None:
        case_id, binding = self._open_desk("desk-crash")
        self.assertTrue(self._apply(INTENT_APPROVE_SEND, binding, gmail_message_id="ctrl-crash")["ok"])
        crashing = CrashAfterAcceptTransport()
        with self.assertRaises(CrashAfterAccept):
            execute_desk_queued_sends(self.layer, crashing)
        stuck = latest_action(self.layer, case_id)
        self.assertEqual(int(stuck["consumed"] or 0), 0)
        self.assertIsNotNone(stuck["locked_at"])
        self.assertEqual(len(crashing.sent), 1)
        verify = MemoryVerifyTransport(sent=list(crashing.sent))
        recovered = reconcile_incomplete_desk_sends(self.layer, verify)
        self.assertEqual(len(recovered), 1)
        self.assertTrue(recovered[0]["recovered"])
        stored = latest_action(self.layer, case_id)
        self.assertEqual(int(stored["consumed"] or 0), 1)
        self.assertEqual(stored["status"], STATUS_ATTEMPTED)
        self.assertIsNone(stored["locked_at"])
        self.assertEqual(execute_desk_queued_sends(self.layer, MemorySendTransport()), [])

        empty = CrashAfterAcceptTransport()
        case_id2, binding2 = self._open_desk("desk-crash-empty")
        self.assertTrue(self._apply(INTENT_APPROVE_SEND, binding2, gmail_message_id="ctrl-crash-empty")["ok"])
        with self.assertRaises(CrashAfterAccept):
            execute_desk_queued_sends(self.layer, empty)
        unlocked = reconcile_incomplete_desk_sends(self.layer, MemoryVerifyTransport())
        self.assertTrue(unlocked[0].get("unlocked"))
        retry = execute_desk_queued_sends(self.layer, MemorySendTransport())
        self.assertTrue(retry[0]["ok"], retry)

    def test_result_delivery_crash_does_not_stick(self) -> None:
        _case_id, binding = self._open_desk("desk-outbox-crash")
        self.assertTrue(self._apply(INTENT_HOLD, binding, gmail_message_id="ctrl-outbox-crash")["ok"])

        class CrashDeliver(MemorySendTransport):
            def send_internal_desk(self, mail):
                result = super().send_internal_desk(mail)
                raise CrashAfterAccept(result)

        crashing = CrashDeliver()
        with self.assertRaises(CrashAfterAccept):
            deliver_pending_desk_mail(self.layer, crashing)
        sending = self.layer.conn.execute(
            "SELECT COUNT(*) FROM desk_result_outbox WHERE status = 'sending'"
        ).fetchone()[0]
        self.assertGreaterEqual(sending, 1)
        recovered = reconcile_sending_outbox(self.layer, list(crashing.sent))
        self.assertTrue(any(item.get("recovered") for item in recovered), recovered)
        leftover_sending = self.layer.conn.execute(
            "SELECT COUNT(*) FROM desk_result_outbox WHERE status = 'sending'"
        ).fetchone()[0]
        self.assertEqual(leftover_sending, 0)
        again = deliver_pending_desk_mail(self.layer, MemorySendTransport())
        recovered_ids = {item["id"] for item in recovered if item.get("recovered")}
        resent = [item for item in again if item.get("ok") and item.get("id") in recovered_ids]
        self.assertEqual(resent, [])

    def test_approve_send_defers_queued_mail_until_final_outcome(self) -> None:
        case_id, binding = self._open_desk("desk-defer")
        accepted = self._apply(INTENT_APPROVE_SEND, binding, gmail_message_id="ctrl-defer")
        self.assertTrue(accepted["ok"], accepted)
        self.assertTrue(accepted.get("send_queued"))
        self.assertTrue(accepted.get("human_mail_deferred"))
        inbox = self.layer.conn.execute(
            "SELECT result_json FROM desk_control_inbox WHERE gmail_message_id = ?",
            ("ctrl-defer",),
        ).fetchone()
        stored = json.loads(inbox["result_json"])
        self.assertTrue(stored.get("ok"))
        self.assertTrue(stored.get("send_queued"))
        self.assertEqual(stored.get("case_id"), case_id)
        pending = self.layer.conn.execute(
            "SELECT kind FROM desk_result_outbox WHERE status = 'pending'"
        ).fetchall()
        self.assertEqual([row["kind"] for row in pending], [])

        send = MemorySendTransport(fail=True)
        executed = execute_desk_queued_sends(self.layer, send)
        enqueue_send_followup(self.layer, executed[0])
        rows = [dict(row) for row in self.layer.conn.execute("SELECT kind, status FROM desk_result_outbox").fetchall()]
        kinds = [row["kind"] for row in rows]
        self.assertEqual(kinds.count("result"), 1)
        self.assertNotIn("case", kinds)
        self.assertNotIn("case_send", kinds)
        self.assertEqual(rows[0]["status"], "pending")
        body = self.layer.conn.execute("SELECT body FROM desk_result_outbox WHERE kind = 'result'").fetchone()["body"]
        self.assertIn("did not complete", body)
        self.assertIn("STATUS=failed", body)

        ondemand = enqueue_on_demand_case(self.layer, case_id)
        self.assertTrue(ondemand["ok"], ondemand)
        case_kinds = [
            row["kind"]
            for row in self.layer.conn.execute("SELECT kind FROM desk_result_outbox").fetchall()
        ]
        self.assertIn("case_ondemand", case_kinds)

    def test_hold_still_sends_result_and_case(self) -> None:
        _case_id, binding = self._open_desk("desk-hold-mail")
        result = self._apply(INTENT_HOLD, binding, gmail_message_id="ctrl-hold-mail")
        self.assertTrue(result["ok"], result)
        self.assertFalse(result.get("human_mail_deferred"))
        kinds = {row["kind"] for row in self.layer.conn.execute("SELECT kind FROM desk_result_outbox").fetchall()}
        self.assertEqual(kinds, {"result", "case"})

    def test_unknown_followup_is_not_suppressed(self) -> None:
        _case_id, binding = self._open_desk("desk-unknown-mail")
        self.assertTrue(self._apply(INTENT_APPROVE_SEND, binding, gmail_message_id="ctrl-unknown-mail")["ok"])
        timed_out = execute_desk_queued_sends(self.layer, MemorySendTransport(timeout=True))
        enqueue_send_followup(self.layer, timed_out[0])
        body = self.layer.conn.execute("SELECT body FROM desk_result_outbox WHERE kind = 'result'").fetchone()["body"]
        self.assertIn("unknown", body.lower())
        self.assertIn("STATUS=failed", body)

    def test_already_sent_queued_result_does_not_hide_failure(self) -> None:
        case_id, binding = self._open_desk("desk-legacy-mail")
        accepted = self._apply(INTENT_APPROVE_SEND, binding, gmail_message_id="ctrl-legacy-mail")
        self.assertTrue(accepted["ok"], accepted)
        from bt_intake_proof.desk_bridge import enqueue_control_deliveries, format_result_email

        queued_mail = format_result_email(accepted)
        self.layer.conn.execute(
            """
            INSERT INTO desk_result_outbox
                (control_gmail_id, nonce, kind, subject, body, status, created_at, sent_at)
            VALUES (?, ?, 'result', ?, ?, 'sent', '2026-09-12T17:20:00+00:00', '2026-09-12T17:20:01+00:00')
            """,
            ("ctrl-legacy-mail", accepted.get("nonce"), queued_mail["subject"], queued_mail["body"]),
        )
        self.layer.conn.execute(
            """
            INSERT INTO desk_result_outbox
                (control_gmail_id, nonce, kind, subject, body, status, created_at, sent_at)
            VALUES (?, ?, 'case', ?, ?, 'sent', '2026-09-12T17:20:00+00:00', '2026-09-12T17:20:01+00:00')
            """,
            ("ctrl-legacy-mail", accepted.get("nonce"), "CASE already sent", "old case"),
        )
        failed = execute_desk_queued_sends(self.layer, MemorySendTransport(fail=True))
        enqueue_send_followup(self.layer, failed[0])
        rows = [dict(row) for row in self.layer.conn.execute("SELECT kind, status FROM desk_result_outbox").fetchall()]
        kinds = {(row["kind"], row["status"]) for row in rows}
        self.assertIn(("result", "sent"), kinds)
        self.assertIn(("result_send", "pending"), kinds)
        self.assertNotIn(("case_send", "pending"), kinds)
        self.assertEqual(latest_action(self.layer, case_id)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
