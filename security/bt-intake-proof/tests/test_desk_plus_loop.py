import base64
import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import patch

from bt_intake_proof.cases import CaseLayer
from bt_intake_proof.constants import (
    ALLOWED_SENDER,
    DETECTION_EVENT_DRIVEN,
    LEAD_DESK_CONTROL_LABEL_ID,
    LEAD_DESK_PLUS_MAILBOX,
    LEAD_DESK_PLUS_RESULTS_MAILBOX,
    LEAD_DESK_RESULTS_LABEL_ID,
    MAILBOX,
    MARKER_PLUS_RESULT,
    STALE_PLUS_CONTROL_ID,
    TRANSPORT_PLUS,
)
from bt_intake_proof.desk_bridge import compute_packet_binding, format_control_mail, process_control_mail
from bt_intake_proof.desk_control import INTENT_HOLD, INTENT_REVISE
from bt_intake_proof.desk_plus_discover import (
    PlusHistoryExpired,
    extract_plus_history_ids,
    fetch_plus_history,
    plus_history_query,
    prefilter_plus_candidate,
    set_test_plus_discover_client,
)
from bt_intake_proof.desk_plus_loop import poll_plus_controls_once, process_discovered_plus_control
from bt_intake_proof.desk_plus_preflight import plus_control_preflight, set_test_plus_preflight
from bt_intake_proof.desk_plus_proof import set_test_plus_client, set_test_plus_fixtures, set_test_plus_now
from bt_intake_proof.desk_plus_result_send import (
    KIND_PLUS_COMBINED,
    MemoryPlusResultTransport,
    REASON_CHANNEL_NOT_READY,
    deliver_plus_results,
    plus_result_channel_ready,
    reconcile_plus_result_outbox,
    set_test_plus_result_ready,
    set_test_plus_result_transport,
)
from bt_intake_proof.desk_plus_store import (
    PLUS_CURSOR_KEY,
    get_plus_cursor,
    get_seen,
    save_plus_cursor,
)
from bt_intake_proof.gmail_readonly import ReadOnlyGmail
from bt_intake_proof.phasee_constants import PHASEE_CASE_MARKER
from bt_intake_proof.send_bind import ensure_send_tables
from bt_intake_proof.store import ReceiptStore, body_hash
from test_desk_plus_control import FakeDanielPlusClient, _raw_plus_message, _receipt


def _ms(value: datetime) -> str:
    return str(int(value.timestamp() * 1000))


def _meta(message_id: str, *, labels: list[str], headers: list[tuple[str, str]], subject: str = "") -> dict:
    payload_headers = [{"name": name, "value": value} for name, value in headers]
    if subject:
        payload_headers.append({"name": "Subject", "value": subject})
    return {"id": message_id, "labelIds": list(labels), "payload": {"headers": payload_headers}}


class FakePlusLoopClient(FakeDanielPlusClient):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.history_error: Exception | None = None
        self.history_pages: list[dict] = []
        self.searches: list[str] = []
        self.search_ids: list[str] = []
        self.labels = [
            {"id": LEAD_DESK_CONTROL_LABEL_ID, "name": "B&T Lead Desk/Control"},
            {"id": LEAD_DESK_RESULTS_LABEL_ID, "name": "B&T Lead Desk/Results"},
        ]
        self.profile_history_id = "900"

    def get_profile(self) -> dict:
        return {"emailAddress": self.profile_email, "historyId": self.profile_history_id}

    def plus_history(self, start_history_id: str) -> dict:
        if self.history_error:
            raise self.history_error
        history: list[dict] = []
        hid = str(start_history_id)
        for page in self.history_pages:
            history.extend(page.get("history") or [])
            hid = str(page.get("historyId") or hid)
        return {"history": history, "historyId": hid}

    def search_messages(self, query: str, max_results: int = 10) -> list[dict]:
        self.searches.append(query)
        return [{"id": item} for item in self.search_ids[:max_results]]

    def get_message(self, message_id: str, fmt: str = "raw") -> dict:
        raw = dict(self.messages[message_id])
        if fmt == "metadata":
            return {
                "id": raw.get("id"),
                "labelIds": raw.get("labelIds") or [],
                "payload": {
                    "headers": [
                        {"name": name, "value": value}
                        for name, value in (raw.get("headers") or [])
                    ]
                },
            }
        return raw

    def list_labels(self) -> list[dict]:
        return list(self.labels)


