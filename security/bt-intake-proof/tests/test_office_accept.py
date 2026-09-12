import json
import tempfile
import unittest
from pathlib import Path

from bt_intake_proof.cases import DRAFT_NOT_SENT
from bt_intake_proof.desk_sent_proof import set_test_sent_lookup
from tests.office_accept_pack import pack_flags_invented_promises, run_office_accept_pack


class OfficeAcceptPackTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_test_sent_lookup(None)

    def test_five_scenarios_pass_on_isolated_store(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "office-accept.sqlite"
        result = run_office_accept_pack(path)
        self.assertTrue(result["ok"], json.dumps(result["scenarios"], indent=2, default=str))
        self.assertTrue(result["isolation"]["actions_1_and_2_untouched"])
        self.assertFalse(result["isolation"]["production_sqlite"])
        self.assertEqual(result["isolation"]["customer_sends"], "off")
        names = [item["name"] for item in result["scenarios"]]
        self.assertEqual(
            names,
            [
                "new_inquiry_reviewable_draft",
                "existing_customer_service_issue_not_discarded",
                "office_ownership_and_hold_block_send",
                "new_inbound_or_changed_draft_invalidates_authorization",
                "repeat_decision_and_restart_no_duplicate_action",
            ],
        )
        self.assertTrue(all(item["status"] == "PASS" for item in result["scenarios"]))
        self.assertTrue(any(item["draft_exists"] for item in result["console"]["cases"]))
        self.assertIn(DRAFT_NOT_SENT, result["review_email"]["body"])
        blocked = {item["id"]: item["status"] for item in result["unsupported"]}
        self.assertEqual(blocked["live_voice_or_phone"], "BLOCKED")
        self.assertEqual(blocked["live_unmarked_customer_mail"], "BLOCKED")
        tmp.cleanup()

    def test_pack_reviewer_flags_invented_promises_locally(self) -> None:
        self.assertFalse(pack_flags_invented_promises("Thanks. The office will call."))
        self.assertTrue(pack_flags_invented_promises("Tuesday at 3pm for $999. You are booked."))


if __name__ == "__main__":
    unittest.main()
