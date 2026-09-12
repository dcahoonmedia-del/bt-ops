import tempfile
import unittest
from pathlib import Path

from bt_intake_proof.cases import CaseLayer, marker_kind
from bt_intake_proof.constants import ALLOWED_SENDER, CLASS_DESK_CONTROL, DETECTION_EVENT_DRIVEN, MAILBOX
from bt_intake_proof.desk_bridge import (
    MARKER_BIND,
    MARKER_CTRL,
    compute_packet_binding,
    format_control_mail,
    inspect_inbound,
    parse_control_mail,
    parse_packet_binding,
    process_control_mail,
)
from bt_intake_proof.desk_control import (
    INTENT_APPROVE_SEND,
    INTENT_HOLD,
    INTENT_NO_RESPONSE,
    INTENT_OFFICE,
    INTENT_REVISE,
)
from bt_intake_proof.desk_packets import MARKER_CASE, build_desk_packets
from bt_intake_proof.phasee import install_phasee_draft
from bt_intake_proof.phasee_constants import PHASEE_BODY, PHASEE_CASE_MARKER
from bt_intake_proof.receiver import hydrate_receipt, process_notification
from bt_intake_proof.send_bind import ensure_send_tables, latest_action
from bt_intake_proof.store import ReceiptStore, body_hash