def _plus_raw_with_headers(message_id: str, subject: str, body: str, internal: datetime, labels: list[str]) -> dict:
    raw = _raw_plus_message(message_id, subject=subject, body=body, internal=internal, labels=labels)
    raw["headers"] = [
        ("From", ALLOWED_SENDER),
        ("To", LEAD_DESK_PLUS_MAILBOX),
        ("Subject", subject),
    ]
    return raw


class DeskPlusLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "receipts.sqlite"
        self.store = ReceiptStore(self.path)
        self.layer = CaseLayer(self.store)
        ensure_send_tables(self.layer)
        self.store.commit_notification(
            mailbox=MAILBOX,
            history_id="cu-1",
            detection_path=DETECTION_EVENT_DRIVEN,
            pubsub_message_id="n-cu-1",
            receipts=[_receipt("plus-in-loop")],
        )
        opened = self.layer.upsert_from_receipt(self.store.get_receipt(MAILBOX, "plus-in-loop"))
        self.layer.save_draft(
            opened["case_id"],
            {
                "classification": "internal_plus_loop",
                "known_facts": [],
                "missing_info": [],
                "recommended_next_step": "Save only",
                "proposed_response": "DRAFT - NOT SENT\n\nThanks. Share the address.",
                "channel": "email",
                "judgment_needed": "Revise only",
                "reasoning_summary": "Plus loop fixture",
            },
            nonce="nonce-plus-loop-1",
            label_not_sent=True,
        )
        self.case_id = opened["case_id"]
        self.binding = compute_packet_binding(self.layer.get_case(self.case_id), self.layer.latest_draft(self.case_id))
        self.mail = format_control_mail(
            INTENT_REVISE,
            self.binding,
            note="DRAFT - NOT SENT\n\nLoop revision. No customer send.",
            transport=TRANSPORT_PLUS,
        )
        self.sent_at = datetime(2026, 9, 12, 22, 0, tzinfo=timezone.utc)
        self.now = self.sent_at + timedelta(minutes=3)
        set_test_plus_fixtures(True)
        set_test_plus_now(self.now)
        set_test_plus_result_ready(True)
        set_test_plus_result_transport(MemoryPlusResultTransport())
        set_test_plus_discover_client(None)
        set_test_plus_client(None)
        set_test_plus_preflight()
        self.watch_before = self.store.get_watch(MAILBOX)

    def tearDown(self) -> None:
        set_test_plus_fixtures(False)
        set_test_plus_now(None)
        set_test_plus_client(None)
        set_test_plus_discover_client(None)
        set_test_plus_result_ready(None)
        set_test_plus_result_transport(None)
        set_test_plus_preflight()
        self.store.close()
        self.tmp.cleanup()

    def _install_control(self, message_id: str, client: FakePlusLoopClient) -> None:
        raw = _plus_raw_with_headers(
            message_id,
            self.mail["subject"],
            self.mail["body"],
            self.sent_at,
            ["SENT", LEAD_DESK_CONTROL_LABEL_ID],
        )
        client.messages[message_id] = raw
        set_test_plus_client(client)
        set_test_plus_discover_client(client)

    def test_repeated_and_reordered_history_dedupes(self) -> None:
        history = {
            "history": [
                {"labelsAdded": [{"message": {"id": "b"}, "labelIds": [LEAD_DESK_CONTROL_LABEL_ID]}]},
                {"messagesAdded": [{"message": {"id": "a"}}]},
                {"messagesAdded": [{"message": {"id": "a"}}]},
                {"labelsAdded": [{"message": {"id": "b"}, "labelIds": [LEAD_DESK_CONTROL_LABEL_ID]}]},
            ]
        }
        ids = extract_plus_history_ids(history)
        self.assertEqual([item["id"] for item in ids], ["b", "a"])

    def test_label_added_without_message_added_is_discovered(self) -> None:
        client = FakePlusLoopClient()
        self._install_control("lab-1", client)
        save_plus_cursor(self.layer, "10")
        client.history_pages = [
            {
                "historyId": "20",
                "history": [
                    {"labelsAdded": [{"message": {"id": "lab-1"}, "labelIds": [LEAD_DESK_CONTROL_LABEL_ID]}]}
                ],
            }
        ]
        result = poll_plus_controls_once(self.layer, client=client)
        self.assertTrue(result["ok"], result)
        self.assertIn("lab-1", result["discovery"]["candidates"])
        self.assertTrue(any(item.get("ok") for item in result["processed"]))
        self.assertEqual(int(self.layer.get_case(self.case_id)["draft_version"]), 2)

    def test_history_pagination_merges_message_and_label_events(self) -> None:
        pages = [
            {
                "history": [{"messagesAdded": [{"message": {"id": "page-a"}}]}],
                "nextPageToken": "p2",
                "historyId": "2",
            },
            {
                "history": [
                    {"labelsAdded": [{"message": {"id": "page-b"}, "labelIds": [LEAD_DESK_CONTROL_LABEL_ID]}]}
                ],
                "historyId": "3",
            },
        ]

        def _get(url: str, _token: str) -> dict:
            if "pageToken=p2" in url:
                return pages[1]
            return pages[0]

        client = type("Tok", (), {"access_token": "tok"})()
        with patch("bt_intake_proof.desk_plus_discover._get_json", side_effect=_get):
            merged = fetch_plus_history(client, "1")
        ids = extract_plus_history_ids(merged)
        self.assertEqual([item["id"] for item in ids], ["page-a", "page-b"])
        self.assertEqual(merged["historyId"], "3")
        self.assertIn("historyTypes=messageAdded", plus_history_query() or "in:sent")

    def test_expired_history_reconciles_sent_control_not_inbox(self) -> None:
        client = FakePlusLoopClient()
        self._install_control("rec-1", client)
        save_plus_cursor(self.layer, "10")
        client.history_error = PlusHistoryExpired("historyId no longer valid")
        client.search_ids = ["rec-1", STALE_PLUS_CONTROL_ID]
        result = poll_plus_controls_once(self.layer, client=client)
        self.assertTrue(result["discovery"].get("history_expired"))
        self.assertTrue(client.searches)
        self.assertIn("in:sent", client.searches[0])
        self.assertIn(LEAD_DESK_CONTROL_LABEL_ID, client.searches[0])
        self.assertNotIn("in:inbox", client.searches[0])
        self.assertEqual(get_seen(self.layer, STALE_PLUS_CONTROL_ID)["status"], "skipped")
        self.assertTrue(any(item.get("ok") and item.get("gmail_message_id") == "rec-1" or item.get("applied") for item in result["processed"]))

    def test_stale_control_never_processed(self) -> None:
        client = FakePlusLoopClient()
        raw = _plus_raw_with_headers(
            STALE_PLUS_CONTROL_ID,
            self.mail["subject"],
            self.mail["body"],
            self.sent_at,
            ["SENT", LEAD_DESK_CONTROL_LABEL_ID],
        )
        client.messages[STALE_PLUS_CONTROL_ID] = raw
        set_test_plus_client(client)
        set_test_plus_discover_client(client)
        save_plus_cursor(self.layer, "10")
        client.history_pages = [
            {"historyId": "11", "history": [{"messagesAdded": [{"message": {"id": STALE_PLUS_CONTROL_ID}}]}]}
        ]
        before = int(self.layer.get_case(self.case_id)["draft_version"])
        result = poll_plus_controls_once(self.layer, client=client)
        self.assertEqual(int(self.layer.get_case(self.case_id)["draft_version"]), before)
        self.assertEqual(get_seen(self.layer, STALE_PLUS_CONTROL_ID)["reason"], "stale_plus_control_forbidden")
        self.assertFalse(any(item.get("ok") for item in result["processed"]))

    def test_wrong_account_and_envelope_are_skipped(self) -> None:
        bad_from = _meta(
            "bad-from",
            labels=["SENT", LEAD_DESK_CONTROL_LABEL_ID],
            headers=[("From", "amy@example.com"), ("To", LEAD_DESK_PLUS_MAILBOX)],
        )
        self.assertEqual(prefilter_plus_candidate(bad_from)["reason"], "plus_discovery_envelope_mismatch")
        results = _meta(
            "res-1",
            labels=["SENT", LEAD_DESK_CONTROL_LABEL_ID, LEAD_DESK_RESULTS_LABEL_ID],
            headers=[("From", ALLOWED_SENDER), ("To", LEAD_DESK_PLUS_RESULTS_MAILBOX)],
        )
        self.assertEqual(prefilter_plus_candidate(results)["reason"], "plus_results_loop_excluded")

    def test_unsupported_plus_intent_does_not_save(self) -> None:
        hold = format_control_mail(INTENT_HOLD, self.binding, transport=TRANSPORT_PLUS)
        client = FakePlusLoopClient()
        raw = _plus_raw_with_headers("hold-1", hold["subject"], hold["body"], self.sent_at, ["SENT", LEAD_DESK_CONTROL_LABEL_ID])
        client.messages["hold-1"] = raw
        set_test_plus_client(client)
        before = int(self.layer.get_case(self.case_id)["draft_version"])
        result = process_control_mail(
            self.layer,
            sender=ALLOWED_SENDER,
            subject=hold["subject"],
            body=hold["body"],
            gmail_message_id="hold-1",
            provider_evidence={
                "fetched_via": "daniel_gmail_plus_control_api",
                "authenticated_mailbox": ALLOWED_SENDER,
                "gmail_message_id": "hold-1",
                "message_exists": True,
                "labels": ["SENT"],
                "headers": [("From", ALLOWED_SENDER), ("To", LEAD_DESK_PLUS_MAILBOX)],
                "internal_date": self.sent_at.isoformat(),
                "live_profile_verified": True,
            },
            headers=[("From", ALLOWED_SENDER), ("To", LEAD_DESK_PLUS_MAILBOX)],
            recipients=[LEAD_DESK_PLUS_MAILBOX],
            received_at=self.sent_at.isoformat(),
            transport=TRANSPORT_PLUS,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "plus_intent_not_in_milestone")
        self.assertEqual(int(self.layer.get_case(self.case_id)["draft_version"]), before)

    def test_missing_result_channel_does_not_consume(self) -> None:
        set_test_plus_result_ready(False)
        set_test_plus_result_transport(None)
        client = FakePlusLoopClient()
        self._install_control("no-send-1", client)
        before = int(self.layer.get_case(self.case_id)["draft_version"])
        nonce_before = self.layer.latest_draft(self.case_id)["nonce"]
        result = process_discovered_plus_control(self.layer, "no-send-1")
        self.assertEqual(result["reason"], REASON_CHANNEL_NOT_READY)
        self.assertEqual(int(self.layer.get_case(self.case_id)["draft_version"]), before)
        self.assertEqual(self.layer.latest_draft(self.case_id)["nonce"], nonce_before)
        consumed = self.layer.conn.execute("SELECT COUNT(*) AS n FROM desk_control_consumed").fetchone()["n"]
        self.assertEqual(consumed, 0)

    def test_concurrency_consumes_nonce_once(self) -> None:
        client = FakePlusLoopClient()
        self._install_control("conc-1", client)
        mail2 = dict(self.mail)
        raw2 = _plus_raw_with_headers("conc-2", mail2["subject"], mail2["body"], self.sent_at, ["SENT", LEAD_DESK_CONTROL_LABEL_ID])
        client.messages["conc-2"] = raw2
        results: list[dict] = [None, None]  # type: ignore[list-item]

        def _run(index: int, mid: str) -> None:
            store = ReceiptStore(self.path)
            try:
                layer = CaseLayer(store)
                results[index] = process_discovered_plus_control(layer, mid)
            finally:
                store.close()

        threads = [
            threading.Thread(target=_run, args=(0, "conc-1")),
            threading.Thread(target=_run, args=(1, "conc-2")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        oks = [item for item in results if item and item.get("ok")]
        self.assertEqual(len(oks), 1)
        self.assertEqual(int(self.layer.get_case(self.case_id)["draft_version"]), 2)

    def test_result_persist_failure_rolls_back_save(self) -> None:
        client = FakePlusLoopClient()
        self._install_control("rb-1", client)
        before = int(self.layer.get_case(self.case_id)["draft_version"])

        def boom(*_args, **_kwargs):
            raise sqlite3.OperationalError("injected plus result failure")

        with patch("bt_intake_proof.desk_plus_result_send.persist_plus_result_intent", side_effect=boom):
            with self.assertRaises(sqlite3.OperationalError):
                process_discovered_plus_control(self.layer, "rb-1")
        self.assertEqual(int(self.layer.get_case(self.case_id)["draft_version"]), before)
        self.assertEqual(self.layer.conn.execute("SELECT COUNT(*) AS n FROM desk_control_consumed").fetchone()["n"], 0)

    def test_crash_recovery_does_not_save_twice(self) -> None:
        client = FakePlusLoopClient()
        self._install_control("once-1", client)
        first = process_discovered_plus_control(self.layer, "once-1")
        self.assertTrue(first["ok"], first)
        replay = process_discovered_plus_control(self.layer, "once-1")
        self.assertTrue(replay.get("replayed") or replay.get("reason") == "already_claimed")
        self.assertEqual(int(self.layer.get_case(self.case_id)["draft_version"]), first["draft_version"])
        rows = self.layer.conn.execute("SELECT id FROM plus_result_outbox").fetchall()
        self.assertEqual(len(rows), 1)

    def test_uncertain_send_reconciles_before_retry(self) -> None:
        client = FakePlusLoopClient()
        self._install_control("unc-1", client)
        transport = MemoryPlusResultTransport(timeout=True)
        set_test_plus_result_transport(transport)
        processed = process_discovered_plus_control(self.layer, "unc-1")
        self.assertTrue(processed["ok"], processed)
        delivered = deliver_plus_results(self.layer, transport)
        self.assertTrue(delivered[0]["unknown"])
        row = dict(self.layer.conn.execute("SELECT * FROM plus_result_outbox").fetchone())
        self.assertEqual(row["status"], "unknown")
        again = deliver_plus_results(self.layer, MemoryPlusResultTransport())
        self.assertEqual(again, [])
        reconciled = reconcile_plus_result_outbox(
            self.layer,
            [
                {
                    "id": "gmail-res-1",
                    "subject": row["subject"],
                    "body": row["body"],
                    "provider_message_id": "gmail-res-1",
                }
            ],
        )
        self.assertTrue(reconciled[0]["recovered"])
        self.assertFalse(reconciled[0]["retried"])
        self.assertEqual(self.layer.conn.execute("SELECT status FROM plus_result_outbox").fetchone()["status"], "sent")

    def test_result_loops_and_contactus_stay_untouched(self) -> None:
        client = FakePlusLoopClient()
        self._install_control("ok-1", client)
        result_mail = _plus_raw_with_headers(
            "loop-res",
            f"{MARKER_PLUS_RESULT} loop",
            f"{MARKER_PLUS_RESULT}\nCONTROL_ID=loop\n",
            self.sent_at,
            ["SENT", LEAD_DESK_CONTROL_LABEL_ID, LEAD_DESK_RESULTS_LABEL_ID],
        )
        result_mail["headers"] = [
            ("From", ALLOWED_SENDER),
            ("To", LEAD_DESK_PLUS_RESULTS_MAILBOX),
            ("Subject", f"{MARKER_PLUS_RESULT} loop"),
        ]
        client.messages["loop-res"] = result_mail
        save_plus_cursor(self.layer, "10")
        client.history_pages = [
            {
                "historyId": "12",
                "history": [
                    {"messagesAdded": [{"message": {"id": "ok-1"}}]},
                    {"messagesAdded": [{"message": {"id": "loop-res"}}]},
                ],
            }
        ]
        result = poll_plus_controls_once(self.layer, client=client)
        skipped = {item["id"]: item["reason"] for item in result["discovery"]["skipped"]}
        self.assertEqual(skipped.get("loop-res"), "plus_results_loop_excluded")
        self.assertEqual(result["contactus_outbox_delta"], 0)
        self.assertTrue(result["contactus_watch_unchanged"])
        self.assertEqual(self.store.get_watch(MAILBOX), self.watch_before)
        self.assertEqual(list(self.layer.conn.execute("SELECT kind FROM desk_result_outbox").fetchall()), [])
        self.assertNotEqual(get_plus_cursor(self.layer)["cursor_key"], MAILBOX)
        self.assertEqual(get_plus_cursor(self.layer)["cursor_key"], PLUS_CURSOR_KEY)

    def test_normal_mail_and_contactus_history_helper_untouched(self) -> None:
        self.assertEqual(self.store.get_receipt(MAILBOX, "plus-in-loop")["classification"], "new_message")
        self.assertIn("messageAdded", str(ReadOnlyGmail.history.__code__.co_consts))
        self.assertNotIn("labelAdded", str(ReadOnlyGmail.history.__code__.co_consts))
        self.assertIn("in:sent", plus_history_query())
        self.assertNotIn(MAILBOX, plus_history_query())

    def test_preflight_reports_blockers_without_settings_scope(self) -> None:
        set_test_plus_result_ready(False)
        set_test_plus_result_transport(None)
        set_test_plus_preflight(
            labels=[
                {"id": LEAD_DESK_CONTROL_LABEL_ID, "name": "B&T Lead Desk/Control"},
                {"id": LEAD_DESK_RESULTS_LABEL_ID, "name": "B&T Lead Desk/Results"},
            ],
            filters="forbidden",
            profile={"emailAddress": ALLOWED_SENDER, "historyId": "9"},
        )
        report = plus_control_preflight()
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["filters"]["accessible"])
        self.assertFalse(report["permissions"]["mail_settings_scope_requested"])
        self.assertFalse(report["permissions"]["filters_or_labels_changed"])
        self.assertTrue(any("plus_result" in item or "not_ready" in item or "disabled" in item for item in report["activation_blockers"]))
        self.assertTrue(report["discovery"]["isolated_from_contactus"])
        self.assertEqual(report["discovery"]["stale_excluded"], STALE_PLUS_CONTROL_ID)
        self.assertFalse(report["exactly_once_delivery"])

    def test_combined_result_has_binding_and_no_contactus_case_email(self) -> None:
        client = FakePlusLoopClient()
        self._install_control("bind-1", client)
        result = process_discovered_plus_control(self.layer, "bind-1")
        self.assertTrue(result["ok"], result)
        row = dict(self.layer.conn.execute("SELECT * FROM plus_result_outbox").fetchone())
        self.assertEqual(row["kind"], KIND_PLUS_COMBINED)
        self.assertIn(MARKER_PLUS_RESULT, row["subject"])
        self.assertIn("Draft updated to v2. Nothing sent.", row["body"])
        self.assertIn("PACKET_HASH=", row["body"])
        self.assertIn("Loop revision", row["body"])
        self.assertNotIn("BT-INTAKE-PROOF-DESK-CASE-E9A8", row["body"])
        self.assertEqual(list(self.layer.conn.execute("SELECT * FROM desk_result_outbox").fetchall()), [])
        mail = result["result_email"]
        self.assertEqual(mail["from"], ALLOWED_SENDER)
        self.assertEqual(mail["to"], LEAD_DESK_PLUS_RESULTS_MAILBOX)
        self.assertEqual(mail["cc"], "")

    def test_channel_ready_helper_does_not_use_contactus_or_readonly(self) -> None:
        set_test_plus_result_ready(None)
        set_test_plus_result_transport(None)
        ready = plus_result_channel_ready()
        self.assertFalse(ready["ready"])
        self.assertEqual(ready["blocker"], "plus_result_send_token_missing")
        self.assertFalse(ready["uses_contactus_credentials"])
        self.assertFalse(ready["widens_readonly"])


if __name__ == "__main__":
    unittest.main()
