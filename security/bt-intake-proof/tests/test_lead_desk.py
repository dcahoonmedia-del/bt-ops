import json
import tempfile
import unittest
from pathlib import Path

from bt_intake_proof.bounded_send import MemorySendTransport, execute_action
from bt_intake_proof.case_manager import draft_pending_cases
from bt_intake_proof.cases import (
    DECISION_APPROVE,
    MARKER_DESK,
    CaseLayer,
    marker_kind,
    parse_decision,
)
from bt_intake_proof.constants import ALLOWED_SENDER, CLASS_NEW, DETECTION_EVENT_DRIVEN, MAILBOX
from bt_intake_proof.desk_bridge import ensure_bridge_tables
from bt_intake_proof.desk_packets import (
    MARKER_CASE,
    MARKER_HEALTH,
    MARKER_QUEUE,
    build_desk_packets,
)
from bt_intake_proof.lead_desk import LeadDesk, db_fingerprint
from bt_intake_proof.phasee_constants import PHASEE_BODY, PHASEE_CASE_MARKER, PHASEE_SEND_MARKER, PHASEE_SUBJECT, PHASEE_TO
from bt_intake_proof.send_bind import ensure_send_tables, queue_phasee_send
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
        "gmail_received_at": extra.pop("gmail_received_at", "2026-09-12T06:00:00+00:00"),
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


class LeadDeskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "receipts.sqlite"
        self.store = ReceiptStore(self.path)
        self.layer = CaseLayer(self.store)
        ensure_send_tables(self.layer)
        ensure_bridge_tables(self.layer)

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _approved_sent_case(self) -> str:
        self.store.commit_notification(
            mailbox=MAILBOX,
            history_id="1",
            detection_path=DETECTION_EVENT_DRIVEN,
            pubsub_message_id="n1",
            receipts=[_receipt("pe1")],
        )
        row = self.store.get_receipt(MAILBOX, "pe1")
        opened = self.layer.upsert_from_receipt(row)
        draft_pending_cases(self.store)
        self.layer.apply_decision(opened["case_id"], DECISION_APPROVE, draft_version=1, actor="daniel@btpestcontrol.com")
        queued = queue_phasee_send(self.layer, opened["case_id"])
        sent = execute_action(self.layer, queued["action"]["id"], MemorySendTransport())
        outbound = {
            "id": sent["provider_message_id"],
            "from": MAILBOX,
            "to": [PHASEE_TO],
            "cc": [],
            "bcc": [],
            "subject": PHASEE_SUBJECT,
            "body": PHASEE_BODY,
            "thread_id": queued["action"]["thread_id"],
            "label_ids": ["SENT"],
        }
        verify_sent(self.layer, queued["action"]["id"], MemoryVerifyTransport(sent=[outbound]))
        verify_recipient(
            self.layer,
            queued["action"]["id"],
            MemoryVerifyTransport(inbox=[{**outbound, "id": "inbox-1", "label_ids": ["INBOX", "UNREAD"]}]),
        )
        return opened["case_id"]

    def test_readonly_list_get_health_do_not_mutate(self) -> None:
        case_id = self._approved_sent_case()
        self.store.close()
        before = db_fingerprint(self.path)
        desk = LeadDesk(self.path, service_probe=lambda: {"observed": True, "active": True, "summary": "fixture receiver active"})
        listed = desk.list_cases()
        detail = desk.get_case(case_id)
        health = desk.get_health()
        desk.close()
        after = db_fingerprint(self.path)
        self.assertEqual(before["sha256"], after["sha256"])
        self.assertEqual(before["counts"], after["counts"])
        self.assertEqual(listed["count"], 1)
        row = listed["cases"][0]
        self.assertEqual(row["case_id"], case_id)
        self.assertEqual(row["contact_name"], "Daniel Cahoon (internal)")
        self.assertTrue(row["draft_exists"])
        self.assertFalse(row["waiting_on_daniel"])
        self.assertNotIn("nonce", json.dumps(detail))
        self.assertEqual(detail["send"]["status"], "recipient_receipt_verified")
        self.assertIn("untrusted_content", detail["latest_inbound"]["body"]["kind"])
        self.assertIn(health["overall"], {"ok", "degraded", "unhealthy"})
        self.assertNotEqual(health["overall"], "healthy")

    def test_desk_packets_answer_iphone_questions_without_approval_markers(self) -> None:
        case_id = self._approved_sent_case()
        self.store.close()
        before = db_fingerprint(self.path)
        payload = build_desk_packets(self.path, case_id=case_id)
        after = db_fingerprint(self.path)
        self.assertEqual(before["sha256"], after["sha256"])
        kinds = {item["kind"]: item for item in payload["emails"]}
        self.assertEqual(set(kinds), {"queue", "case", "health"})
        control = payload.get("control") or {}
        self.assertEqual(len((control.get("binding") or {}).get("packet_hash") or ""), 64)
        self.assertTrue(control.get("generate_only"))
        self.assertIn(MARKER_QUEUE, kinds["queue"]["subject"])
        self.assertIn(MARKER_CASE, kinds["case"]["subject"])
        self.assertIn(MARKER_HEALTH, kinds["health"]["subject"])
        self.assertEqual(kinds["queue"]["to"], "daniel@btpestcontrol.com")
        self.assertEqual(kinds["queue"]["cc"], "")
        self.assertIn(case_id, kinds["queue"]["body"])
        self.assertIn("Latest lead", kinds["queue"]["body"])
        self.assertIn("What came in?", kinds["queue"]["body"])
        self.assertIn(PHASEE_SEND_MARKER, kinds["case"]["body"])
        self.assertIn("recipient_receipt_verified", kinds["case"]["body"])
        self.assertIn("Did the message actually send?", kinds["case"]["body"])
        self.assertIn("Is intake healthy?", kinds["health"]["body"])
        self.assertIn("A running process alone is not enough", kinds["health"]["body"])
        blob = "\n".join(item["body"] for item in payload["emails"])
        self.assertNotIn("BT-INTAKE-PROOF-CASE-APPROVE", blob)
        self.assertNotIn("BT-INTAKE-PROOF-CASE-CHANGES", blob)
        self.assertIsNone(parse_decision(kinds["case"]["subject"], kinds["case"]["body"]))

    def test_desk_packet_does_not_open_or_approve_a_case(self) -> None:
        self.assertEqual(marker_kind(MARKER_QUEUE), "desk_packet")
        self.store.commit_notification(
            mailbox=MAILBOX,
            history_id="2",
            detection_path=DETECTION_EVENT_DRIVEN,
            pubsub_message_id="n2",
            receipts=[
                _receipt(
                    "desk1",
                    subject=f"{MARKER_QUEUE} attention queue",
                    test_marker=MARKER_QUEUE,
                    body_text=f"{MARKER_DESK}QUEUE-E9A8 read-only desk packet",
                )
            ],
        )
        results = self.layer.sync_eligible_receipts()
        self.assertTrue(any(item.get("reason") == "desk_packet" for item in results))
        self.assertIsNone(self.layer.get_case("BTC-contactus-thr-phasee"))
        self.assertEqual(self.layer.conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0], 0)
        self.assertEqual(self.layer.conn.execute("SELECT COUNT(*) FROM case_decisions").fetchone()[0], 0)

    def test_hold_and_office_attention_is_not_waiting_on_daniel(self) -> None:
        marker = "BT-INTAKE-PROOF-CASEMGR-ATTN-E9A8"
        self.store.commit_notification(
            mailbox=MAILBOX,
            history_id="attn",
            detection_path=DETECTION_EVENT_DRIVEN,
            pubsub_message_id="n-attn",
            receipts=[
                _receipt(
                    "attn1",
                    thread_id="thr-attn",
                    subject=marker,
                    test_marker=marker,
                    body_text=f"Internal inquiry. {marker}",
                    sender=ALLOWED_SENDER,
                )
            ],
        )
        row = self.store.get_receipt(MAILBOX, "attn1")
        opened = self.layer.upsert_from_receipt(row)
        self.layer.save_draft(
            opened["case_id"],
            {
                "classification": "new_customer_lead",
                "known_facts": ["test"],
                "missing_info": [],
                "recommended_next_step": "review",
                "proposed_response": "DRAFT - NOT SENT\n\nThanks.",
                "channel": "email",
            },
            "nonce-attn",
        )
        desk = LeadDesk(self.path, service_probe=lambda: {"observed": False, "active": None, "summary": "fixture"})
        waiting = desk.get_case(opened["case_id"])
        self.assertTrue(waiting["waiting_on_daniel"])
        self.assertEqual(waiting["attention_reason"], "Draft is waiting on Daniel.")
        desk.close()

        self.layer.conn.execute("UPDATE cases SET hold = 1, next_action = 'hold' WHERE case_id = ?", (opened["case_id"],))
        desk = LeadDesk(self.path, service_probe=lambda: {"observed": False, "active": None, "summary": "fixture"})
        held = desk.get_case(opened["case_id"])
        health_held = desk.get_health()
        self.assertFalse(held["waiting_on_daniel"])
        self.assertEqual(held["attention_reason"], "Held. Nothing will send.")
        self.assertEqual(held["owner"], "office")
        self.assertEqual(health_held["backlog"]["waiting_on_daniel"], 0)
        desk.close()

        self.layer.conn.execute(
            "UPDATE cases SET hold = 0, owner = 'brenda', next_action = 'office_owned' WHERE case_id = ?",
            (opened["case_id"],),
        )
        desk = LeadDesk(self.path, service_probe=lambda: {"observed": False, "active": None, "summary": "fixture"})
        brenda = desk.get_case(opened["case_id"])
        queued = desk.list_cases()["cases"][0]
        self.assertFalse(brenda["waiting_on_daniel"])
        self.assertEqual(brenda["attention_reason"], "Brenda owns this. Do not send a competing reply.")
        self.assertEqual(brenda["owner"], "brenda")
        self.assertEqual(queued["attention_reason"], brenda["attention_reason"])
        self.assertFalse(queued["waiting_on_daniel"])
        self.assertEqual(desk.get_health()["backlog"]["waiting_on_daniel"], 0)
        desk.close()

        self.layer.conn.execute("UPDATE cases SET owner = 'ally' WHERE case_id = ?", (opened["case_id"],))
        desk = LeadDesk(self.path, service_probe=lambda: {"observed": False, "active": None, "summary": "fixture"})
        ally = desk.get_case(opened["case_id"])
        self.assertEqual(ally["attention_reason"], "Ally owns this. Do not send a competing reply.")
        self.assertFalse(ally["waiting_on_daniel"])
        desk.close()
