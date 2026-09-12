"""Offline phone-handoff vector must match the deployed production parser.

Does not send mail or touch live cases.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

from bt_intake_proof.desk_bridge import format_control_mail, parse_control_mail
from bt_intake_proof.desk_control_codec import decode_control_fields, serialize_control_body
from bt_intake_proof.desk_sent_proof import canonical_control_payload

ROOT = Path(__file__).resolve().parents[1]
VECTOR = ROOT / "results" / "phone-handoff" / "offline_vector.json"
PORTABLE = ROOT / "results" / "phone-handoff" / "offline_ctrl_enc.py"


def _load_portable():
    spec = importlib.util.spec_from_file_location("offline_ctrl_enc", PORTABLE)
    if spec is None or spec.loader is None:
        raise RuntimeError("portable encoder missing")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PhoneHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.vector = json.loads(VECTOR.read_text(encoding="utf-8"))
        cls.portable = _load_portable()

    def test_vector_is_synthetic(self) -> None:
        self.assertTrue(self.vector["synthetic"])
        self.assertFalse(self.vector["live"])
        self.assertNotIn("1a096d60643b3b1a", json.dumps(self.vector))
        self.assertEqual(self.vector["source_commit"], "c41404e75bbc768d034814a5ec3bca90ad927b6e")

    def test_production_serialize_matches_vector(self) -> None:
        body = serialize_control_body(
            intent=self.vector["intent"],
            binding=self.vector["binding"],
            owner=self.vector.get("owner") or "",
            note=self.vector["note"],
        )
        self.assertEqual(body, self.vector["body"])
        mail = format_control_mail(
            self.vector["intent"],
            self.vector["binding"],
            owner=self.vector.get("owner") or None,
            note=self.vector["note"],
        )
        self.assertEqual(mail["from"], "daniel@btpestcontrol.com")
        self.assertEqual(mail["to"], "contactus@btpestcontrol.com")
        self.assertEqual(mail["subject"], "BT-INTAKE-PROOF-DESK-CTRL-E9A8")
        self.assertEqual(mail["body"], self.vector["body"])

    def test_portable_encode_matches_production(self) -> None:
        body = self.portable.encode(
            intent=self.vector["intent"],
            binding=self.vector["binding"],
            owner=self.vector.get("owner") or "",
            note=self.vector["note"],
        )
        self.assertEqual(body, self.vector["body"])
        self.assertEqual(body, serialize_control_body(
            intent=self.vector["intent"],
            binding=self.vector["binding"],
            owner=self.vector.get("owner") or "",
            note=self.vector["note"],
        ))

    def test_production_parser_keeps_exact_note(self) -> None:
        parsed = parse_control_mail(self.vector["subject"], self.vector["body"])
        decoded = decode_control_fields(self.vector["subject"], self.vector["body"])
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["note"], self.vector["note"])
        self.assertTrue(parsed["note"].endswith("  \n"))
        self.assertIn("Café", parsed["note"])
        self.assertIn("—", parsed["note"])
        self.assertEqual(decoded["note"], self.vector["note"])
        self.assertEqual(decoded["payload"]["packet_hash"], self.vector["binding"]["packet_hash"])
        self.assertEqual(canonical_control_payload(self.vector["subject"], self.vector["body"]), self.vector["canonical"])

    def test_portable_decode_matches_production(self) -> None:
        portable = self.portable.decode(self.vector["subject"], self.vector["body"])
        production = decode_control_fields(self.vector["subject"], self.vector["body"])
        self.assertTrue(portable["ok"])
        self.assertEqual(portable["note"], production["note"])
        self.assertEqual(portable["enc_len"], self.vector["enc_len"])
        self.assertEqual(portable["enc_sha256"], self.vector["enc_sha256"])
        self.assertEqual(portable["raw_json"], self.vector["raw_json"])

    def test_portable_checker_passes(self) -> None:
        result = self.portable.check_vector(VECTOR)
        self.assertTrue(result["ok"], result)


if __name__ == "__main__":
    unittest.main()
