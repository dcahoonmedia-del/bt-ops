import tempfile
import unittest
from pathlib import Path

from bt_intake_proof.cases import CaseLayer
from bt_intake_proof.constants import (
    ALLOWED_SENDER,
    DETECTION_EVENT_DRIVEN,
    LEAD_DESK_PLUS_MAILBOX,
    MAILBOX,
    TRANSPORT_CONTACTUS,
    TRANSPORT_PLUS,
)
from bt_intake_proof.desk_bridge import (
    compute_packet_binding,
    format_control_mail,
    inspect_inbound,
    inspect_plus_inbound,
    process_control_mail,
    process_plus_control_mail,
)
from bt_intake_proof.desk_control import INTENT_HOLD, INTENT_REVISE
from bt_intake_proof.desk_origin import daniel_origin_evidence
from bt_intake_proof.desk_plus_proof import (
    FETCHED_VIA_DANIEL_PLUS,
    FETCHED_VIA_FIXTURE_PLUS,
    REASON_PLUS_FETCH,
    REASON_PLUS_FROM,
    REASON_PLUS_OK,
    REASON_PLUS_SENT,
    REASON_PLUS_TO,
    authorize_plus_address_control,
    plus_control_evidence,
)
from bt_intake_proof.desk_sent_proof import fixture_sent_lookup, inbound_control_view
from bt_intake_proof.phasee_constants import PHASEE_CASE_MARKER
from bt_intake_proof.send_bind import ensure_send_tables, latest_action
from bt_intake_proof.store import ReceiptStore, body_hash


def _receipt(message_id: str) -> dict:
    body = f"Internal plus-path inbound. {PHASEE_CASE_MARKER}"
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


class DeskPlusControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "receipts.sqlite"
        self.store = ReceiptStore(self.path)
        self.layer = CaseLayer(self.store)
        ensure_send_tables(self.layer)
        self.store.commit_notification(
            mailbox=MAILBOX,
            history_id="plus-1",
            detection_path=DETECTION_EVENT_DRIVEN,
            pubsub_message_id="n-plus-1",
            receipts=[_receipt("plus-in-1")],
        )
        opened = self.layer.upsert_from_receipt(self.store.get_receipt(MAILBOX, "plus-in-1"))
        self.layer.save_draft(
            opened["case_id"],
            {
                "classification": "internal_plus_draft_save",
                "known_facts": [],
                "missing_info": [],
                "recommended_next_step": "Save only",
                "proposed_response": "DRAFT - NOT SENT\n\nThanks for writing. Please share the address.",
                "channel": "email",
                "judgment_needed": "Revise only",
                "reasoning_summary": "Plus-address draft-save fixture",
            },
            nonce="nonce-plus-1",
            label_not_sent=True,
        )
        self.case_id = opened["case_id"]
        self.binding = compute_packet_binding(self.layer.get_case(self.case_id), self.layer.latest_draft(self.case_id))
        self.mail = format_control_mail(
            INTENT_REVISE,
            self.binding,
            note="DRAFT - NOT SENT\n\nInternal plus-address draft-save test. No customer send.",
            transport=TRANSPORT_PLUS,
        )
        self.rfc = "<plus-ctrl-1@desk.btpestcontrol.com>"
        self.received = "2026-09-12T21:00:00+00:00"
        self.headers = [
            ("From", f"Daniel Cahoon <{ALLOWED_SENDER}>"),
            ("To", LEAD_DESK_PLUS_MAILBOX),
        ]
        self.evidence = plus_control_evidence(
            "plus-ctrl-1",
            headers=self.headers,
            rfc_message_id=self.rfc,
            received_at=self.received,
            recipients=[LEAD_DESK_PLUS_MAILBOX],
        )

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _inbound(self, **extra) -> dict:
        return inbound_control_view(
            subject=extra.get("subject", self.mail["subject"]),
            body=extra.get("body", self.mail["body"]),
            rfc_message_id=extra.get("rfc_message_id", self.rfc),
            recipients=extra.get("recipients", [LEAD_DESK_PLUS_MAILBOX]),
            received_at=extra.get("received_at", self.received),
            provider_evidence=extra.get("provider_evidence", self.evidence),
            headers=extra.get("headers", self.headers),
        )

    def _process(self, **extra) -> dict:
        return process_control_mail(
            self.layer,
            sender=extra.get("sender", ALLOWED_SENDER),
            subject=extra.get("subject", self.mail["subject"]),
            body=extra.get("body", self.mail["body"]),
            gmail_message_id=extra.get("gmail_message_id", "plus-ctrl-1"),
            provider_evidence=extra.get("provider_evidence", self.evidence),
            headers=extra.get("headers", self.headers),
            rfc_message_id=extra.get("rfc_message_id", self.rfc),
            recipients=extra.get("recipients", [LEAD_DESK_PLUS_MAILBOX]),
            received_at=extra.get("received_at", self.received),
            transport=extra.get("transport", TRANSPORT_PLUS),
        )

    def test_format_defaults_to_contactus_and_plus_is_explicit(self) -> None:
        contactus = format_control_mail(INTENT_HOLD, self.binding)
        self.assertEqual(contactus["to"], MAILBOX)
        self.assertEqual(contactus["transport"], TRANSPORT_CONTACTUS)
        self.assertEqual(self.mail["to"], LEAD_DESK_PLUS_MAILBOX)
        self.assertEqual(self.mail["from"], ALLOWED_SENDER)
        self.assertEqual(self.mail["transport"], TRANSPORT_PLUS)

    def test_plus_sent_from_to_authorizes_without_ar(self) -> None:
        origin = authorize_plus_address_control(ALLOWED_SENDER, self.evidence, self._inbound())
        self.assertTrue(origin["accepted"])
        self.assertEqual(origin["reason"], REASON_PLUS_OK)
        self.assertFalse(origin["requires_authentication_results"])
        self.assertFalse(origin["mailbox_bound"])
        self.assertFalse(origin["full_identity_pass"])
        proven = inspect_plus_inbound(
            ALLOWED_SENDER,
            self.mail["subject"],
            self.mail["body"],
            provider_evidence=self.evidence,
            headers=self.headers,
            rfc_message_id=self.rfc,
            recipients=[LEAD_DESK_PLUS_MAILBOX],
            received_at=self.received,
        )
        self.assertTrue(proven["sender_ok"], proven)
        self.assertEqual(proven["transport"], TRANSPORT_PLUS)

    def test_plus_revise_saves_exactly_one_version_and_no_contactus_outbox(self) -> None:
        before = int(self.layer.get_case(self.case_id)["draft_version"])
        result = self._process()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["applied"], "revise_draft")
        self.assertEqual(result["transport"], TRANSPORT_PLUS)
        self.assertFalse(result["execute_send"])
        self.assertFalse(result["send_queued"])
        after = int(self.layer.get_case(self.case_id)["draft_version"])
        self.assertEqual(after, before + 1)
        self.assertEqual(result["draft_version"], after)
        draft = self.layer.latest_draft(self.case_id)
        self.assertIn("Internal plus-address draft-save test", draft["proposed_response"])
        self.assertIsNone(latest_action(self.layer, self.case_id))
        outbox = self.layer.conn.execute("SELECT kind, status FROM desk_result_outbox").fetchall()
        self.assertEqual(list(outbox), [])
        proof = self.layer.conn.execute(
            "SELECT recipient FROM desk_origin_proof WHERE control_gmail_id = ?",
            ("plus-ctrl-1",),
        ).fetchone()
        self.assertEqual(proof["recipient"], LEAD_DESK_PLUS_MAILBOX)
        replay = self._process()
        self.assertTrue(replay.get("replayed"))
        self.assertEqual(int(self.layer.get_case(self.case_id)["draft_version"]), after)

    def test_duplicate_nonce_is_rejected(self) -> None:
        first = self._process()
        self.assertTrue(first["ok"], first)
        second = self._process(gmail_message_id="plus-ctrl-2")
        self.assertFalse(second["ok"])
        self.assertIn("nonce_consumed", second.get("blocks") or [])
        self.assertEqual(int(self.layer.get_case(self.case_id)["draft_version"]), first["draft_version"])

    def test_stale_packet_hash_is_rejected(self) -> None:
        stale = format_control_mail(
            INTENT_REVISE,
            {**self.binding, "packet_hash": "ab" * 32},
            note="should not save",
            transport=TRANSPORT_PLUS,
        )
        result = self._process(subject=stale["subject"], body=stale["body"], gmail_message_id="plus-stale")
        self.assertFalse(result["ok"])
        self.assertIn("packet_hash_invalid", result.get("blocks") or [])
        self.assertEqual(int(self.layer.latest_draft(self.case_id)["version"]), 1)

    def test_missing_sent_label_is_rejected(self) -> None:
        evidence = plus_control_evidence(
            "plus-nosent",
            labels=["INBOX"],
            headers=self.headers,
            rfc_message_id="<plus-nosent@desk.btpestcontrol.com>",
            received_at=self.received,
            recipients=[LEAD_DESK_PLUS_MAILBOX],
        )
        origin = authorize_plus_address_control(
            ALLOWED_SENDER,
            evidence,
            self._inbound(provider_evidence=evidence, rfc_message_id="<plus-nosent@desk.btpestcontrol.com>"),
        )
        self.assertFalse(origin["accepted"])
        self.assertEqual(origin["reason"], REASON_PLUS_SENT)

    def test_spoofed_from_is_rejected(self) -> None:
        headers = [("From", "Amy <amy@example.com>"), ("To", LEAD_DESK_PLUS_MAILBOX)]
        evidence = plus_control_evidence(
            "plus-spoof",
            headers=headers,
            rfc_message_id="<plus-spoof@desk.btpestcontrol.com>",
            received_at=self.received,
            recipients=[LEAD_DESK_PLUS_MAILBOX],
        )
        origin = authorize_plus_address_control(
            "amy@example.com",
            evidence,
            self._inbound(provider_evidence=evidence, headers=headers),
        )
        self.assertFalse(origin["accepted"])
        self.assertEqual(origin["reason"], REASON_PLUS_FROM)

    def test_contactus_recipient_cannot_use_plus_path(self) -> None:
        headers = [("From", ALLOWED_SENDER), ("To", MAILBOX)]
        evidence = plus_control_evidence(
            "plus-wrong-to",
            headers=headers,
            rfc_message_id="<plus-wrong-to@desk.btpestcontrol.com>",
            received_at=self.received,
            recipients=[MAILBOX],
        )
        origin = authorize_plus_address_control(
            ALLOWED_SENDER,
            evidence,
            self._inbound(provider_evidence=evidence, headers=headers, recipients=[MAILBOX]),
        )
        self.assertFalse(origin["accepted"])
        self.assertEqual(origin["reason"], REASON_PLUS_TO)

    def test_contactus_fetch_cannot_satisfy_plus_path(self) -> None:
        evidence = {
            **daniel_origin_evidence("plus-ar"),
            "authenticated_mailbox": ALLOWED_SENDER,
            "labels": ["SENT"],
            "rfc_message_id": self.rfc,
            "received_at": self.received,
            "recipients": [LEAD_DESK_PLUS_MAILBOX],
            "headers": self.headers,
        }
        origin = authorize_plus_address_control(ALLOWED_SENDER, evidence, self._inbound(provider_evidence=evidence))
        self.assertFalse(origin["accepted"])
        self.assertEqual(origin["reason"], REASON_PLUS_FETCH)

    def test_customer_copy_does_not_authorize_either_path(self) -> None:
        quoted = "Thanks.\n\n> " + "\n> ".join(self.mail["body"].splitlines())
        plus = inspect_plus_inbound(
            "amy@example.com",
            "Re: service",
            quoted,
            provider_evidence=plus_control_evidence(
                "cust-copy",
                mailbox="amy@example.com",
                headers=[("From", "amy@example.com"), ("To", LEAD_DESK_PLUS_MAILBOX)],
            ),
            recipients=[LEAD_DESK_PLUS_MAILBOX],
            rfc_message_id="<cust-copy@example.com>",
            received_at=self.received,
        )
        self.assertTrue(plus["shaped"])
        self.assertFalse(plus["sender_ok"])
        contactus = inspect_inbound(
            "amy@example.com",
            self.mail["subject"],
            self.mail["body"],
            provider_evidence=daniel_origin_evidence("cust-contactus"),
            recipients=[MAILBOX],
        )
        self.assertTrue(contactus["shaped"])
        self.assertFalse(contactus["sender_ok"])

    def test_plus_mail_does_not_authorize_contactus_path(self) -> None:
        bare = inspect_inbound(
            ALLOWED_SENDER,
            self.mail["subject"],
            self.mail["body"],
            provider_evidence={
                **daniel_origin_evidence("plus-on-contactus"),
                "rfc_message_id": self.rfc,
                "received_at": self.received,
                "recipients": [LEAD_DESK_PLUS_MAILBOX],
            },
            rfc_message_id=self.rfc,
            recipients=[LEAD_DESK_PLUS_MAILBOX],
            received_at=self.received,
            sent_lookup=fixture_sent_lookup(
                self.mail["subject"], self.mail["body"], rfc_message_id=self.rfc, received_at=self.received
            ),
        )
        self.assertFalse(bare["sender_ok"])

    def test_contactus_path_still_authorizes_with_ar_and_sent(self) -> None:
        mail = format_control_mail(INTENT_HOLD, self.binding)
        rfc = "<contactus-still@desk.btpestcontrol.com>"
        received = self.received
        evidence = {
            **daniel_origin_evidence("contactus-still"),
            "rfc_message_id": rfc,
            "received_at": received,
            "recipients": [MAILBOX],
        }
        result = process_control_mail(
            self.layer,
            sender=ALLOWED_SENDER,
            subject=mail["subject"],
            body=mail["body"],
            gmail_message_id="contactus-still",
            provider_evidence=evidence,
            rfc_message_id=rfc,
            recipients=[MAILBOX],
            received_at=received,
            sent_lookup=fixture_sent_lookup(mail["subject"], mail["body"], rfc_message_id=rfc, received_at=received),
            transport=TRANSPORT_CONTACTUS,
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result.get("transport"), TRANSPORT_CONTACTUS)
        self.assertEqual(int(self.layer.get_case(self.case_id)["hold"] or 0), 1)
        proof = self.layer.conn.execute(
            "SELECT recipient FROM desk_origin_proof WHERE control_gmail_id = ?",
            ("contactus-still",),
        ).fetchone()
        self.assertEqual(proof["recipient"], MAILBOX)

    def test_process_plus_helper_uses_fetched_daniel_evidence(self) -> None:
        fetched = {
            "ok": True,
            "sender": ALLOWED_SENDER,
            "subject": self.mail["subject"],
            "body": self.mail["body"],
            "rfc_message_id": self.rfc,
            "recipients": [LEAD_DESK_PLUS_MAILBOX],
            "received_at": self.received,
            "gmail_message_id": "plus-helper-1",
            "evidence": plus_control_evidence(
                "plus-helper-1",
                fetched_via=FETCHED_VIA_DANIEL_PLUS,
                headers=self.headers,
                rfc_message_id=self.rfc,
                received_at=self.received,
                recipients=[LEAD_DESK_PLUS_MAILBOX],
            ),
        }
        before = int(self.layer.get_case(self.case_id)["draft_version"])
        result = process_plus_control_mail(self.layer, gmail_message_id="plus-helper-1", fetched=fetched)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["applied"], "revise_draft")
        self.assertEqual(int(self.layer.get_case(self.case_id)["draft_version"]), before + 1)
        self.assertEqual(
            list(self.layer.conn.execute("SELECT kind FROM desk_result_outbox").fetchall()),
            [],
        )


if __name__ == "__main__":
    unittest.main()
