"""Exact-text control encoding. Isolated fixtures only. Does not send or touch live cases."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from bt_intake_proof.cases import CaseLayer
from bt_intake_proof.constants import ALLOWED_SENDER, DETECTION_EVENT_DRIVEN, MAILBOX, MARKER_DESK_CTRL
from bt_intake_proof.desk_bridge import (
    compute_packet_binding,
    format_control_mail,
    install_desk_send_draft,
    parse_control_mail,
    process_control_mail,
)
from bt_intake_proof.desk_control import INTENT_HOLD, INTENT_REVISE
from bt_intake_proof.desk_control_codec import (
    CTRL_ENC_VERSION,
    WIRE_LINE,
    decode_control_fields,
    note_fits_simple,
    serialize_control_body,
)
from bt_intake_proof.desk_origin import daniel_origin_evidence
from bt_intake_proof.desk_packets import build_desk_packets, write_desk_packets
from bt_intake_proof.desk_sent_proof import (
    REASON_MISMATCH,
    authorize_control_sender,
    canonical_control_payload,
    fixture_sent_lookup,
    inbound_control_view,
    match_sent_record,
    matching_sent_record,
)
from bt_intake_proof.phasee_constants import PHASEE_CASE_MARKER
from bt_intake_proof.send_bind import ensure_send_tables
from bt_intake_proof.store import ReceiptStore, body_hash

# Reconstructed from Codex-observed wrap of Daniel Sent 1a096d7c880b70fb /
# contactus 1a096d7f837799a5. Not a live replay and not a model PASS.
LIVE_WRAP_NOTE = (
    "DRAFT - NOT SENT Please share your name, a callback number, the service "
    "address, and details about the ants. Our office will follow up once we have that."
)
LIVE_WRAP_DELIVERED_NOTE = (
    "NOTE="
    "DRAFT - NOT SENT Please share your name, a callback number, the service "
    "address, and details about the ants.\n"
    "Our office\n"
    "will follow up once we have that."
)


def _mime_hard_wrap(text: str, width: int = 78) -> str:
    """Gmail-style hard wrap: break long lines, no leading WSP on continuations."""
    out: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        while len(line) > width:
            cut = line.rfind(" ", 0, width + 1)
            if cut <= 0:
                cut = width
            out.append(line[:cut])
            line = line[cut:].lstrip()
        out.append(line)
    return "\n".join(out)


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


class DeskControlCodecTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "receipts.sqlite"
        self.store = ReceiptStore(self.path)
        self.layer = CaseLayer(self.store)
        ensure_send_tables(self.layer)
        self.store.commit_notification(
            mailbox=MAILBOX,
            history_id="enc-1",
            detection_path=DETECTION_EVENT_DRIVEN,
            pubsub_message_id="n-enc-1",
            receipts=[_receipt("enc-1")],
        )
        opened = self.layer.upsert_from_receipt(self.store.get_receipt(MAILBOX, "enc-1"))
        install_desk_send_draft(self.layer, opened["case_id"], "nonce-enc-1")
        self.case_id = opened["case_id"]
        self.binding = compute_packet_binding(self.layer.get_case(self.case_id), self.layer.latest_draft(self.case_id))

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _process(self, mail: dict, *, body: str | None = None, sent_body: str | None = None, mid: str = "ctrl-enc") -> dict:
        rfc = f"<{mid}@desk.btpestcontrol.com>"
        received = "2026-09-12T18:20:00+00:00"
        inbound_body = body if body is not None else mail["body"]
        lookup_body = sent_body if sent_body is not None else mail["body"]
        return process_control_mail(
            self.layer,
            sender=ALLOWED_SENDER,
            subject=mail["subject"],
            body=inbound_body,
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
            sent_lookup=fixture_sent_lookup(mail["subject"], lookup_body, rfc_message_id=rfc, received_at=received),
        )

    def test_simple_hold_stays_unencoded(self) -> None:
        mail = format_control_mail(INTENT_HOLD, self.binding)
        self.assertNotIn("CTRL-ENC=", mail["body"])
        self.assertIn("NOTE=\n", mail["body"])
        parsed = parse_control_mail(mail["subject"], mail["body"])
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["encoding"], "simple")
        self.assertEqual(parsed["intent"], INTENT_HOLD)
        self.assertIsNone(parsed["note"])

    def test_live_wrap_evidence_old_note_fails_closed(self) -> None:
        self.assertGreater(len(f"NOTE={LIVE_WRAP_NOTE}"), WIRE_LINE)
        self.assertFalse(note_fits_simple(LIVE_WRAP_NOTE))
        old_sent = (
            f"{MARKER_DESK_CTRL}\nINTENT={INTENT_REVISE}\nOWNER=\nNOTE={LIVE_WRAP_NOTE}\n"
            f"CASE_ID={self.binding['case_id']}\nDRAFT_VERSION={self.binding['draft_version']}\n"
            f"NONCE={self.binding['nonce']}\nPACKET_HASH={self.binding['packet_hash']}\n"
        )
        old_delivered = old_sent.replace(f"NOTE={LIVE_WRAP_NOTE}", LIVE_WRAP_DELIVERED_NOTE)
        sent = decode_control_fields(MARKER_DESK_CTRL, old_sent)
        delivered = decode_control_fields(MARKER_DESK_CTRL, old_delivered)
        self.assertFalse(sent["ok"])
        self.assertEqual(sent["reason"], "note_folded_or_truncated")
        self.assertFalse(delivered["ok"])
        self.assertEqual(delivered["reason"], "note_folded_or_truncated")
        inbound = inbound_control_view(
            subject=MARKER_DESK_CTRL,
            body=old_delivered,
            rfc_message_id="<wrap@bt>",
            recipients=[MAILBOX],
            received_at="2026-09-12T18:10:00+00:00",
        )
        record = matching_sent_record(
            MARKER_DESK_CTRL,
            old_sent,
            rfc_message_id="<wrap@bt>",
            received_at="2026-09-12T18:10:00+00:00",
        )
        judged = match_sent_record(inbound, record)
        self.assertFalse(judged["ok"])
        self.assertIn("payload", judged["reasons"])

    def test_v1_roundtrips_unicode_paragraphs_and_mime_wrap(self) -> None:
        note = (
            "DRAFT - NOT SENT\n\n"
            "Café — please share your name, callback, address, and ant details. "
            "Leave the kitchen as-is; we will not quote a price or book a time. 🐜\n\n"
            "B&T office"
        )
        mail = format_control_mail(INTENT_REVISE, self.binding, note=note)
        self.assertIn(f"CTRL-ENC={CTRL_ENC_VERSION}", mail["body"])
        self.assertIn("ENC_B64\n", mail["body"])
        self.assertTrue(all(len(line) <= 64 for line in mail["body"].splitlines()))
        self.assertNotIn(f"NOTE={note.splitlines()[0]}", mail["body"])
        wrapped = _mime_hard_wrap(mail["body"], width=46)
        self.assertNotEqual(wrapped, mail["body"])
        sent = parse_control_mail(mail["subject"], mail["body"])
        delivered = parse_control_mail(mail["subject"], wrapped)
        self.assertTrue(sent["ok"])
        self.assertTrue(delivered["ok"])
        self.assertEqual(sent["note"], note)
        self.assertEqual(delivered["note"], note)
        self.assertEqual(sent["packet_hash"], self.binding["packet_hash"])
        self.assertEqual(
            canonical_control_payload(mail["subject"], mail["body"]),
            canonical_control_payload(mail["subject"], wrapped),
        )
        inbound = inbound_control_view(
            subject=mail["subject"],
            body=wrapped,
            rfc_message_id="<v1wrap@bt>",
            recipients=[MAILBOX],
            received_at="2026-09-12T18:20:00+00:00",
        )
        record = matching_sent_record(
            mail["subject"],
            mail["body"],
            rfc_message_id="<v1wrap@bt>",
            received_at="2026-09-12T18:20:00+00:00",
        )
        self.assertTrue(match_sent_record(inbound, record)["ok"])

    def test_v1_wrapped_revise_authorizes_and_saves_exact_note(self) -> None:
        note = LIVE_WRAP_NOTE + "\n\nPlease keep this exact."
        mail = format_control_mail(INTENT_REVISE, self.binding, note=note)
        wrapped = _mime_hard_wrap(mail["body"], width=50)
        result = self._process(mail, body=wrapped, sent_body=mail["body"], mid="ctrl-v1-wrap")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["applied"], "revise_draft")
        draft = self.layer.latest_draft(self.case_id)
        self.assertEqual(draft["proposed_response"], note)
        self.assertEqual(int(draft["version"]), 2)

    def test_tampered_b64_and_checksums_fail(self) -> None:
        note = "DRAFT - NOT SENT\n\nPlease share the service address and a callback number."
        mail = format_control_mail(INTENT_REVISE, self.binding, note=note)
        parsed = parse_control_mail(mail["subject"], mail["body"])
        self.assertTrue(parsed["ok"])

        flipped = mail["body"].replace("ENC_B64\n", "ENC_B64\nA", 1)
        self.assertFalse(parse_control_mail(mail["subject"], flipped)["ok"])

        bad_len = re.sub(r"ENC_LEN=\d+", "ENC_LEN=1", mail["body"], count=1)
        self.assertEqual(parse_control_mail(mail["subject"], bad_len)["reason"], "note_len_mismatch")

        bad_sha = re.sub(r"\n[0-9a-f]{64}\n", "\n" + ("ab" * 32) + "\n", mail["body"], count=1)
        self.assertEqual(parse_control_mail(mail["subject"], bad_sha)["reason"], "note_sha256_mismatch")

        truncated = mail["body"].split("ENC_B64_END")[0]
        self.assertEqual(parse_control_mail(mail["subject"], truncated)["reason"], "note_b64_truncated")

        dup = mail["body"].replace("ENC_LEN=", "ENC_LEN=1\nENC_LEN=", 1)
        self.assertEqual(parse_control_mail(mail["subject"], dup)["reason"], "duplicate_control_field")

        conflict = mail["body"].replace("CTRL-ENC=v1\n", "CTRL-ENC=v1\nNOTE=other text\n", 1)
        self.assertEqual(parse_control_mail(mail["subject"], conflict)["reason"], "conflicting_note_encoding")

        inbound = inbound_control_view(
            subject=mail["subject"],
            body=flipped,
            rfc_message_id="<tamper@bt>",
            recipients=[MAILBOX],
            received_at="2026-09-12T18:20:00+00:00",
        )
        record = matching_sent_record(
            mail["subject"],
            mail["body"],
            rfc_message_id="<tamper@bt>",
            received_at="2026-09-12T18:20:00+00:00",
        )
        judged = match_sent_record(inbound, record)
        self.assertFalse(judged["ok"])
        self.assertIn("payload", judged["reasons"])

    def test_quoted_copy_does_not_authorize(self) -> None:
        mail = format_control_mail(INTENT_HOLD, self.binding)
        quoted = "\n".join(f"> {line}" for line in mail["body"].splitlines())
        parsed = parse_control_mail(mail["subject"], quoted)
        self.assertFalse(parsed.get("ok") and parsed.get("intent"))
        rfc = "<quoted@desk.btpestcontrol.com>"
        received = "2026-09-12T18:20:00+00:00"
        origin = authorize_control_sender(
            None,
            ALLOWED_SENDER,
            {
                **daniel_origin_evidence("quoted"),
                "rfc_message_id": rfc,
                "received_at": received,
                "recipients": [MAILBOX],
            },
            inbound_control_view(
                subject=mail["subject"],
                body=quoted,
                rfc_message_id=rfc,
                recipients=[MAILBOX],
                received_at=received,
            ),
            sent_lookup=fixture_sent_lookup(mail["subject"], mail["body"], rfc_message_id=rfc, received_at=received),
        )
        self.assertFalse(origin.get("accepted"))
        self.assertEqual(origin.get("reason"), REASON_MISMATCH)

    def test_sixty_three_char_hash_still_packet_hash_invalid(self) -> None:
        mail = format_control_mail(INTENT_HOLD, self.binding)
        short = self.binding["packet_hash"][:63]
        self.assertEqual(len(short), 63)
        body = mail["body"].replace(self.binding["packet_hash"], short)
        parsed = parse_control_mail(mail["subject"], body)
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["packet_hash"], short)
        result = self._process(mail, body=body, sent_body=body, mid="ctrl-short-hash")
        self.assertFalse(result["ok"])
        self.assertIn("packet_hash_invalid", result.get("blocks") or [])

    def test_unknown_encoding_fails_closed(self) -> None:
        body = serialize_control_body(intent=INTENT_HOLD, binding=self.binding).replace(
            "INTENT=hold\n", "CTRL-ENC=v2\nINTENT=hold\n", 1
        )
        parsed = parse_control_mail(MARKER_DESK_CTRL, body)
        self.assertFalse(parsed["ok"])
        self.assertEqual(parsed["reason"], "unknown_ctrl_enc")

    def test_packets_emit_machine_readable_control_hash(self) -> None:
        self.store.close()
        dest = Path(self.tmp.name) / "packets"
        payload = build_desk_packets(self.path, case_id=self.case_id, control_intent=INTENT_REVISE, control_note=LIVE_WRAP_NOTE)
        write_desk_packets(payload, dest)
        control = payload["control"]
        self.assertEqual(len(control["binding"]["packet_hash"]), 64)
        self.assertEqual(control["binding"]["packet_hash"], self.binding["packet_hash"])
        self.assertTrue(control["generate_only"])
        selected = control["selected"]
        self.assertEqual(parse_control_mail(selected["subject"], selected["body"])["note"], LIVE_WRAP_NOTE)
        disk = (dest / "desk-control.json").read_text(encoding="utf-8")
        self.assertIn(self.binding["packet_hash"], disk)
        self.assertTrue((dest / "desk-control.txt").exists())
        kinds = {item["kind"] for item in payload["emails"]}
        self.assertEqual(kinds, {"queue", "case", "health"})


if __name__ == "__main__":
    unittest.main()