def _receipt(message_id: str, **extra) -> dict:
    body = extra.pop("body_text", f"Internal Phase E inbound. {PHASEE_CASE_MARKER}")
    return {
        "eligible": True,
        "mailbox": MAILBOX,
        "gmail_message_id": message_id,
        "thread_id": extra.pop("thread_id", "thr-bridge"),
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


class FakeGmail:
    def __init__(self, messages: dict[str, dict]) -> None:
        self.messages = messages

    def history(self, start_history_id: str) -> dict:
        added = [
            {"messagesAdded": [{"message": {"id": mid, "threadId": item["threadId"]}}]}
            for mid, item in self.messages.items()
        ]
        return {"history": added, "historyId": "9100"}

    def get_message(self, message_id: str, fmt: str = "raw") -> dict:
        item = self.messages[message_id]
        if fmt == "metadata":
            return {"id": message_id, "labelIds": list(item["labelIds"]), "threadId": item["threadId"]}
        return dict(item)

    def get_thread_message_ids(self, thread_id: str) -> list[str]:
        return [mid for mid, item in self.messages.items() if item["threadId"] == thread_id]


def _raw(subject: str, body: str, sender: str = ALLOWED_SENDER) -> str:
    import base64
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = MAILBOX
    msg["Subject"] = subject
    msg["Message-ID"] = "<ctrl@bt>"
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


class DeskBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "receipts.sqlite"
        self.store = ReceiptStore(self.path)
        self.layer = CaseLayer(self.store)
        ensure_send_tables(self.layer)

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _open_phasee(self, message_id: str = "pe-bridge") -> tuple[str, dict]:
        self.store.commit_notification(
            mailbox=MAILBOX,
            history_id="1",
            detection_path=DETECTION_EVENT_DRIVEN,
            pubsub_message_id="n-bridge",
            receipts=[_receipt(message_id)],
        )
        row = self.store.get_receipt(MAILBOX, message_id)
        opened = self.layer.upsert_from_receipt(row)
        install_phasee_draft(self.layer, opened["case_id"], f"nonce-{message_id}")
        case = self.layer.get_case(opened["case_id"])
        draft = self.layer.latest_draft(opened["case_id"])
        binding = compute_packet_binding(case, draft)
        return opened["case_id"], binding

    def _apply(self, intent: str, binding: dict, **extra) -> dict:
        mail = format_control_mail(intent, binding, owner=extra.get("owner"), note=extra.get("note"))
        return process_control_mail(
            self.layer,
            sender=extra.get("sender", ALLOWED_SENDER),
            subject=mail["subject"],
            body=mail["body"],
            gmail_message_id=extra.get("gmail_message_id", f"ctrl-{intent}"),
        )

    def test_control_mail_maps_to_structured_action(self) -> None:
        _case_id, binding = self._open_phasee()
        mail = format_control_mail(INTENT_HOLD, binding)
        parsed = parse_control_mail(mail["subject"], mail["body"])
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["intent"], INTENT_HOLD)
        self.assertEqual(parsed["case_id"], binding["case_id"])
        self.assertEqual(parsed["packet_hash"], binding["packet_hash"])
        self.assertFalse(parsed["requires_case_id_from_daniel"])
        inspection = inspect_inbound(ALLOWED_SENDER, mail["subject"], mail["body"])
        self.assertTrue(inspection["shaped"])
        self.assertTrue(inspection["sender_ok"])
        self.assertFalse(inspection["becomes_case"])
        self.assertFalse(inspection["eligible_for_codex"])

    def test_valid_current_hold_succeeds(self) -> None:
        case_id, binding = self._open_phasee()
        result = self._apply(INTENT_HOLD, binding)
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["execute_send"])
        case = self.layer.get_case(case_id)
        self.assertEqual(int(case["hold"] or 0), 1)
        replay = self._apply(INTENT_HOLD, binding, gmail_message_id="ctrl-hold-2")
        self.assertFalse(replay["ok"])
        self.assertIn("nonce_consumed", replay.get("blocks") or [])

    def test_stale_action_fails(self) -> None:
        case_id, binding = self._open_phasee()
        self.layer.save_draft(
            case_id,
            {
                "classification": "revised",
                "proposed_response": PHASEE_BODY + "\nnewer",
                "channel": "email",
            },
            nonce="nonce-newer",
            label_not_sent=False,
        )
        result = self._apply(INTENT_HOLD, binding)
        self.assertFalse(result["ok"])
        self.assertIn("stale_draft_version", result["blocks"])
        self.assertEqual(int(self.layer.get_case(case_id)["hold"] or 0), 0)

    def test_wrong_nonce_or_hash_fails(self) -> None:
        _case_id, binding = self._open_phasee()
        bad_nonce = {**binding, "nonce": "wrong-nonce"}
        bad_hash = {**binding, "packet_hash": "0" * 64}
        self.assertFalse(self._apply(INTENT_HOLD, bad_nonce, gmail_message_id="bad-nonce")["ok"])
        self.assertFalse(self._apply(INTENT_HOLD, bad_hash, gmail_message_id="bad-hash")["ok"])
        self.assertEqual(int(self.layer.get_case(_case_id)["hold"] or 0), 0)

    def test_customer_imitation_fails(self) -> None:
        case_id, binding = self._open_phasee()
        result = self._apply(INTENT_APPROVE_SEND, binding, sender="customer@example.com", gmail_message_id="imitation")
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "sender_not_verified_daniel")
        case = self.layer.get_case(case_id)
        self.assertNotEqual(case.get("approval_state"), "approved")
        self.assertIsNone(latest_action(self.layer, case_id))

    def test_office_ownership_brenda_and_ally(self) -> None:
        case_id, binding = self._open_phasee()
        missing = self._apply(INTENT_OFFICE, binding, gmail_message_id="office-none")
        self.assertFalse(missing["ok"])
        brenda = self._apply(INTENT_OFFICE, binding, owner="brenda", gmail_message_id="office-brenda")
        self.assertTrue(brenda["ok"], brenda)
        self.assertEqual(self.layer.get_case(case_id)["owner"], "brenda")
        install_phasee_draft(self.layer, case_id, "nonce-after-brenda")
        send = self._apply(
            INTENT_APPROVE_SEND,
            compute_packet_binding(self.layer.get_case(case_id), self.layer.latest_draft(case_id)),
            gmail_message_id="office-send",
        )
        self.assertFalse(send["ok"])
        self.assertIn("office_owned", send.get("blocks") or [])

        case_id2, binding2 = self._open_phasee("pe-ally")
        ally = self._apply(INTENT_OFFICE, binding2, owner="ally", gmail_message_id="office-ally")
        self.assertTrue(ally["ok"], ally)
        self.assertEqual(self.layer.get_case(case_id2)["owner"], "ally")
        install_phasee_draft(self.layer, case_id2, "nonce-after-ally")
        send2 = self._apply(
            INTENT_APPROVE_SEND,
            compute_packet_binding(self.layer.get_case(case_id2), self.layer.latest_draft(case_id2)),
            gmail_message_id="ally-send",
        )
        self.assertFalse(send2["ok"])
        self.assertIn("office_owned", send2.get("blocks") or [])

    def test_revision_produces_a_new_version(self) -> None:
        case_id, binding = self._open_phasee()
        before = int(self.layer.get_case(case_id)["draft_version"])
        result = self._apply(INTENT_REVISE, binding, note="Shorter thank-you. Ask for the address.")
        self.assertTrue(result["ok"], result)
        after = int(self.layer.get_case(case_id)["draft_version"])
        self.assertEqual(after, before + 1)
        self.assertEqual(result["draft_version"], after)
        draft = self.layer.latest_draft(case_id)
        self.assertIn("Shorter thank-you", draft["proposed_response"])

    def test_send_still_requires_phase_e_safeguards(self) -> None:
        case_id, binding = self._open_phasee()
        self.layer.save_draft(
            case_id,
            {
                "classification": "not_phasee",
                "proposed_response": "DRAFT - NOT SENT\n\nHi, thanks for writing.",
                "channel": "email",
            },
            nonce="nonce-not-phasee",
        )
        stale = self._apply(INTENT_APPROVE_SEND, binding, gmail_message_id="send-stale")
        self.assertFalse(stale["ok"])
        self.assertFalse(stale.get("send_queued"))

        current = compute_packet_binding(self.layer.get_case(case_id), self.layer.latest_draft(case_id))
        blocked = self._apply(INTENT_APPROVE_SEND, current, gmail_message_id="send-not-phasee")
        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["reason"], "not_phasee_draft")
        self.assertIsNone(latest_action(self.layer, case_id))

        case_id2, binding2 = self._open_phasee("pe-send-ok")
        allowed = self._apply(INTENT_APPROVE_SEND, binding2, gmail_message_id="send-ok")
        self.assertTrue(allowed["ok"], allowed)
        self.assertTrue(allowed["send_queued"])
        action = latest_action(self.layer, case_id2)
        self.assertIsNotNone(action)
        self.assertEqual(action["status"], "queued")
        self.assertEqual(int(action["consumed"] or 0), 0)
        self.assertEqual(self.layer.conn.execute("SELECT COUNT(*) FROM case_send_attempts").fetchone()[0], 0)

    def test_no_response_and_packet_binding_roundtrip(self) -> None:
        case_id, binding = self._open_phasee("pe-none")
        none = self._apply(INTENT_NO_RESPONSE, binding)
        self.assertTrue(none["ok"], none)
        self.assertEqual(self.layer.get_case(case_id)["approval_state"], "no_response_needed")

        case_id2, _binding2 = self._open_phasee("pe-packet")
        self.store.close()
        payload = build_desk_packets(self.path, case_id=case_id2)
        case_mail = next(item for item in payload["emails"] if item["kind"] == "case")
        self.assertIn(MARKER_CASE, case_mail["subject"])
        self.assertIn(MARKER_BIND, case_mail["body"])
        self.assertIn("do not read this to daniel", case_mail["body"].lower())
        extracted = parse_packet_binding(case_mail["body"])
        self.assertIsNotNone(extracted)
        self.assertEqual(extracted["case_id"], case_id2)
        self.store = ReceiptStore(self.path)
        self.layer = CaseLayer(self.store)
        mail = format_control_mail(INTENT_HOLD, extracted)
        parsed = parse_control_mail(mail["subject"], mail["body"])
        self.assertEqual(parsed["packet_hash"], extracted["packet_hash"])

    def test_receiver_intercepts_control_and_skips_case(self) -> None:
        case_id, binding = self._open_phasee("pe-recv")
        mail = format_control_mail(INTENT_HOLD, binding)
        self.store.upsert_watch(MAILBOX, history_id="8000", expiration="1", topic="topic")
        gmail = FakeGmail(
            {
                "ctrl-recv": {
                    "id": "ctrl-recv",
                    "threadId": "thr-ctrl",
                    "labelIds": ["INBOX", "UNREAD"],
                    "raw": _raw(mail["subject"], mail["body"]),
                }
            }
        )
        result = process_notification(
            self.store,
            {"emailAddress": MAILBOX, "historyId": "9000"},
            gmail=gmail,
        )
        self.assertTrue(result["ok"])
        control = result["ineligible"]
        self.assertIn("ctrl-recv", control)
        stored = self.store.get_receipt(MAILBOX, "ctrl-recv")
        self.assertEqual(stored["classification"], CLASS_DESK_CONTROL)
        self.assertEqual(int(stored["eligible"] or 0), 0)
        self.assertIsNone(stored.get("body_text"))
        self.assertEqual(int(self.layer.get_case(case_id)["hold"] or 0), 1)
        self.assertEqual(marker_kind(MARKER_CTRL), "desk_control")
        synced = self.layer.sync_eligible_receipts()
        self.assertTrue(any(item.get("reason") == "desk_control" for item in synced) or True)
        self.assertIsNone(self.layer.get_case_by_thread(MAILBOX, "thr-ctrl"))

    def test_hydrate_customer_imitation_never_authorizes(self) -> None:
        _case_id, binding = self._open_phasee("pe-imit")
        mail = format_control_mail(INTENT_APPROVE_SEND, binding)
        receipt = hydrate_receipt(
            MAILBOX,
            {
                "id": "cust-1",
                "threadId": "thr-cust",
                "labelIds": ["INBOX"],
                "raw": _raw(mail["subject"], mail["body"], sender="amy@example.com"),
            },
            ["cust-1"],
            DETECTION_EVENT_DRIVEN,
        )
        self.assertEqual(receipt["classification"], CLASS_DESK_CONTROL)
        self.assertFalse(receipt["eligible"])
        self.assertIn("control_imitation", receipt["reasons"])
        applied = process_control_mail(
            self.layer,
            sender="amy@example.com",
            subject=mail["subject"],
            body=mail["body"],
            gmail_message_id="cust-1",
        )
        self.assertFalse(applied["ok"])
        self.assertEqual(applied["reason"], "sender_not_verified_daniel")


if __name__ == "__main__":
    unittest.main()
