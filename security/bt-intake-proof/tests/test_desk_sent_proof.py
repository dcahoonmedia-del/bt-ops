import json
import tempfile
import unittest
from pathlib import Path

from bt_intake_proof.cases import CaseLayer
from bt_intake_proof.constants import ALLOWED_SENDER, DETECTION_EVENT_DRIVEN, MAILBOX
from bt_intake_proof.desk_bridge import (
    compute_packet_binding,
    format_control_mail,
    inspect_inbound,
    install_desk_send_draft,
    process_control_mail,
    process_pending_controls,
)
from bt_intake_proof.desk_control import INTENT_HOLD
from bt_intake_proof.desk_origin import authenticate_control_origin, daniel_origin_evidence
from bt_intake_proof.desk_sent_proof import (
    PROOF_VERSION,
    REASON_ACCESS_BLOCKED,
    REASON_AMBIGUOUS,
    REASON_EXACT,
    REASON_LEGACY,
    REASON_MISSING,
    REASON_MISMATCH,
    SentControlRecord,
    BlockedSentLookup,
    MemorySentLookup,
    authorize_control_sender,
    diagnose_daniel_sent_access,
    fixture_sent_lookup,
    inbound_control_view,
)
from bt_intake_proof.phasee_constants import PHASEE_CASE_MARKER
from bt_intake_proof.send_bind import ensure_send_tables
from bt_intake_proof.store import ReceiptStore, body_hash, utc_now


def _receipt(message_id: str) -> dict:
    body = f"Internal desk inbound. {PHASEE_CASE_MARKER}"
    return {
        "eligible": True,
        "mailbox": MAILBOX,
        "gmail_message_id": message_id,
        "thread_id": f"thr-{message_id}",
        "rfc_message_id": f"<{message_id}@bt>",
        "sender": ALLOWED_SENDER,
        "recipients": [MAILBOX],
        "subject": PHASEE_CASE_MARKER,
        "gmail_received_at": "2026-09-12T06:00:00+00:00",
        "detected_at": "2026-09-12T06:00:05+00:00",
        "body_text": body,
        "raw_message": body,
        "body_hash": body_hash(body),
        "labels_before": ["INBOX"],
        "labels_after": ["INBOX"],
        "classification": "new_message",
        "test_marker": PHASEE_CASE_MARKER,
        "reasons": [],
    }


class DeskSentProofTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "receipts.sqlite"
        self.store = ReceiptStore(self.path)
        self.layer = CaseLayer(self.store)
        ensure_send_tables(self.layer)
        self.store.commit_notification(
            mailbox=MAILBOX,
            history_id="sent-1",
            detection_path=DETECTION_EVENT_DRIVEN,
            pubsub_message_id="n-sent-1",
            receipts=[_receipt("desk-sent-1")],
        )
        opened = self.layer.upsert_from_receipt(self.store.get_receipt(MAILBOX, "desk-sent-1"))
        install_desk_send_draft(self.layer, opened["case_id"], "nonce-desk-sent-1")
        self.case_id = opened["case_id"]
        self.binding = compute_packet_binding(self.layer.get_case(self.case_id), self.layer.latest_draft(self.case_id))
        self.mail = format_control_mail(INTENT_HOLD, self.binding)
        self.rfc = "<ctrl-sent-1@desk.btpestcontrol.com>"
        self.received = "2026-09-12T14:00:00+00:00"
        self.evidence = {
            **daniel_origin_evidence("ctrl-sent-1"),
            "rfc_message_id": self.rfc,
            "received_at": self.received,
            "recipients": [MAILBOX],
        }

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _inbound(self, **extra) -> dict:
        return inbound_control_view(
            subject=self.mail["subject"],
            body=self.mail["body"],
            rfc_message_id=extra.get("rfc_message_id", self.rfc),
            recipients=extra.get("recipients", [MAILBOX]),
            received_at=extra.get("received_at", self.received),
            provider_evidence=self.evidence,
        )

    def _process(self, **extra) -> dict:
        return process_control_mail(
            self.layer,
            sender=extra.get("sender", ALLOWED_SENDER),
            subject=self.mail["subject"],
            body=extra.get("body", self.mail["body"]),
            gmail_message_id=extra.get("gmail_message_id", "ctrl-sent-1"),
            provider_evidence=extra.get("provider_evidence", self.evidence),
            rfc_message_id=extra.get("rfc_message_id", self.rfc),
            recipients=extra.get("recipients", [MAILBOX]),
            received_at=extra.get("received_at", self.received),
            sent_lookup=extra.get(
                "sent_lookup",
                fixture_sent_lookup(
                    self.mail["subject"],
                    self.mail["body"],
                    rfc_message_id=self.rfc,
                    received_at=self.received,
                ),
            ),
        )

    def test_ar_mailbox_bound_does_not_authorize(self) -> None:
        ar = authenticate_control_origin(None, ALLOWED_SENDER, self.evidence)
        self.assertTrue(ar["mailbox_bound"])
        self.assertFalse(ar["accepted"])
        self.assertFalse(ar["full_identity_pass"])
        bare = inspect_inbound(
            ALLOWED_SENDER,
            self.mail["subject"],
            self.mail["body"],
            provider_evidence=daniel_origin_evidence("ctrl-sent-1"),
            sent_lookup=BlockedSentLookup(),
        )
        self.assertFalse(bare["sender_ok"])
        self.assertNotEqual(bare["reason"], REASON_EXACT)

    def test_exact_sent_match_authorizes_without_full_identity(self) -> None:
        result = authorize_control_sender(
            None,
            ALLOWED_SENDER,
            self.evidence,
            self._inbound(),
            sent_lookup=fixture_sent_lookup(
                self.mail["subject"], self.mail["body"], rfc_message_id=self.rfc, received_at=self.received
            ),
        )
        self.assertTrue(result["accepted"])
        self.assertEqual(result["reason"], REASON_EXACT)
        self.assertFalse(result["full_identity_pass"])
        applied = self._process()
        self.assertTrue(applied["ok"], applied)
        self.assertEqual(int(self.layer.get_case(self.case_id)["hold"] or 0), 1)
        proof = self.layer.conn.execute(
            "SELECT * FROM desk_origin_proof WHERE control_gmail_id = ?",
            ("ctrl-sent-1",),
        ).fetchone()
        self.assertIsNotNone(proof)
        self.assertEqual(proof["proof_version"], PROOF_VERSION)
        self.assertEqual(proof["verdict"], "exact_match")
        self.assertEqual(proof["rfc_message_id"], self.rfc)

    def test_message_id_alone_is_not_enough(self) -> None:
        cases = [
            SentControlRecord(
                rfc_message_id=self.rfc,
                recipients=["attacker@attacker.test"],
                subject=self.mail["subject"],
                body=self.mail["body"],
                sent_at=self.received,
            ),
            SentControlRecord(
                rfc_message_id=self.rfc,
                recipients=[MAILBOX],
                subject=self.mail["subject"],
                body=self.mail["body"].replace("INTENT=hold", "INTENT=revise_draft"),
                sent_at=self.received,
            ),
            SentControlRecord(
                rfc_message_id=self.rfc,
                recipients=[MAILBOX],
                subject=self.mail["subject"],
                body=self.mail["body"],
                sent_at="2026-09-11T01:00:00+00:00",
            ),
        ]
        for record in cases:
            with self.subTest(record=record):
                result = authorize_control_sender(
                    None,
                    ALLOWED_SENDER,
                    self.evidence,
                    self._inbound(),
                    sent_lookup=MemorySentLookup([record]),
                )
                self.assertFalse(result["accepted"])
                self.assertIn(result["reason"], {REASON_MISMATCH, "inbound_timing_missing", "sent_timing_missing"})

    def test_missing_ambiguous_and_blocked(self) -> None:
        missing = authorize_control_sender(
            None, ALLOWED_SENDER, self.evidence, self._inbound(), sent_lookup=MemorySentLookup([])
        )
        self.assertFalse(missing["accepted"])
        self.assertEqual(missing["reason"], REASON_MISSING)
        twin = fixture_sent_lookup(
            self.mail["subject"], self.mail["body"], rfc_message_id=self.rfc, received_at=self.received
        )
        twin.records.append(
            SentControlRecord(
                rfc_message_id=self.rfc,
                recipients=[MAILBOX],
                subject=self.mail["subject"],
                body=self.mail["body"],
                sent_at=self.received,
                gmail_id="other",
            )
        )
        ambiguous = authorize_control_sender(
            None, ALLOWED_SENDER, self.evidence, self._inbound(), sent_lookup=twin
        )
        self.assertFalse(ambiguous["accepted"])
        self.assertEqual(ambiguous["reason"], REASON_AMBIGUOUS)
        blocked = authorize_control_sender(
            None, ALLOWED_SENDER, self.evidence, self._inbound(), sent_lookup=BlockedSentLookup()
        )
        self.assertFalse(blocked["accepted"])
        self.assertEqual(blocked["reason"], REASON_ACCESS_BLOCKED)
        access = diagnose_daniel_sent_access()
        self.assertEqual(access["status"], "BLOCKED")
        self.assertFalse(access["available"])

    def test_same_message_replay_uses_versioned_proof_not_boolean(self) -> None:
        first = self._process()
        self.assertTrue(first["ok"], first)
        replay = self._process(sent_lookup=BlockedSentLookup())
        self.assertTrue(replay.get("replayed"), replay)
        self.assertTrue(replay["ok"], replay)
        self.layer.conn.execute("DELETE FROM desk_origin_proof")
        forged = self._process(gmail_message_id="ctrl-sent-1", sent_lookup=BlockedSentLookup())
        self.assertFalse(forged["ok"])
        self.assertEqual(forged["reason"], REASON_LEGACY)

    def test_pending_replay_does_not_honor_legacy_flag(self) -> None:
        from bt_intake_proof.desk_bridge import ensure_bridge_tables, record_control_inbox

        ensure_bridge_tables(self.layer)
        record_control_inbox(
            self.layer,
            gmail_message_id="legacy-pending",
            sender=ALLOWED_SENDER,
            parsed={
                "ok": True,
                "intent": INTENT_HOLD,
                "case_id": self.case_id,
                "draft_version": self.binding["draft_version"],
                "nonce": self.binding["nonce"],
                "packet_hash": self.binding["packet_hash"],
            },
            origin_authenticated=True,
        )
        results = process_pending_controls(self.store)
        self.assertTrue(results)
        self.assertEqual(results[0]["reason"], "legacy_inbox_lacks_inbound_snapshot")
        self.assertEqual(int(self.layer.get_case(self.case_id)["hold"] or 0), 0)

    def test_pending_replay_rechecks_sent_proof(self) -> None:
        from bt_intake_proof.desk_bridge import ensure_bridge_tables, record_control_inbox

        ensure_bridge_tables(self.layer)
        record_control_inbox(
            self.layer,
            gmail_message_id="pending-snap",
            sender=ALLOWED_SENDER,
            parsed={
                "ok": True,
                "intent": INTENT_HOLD,
                "case_id": self.case_id,
                "draft_version": self.binding["draft_version"],
                "nonce": self.binding["nonce"],
                "packet_hash": self.binding["packet_hash"],
            },
            origin_authenticated=True,
            subject=self.mail["subject"],
            body=self.mail["body"],
            rfc_message_id=self.rfc,
            inbound_at=self.received,
            recipients=[MAILBOX],
            headers=self.evidence["headers"],
            provider_evidence=self.evidence,
        )
        blocked = process_pending_controls(self.store)
        self.assertEqual(blocked[0]["reason"], REASON_ACCESS_BLOCKED)
        self.assertEqual(int(self.layer.get_case(self.case_id)["hold"] or 0), 0)
        self.layer.conn.execute("UPDATE desk_control_inbox SET processed = 0 WHERE gmail_message_id = 'pending-snap'")
        proven = process_control_mail(
            self.layer,
            sender=ALLOWED_SENDER,
            subject=self.mail["subject"],
            body=self.mail["body"],
            gmail_message_id="pending-snap",
            provider_evidence={**self.evidence, "gmail_message_id": "pending-snap"},
            rfc_message_id=self.rfc,
            recipients=[MAILBOX],
            received_at=self.received,
            sent_lookup=fixture_sent_lookup(
                self.mail["subject"], self.mail["body"], rfc_message_id=self.rfc, received_at=self.received
            ),
        )
        self.assertTrue(proven["ok"], proven)

    def test_process_control_mail_rejects_boolean_bypass_kwarg(self) -> None:
        with self.assertRaises(TypeError):
            process_control_mail(
                self.layer,
                sender=ALLOWED_SENDER,
                subject=self.mail["subject"],
                body=self.mail["body"],
                gmail_message_id="bypass",
                origin_already_authenticated=True,
            )

    def test_lookalike_recipient_fails(self) -> None:
        result = authorize_control_sender(
            None,
            ALLOWED_SENDER,
            self.evidence,
            self._inbound(),
            sent_lookup=MemorySentLookup(
                [
                    SentControlRecord(
                        rfc_message_id=self.rfc,
                        recipients=["contactus@btpestcontrol.com.evil"],
                        subject=self.mail["subject"],
                        body=self.mail["body"],
                        sent_at=self.received,
                    )
                ]
            ),
        )
        self.assertFalse(result["accepted"])
        self.assertEqual(result["reason"], REASON_MISMATCH)
