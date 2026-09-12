import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bt_intake_proof.cloud_host import safe_log
from bt_intake_proof.gce_identity import metadata_available, receiver_identity
from bt_intake_proof.live_google import _later_history_id, renew_watch_preserving_cursor
from bt_intake_proof.constants import MAILBOX
from bt_intake_proof.store import ReceiptStore


class CloudHostTests(unittest.TestCase):
    def test_metadata_absent_off_gce(self) -> None:
        self.assertFalse(metadata_available())
        identity = receiver_identity()
        self.assertEqual(identity["source"], "impersonation_fallback")
        self.assertFalse(identity["json_key_created"])

    def test_later_history_id_never_rewinds(self) -> None:
        self.assertEqual(_later_history_id("6008029", "6007981"), "6008029")
        self.assertEqual(_later_history_id("6007981", "6008029"), "6008029")

    def test_renew_skips_when_not_near_expiry(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        store = ReceiptStore(Path(tmp.name) / "receipts.sqlite")
        far = str(int((__import__("time").time() + 6 * 24 * 3600) * 1000))
        store.upsert_watch(MAILBOX, history_id="6008029", expiration=far, topic="topic")
        try:
            result = renew_watch_preserving_cursor(store, min_remaining_seconds=86400)
            self.assertEqual(result["status"], "SKIPPED")
            self.assertEqual(store.get_watch(MAILBOX)["history_id"], "6008029")
        finally:
            store.close()
            tmp.cleanup()

    def test_safe_log_omits_bodies(self) -> None:
        with mock.patch("builtins.print") as printer:
            safe_log("capture", gmail_message_id="mid", body_text="secret body", raw_message="raw")
        printed = json.loads(printer.call_args[0][0])
        self.assertEqual(printed["event"], "capture")
        self.assertNotIn("body_text", printed)
        self.assertNotIn("raw_message", printed)
        self.assertEqual(printed["gmail_message_id"], "mid")


if __name__ == "__main__":
    unittest.main()
