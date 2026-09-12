import base64
import json
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
from bt_intake_proof.desk_bridge import (
    compute_packet_binding,
    ensure_bridge_tables,
    format_control_mail,
    process_control_mail,
)
from bt_intake_proof.desk_control import INTENT_HOLD, INTENT_REVISE
from bt_intake_proof.desk_plus_discover import (
    PlusHistoryExpired,
    discover_plus_controls,
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
    plus_result_payload_digest,
    reconcile_plus_result_outbox,
    set_test_fail_after_result_insert,
    set_test_plus_result_ready,
    set_test_plus_result_sent_lookup,
    set_test_plus_result_transport,
    set_test_plus_sender_identity,
)
from bt_intake_proof.desk_plus_store import (
    PLUS_CURSOR_KEY,
    STATUS_AWAITING_LABEL,
    STATUS_PROCESSING,
    CLAIM_LEASE,
    ensure_plus_tables,
    get_plus_cursor,
    get_seen,
    pending_seen_ids,
    save_plus_cursor,
)
from bt_intake_proof.gmail_readonly import ReadOnlyGmail
from bt_intake_proof.phasee_constants import PHASEE_CASE_MARKER
from bt_intake_proof.send_bind import ensure_send_tables
from bt_intake_proof.store import ReceiptStore, body_hash


def _ms(value: datetime) -> str:
    return str(int(value.timestamp() * 1000))


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


def _raw_plus_message(
    message_id: str,
    *,
    subject: str,
    body: str,
    sender: str = ALLOWED_SENDER,
    to: str = LEAD_DESK_PLUS_MAILBOX,
    internal: datetime,
    labels: list[str] | None = None,
) -> dict:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = f"<{message_id}@desk.btpestcontrol.com>"
    msg["Date"] = "Sat, 12 Sep 2026 21:00:00 +0000"
    msg.set_content(body)
    return {
        "id": message_id,
        "labelIds": list(labels if labels is not None else ["SENT"]),
        "internalDate": _ms(internal),
        "raw": base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii"),
    }


class FakeDanielPlusClient:
    def __init__(self, *, profile_email: str = ALLOWED_SENDER, messages: dict | None = None) -> None:
        self.profile_email = profile_email
        self.messages = dict(messages or {})

    def get_profile(self) -> dict:
        return {"emailAddress": self.profile_email}

    def get_message(self, message_id: str, fmt: str = "raw") -> dict:
        return dict(self.messages[message_id])


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
        self.search_pages: list[list[str]] | None = None
        self.search_calls: list[dict] = []
        self.raw_fetches: list[str] = []
        self.metadata_fetches: list[str] = []
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

    def search_messages(
        self,
        query: str,
        max_results: int = 10,
        label_ids: list[str] | None = None,
        page_token: str | None = None,
    ):
        self.searches.append(query)
        self.search_calls.append(
            {"q": query, "max_results": max_results, "label_ids": label_ids, "page_token": page_token}
        )
        if self.search_pages is not None:
            idx = int(page_token or 0)
            page = self.search_pages[idx] if 0 <= idx < len(self.search_pages) else []
            nxt = str(idx + 1) if idx + 1 < len(self.search_pages) else None
            return {"messages": [{"id": item} for item in page], "nextPageToken": nxt}
        return [{"id": item} for item in self.search_ids[:max_results]]

    def get_message(self, message_id: str, fmt: str = "raw") -> dict:
        raw = dict(self.messages[message_id])
        if fmt == "metadata":
            self.metadata_fetches.append(message_id)
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
        self.raw_fetches.append(message_id)
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
        ensure_bridge_tables(self.layer)
        ensure_plus_tables(self.layer)
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
        set_test_plus_result_sent_lookup(None)
        set_test_plus_sender_identity(None)
        set_test_fail_after_result_insert(False)
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
        set_test_plus_result_sent_lookup(None)
        set_test_plus_sender_identity(None)
        set_test_fail_after_result_insert(False)
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

        seen_urls: list[str] = []

        def _get(url: str, _token: str) -> dict:
            seen_urls.append(url)
            if "pageToken=p2" in url:
                return pages[1]
            return pages[0]

        client = type("Tok", (), {"access_token": "tok"})()
        with patch("bt_intake_proof.desk_plus_discover._get_json", side_effect=_get):
            merged = fetch_plus_history(client, "1")
        ids = extract_plus_history_ids(merged)
        self.assertEqual([item["id"] for item in ids], ["page-a", "page-b"])
        self.assertEqual(merged["historyId"], "3")
        self.assertEqual(len(seen_urls), 2)
        self.assertIn("historyTypes=messageAdded", seen_urls[0])
        self.assertIn("historyTypes=labelAdded", seen_urls[0])
        self.assertIn("pageToken=p2", seen_urls[1])

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
        self.assertNotIn("label:", client.searches[0])
        self.assertNotIn(LEAD_DESK_CONTROL_LABEL_ID, client.searches[0])
        self.assertTrue(any(LEAD_DESK_CONTROL_LABEL_ID in (call.get("label_ids") or []) for call in client.search_calls))
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

        def _lookup(_row):
            return {
                "ok": True,
                "matches": [
                    {
                        "id": "gmail-res-1",
                        "from": ALLOWED_SENDER,
                        "to": [LEAD_DESK_PLUS_RESULTS_MAILBOX],
                        "cc": [],
                        "bcc": [],
                        "subject": row["subject"],
                        "body": row["body"],
                        "rfc_message_id": row["rfc_message_id"],
                        "provider_message_id": "gmail-res-1",
                    }
                ],
            }

        set_test_plus_result_sent_lookup(_lookup)
        reconciled = reconcile_plus_result_outbox(self.layer, [{"subject": row["subject"], "body": "ignored"}])
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

    def _expire_claim(self, gmail_message_id: str) -> None:
        stale = (datetime.now(timezone.utc) - CLAIM_LEASE - timedelta(seconds=5)).isoformat()
        self.layer.conn.execute(
            "UPDATE plus_control_seen SET claimed_at = ? WHERE gmail_message_id = ?",
            (stale, gmail_message_id),
        )

    def test_format_failure_inside_persist_rolls_back_draft_nonce_result(self) -> None:
        client = FakePlusLoopClient()
        self._install_control("atom-fmt", client)
        before = int(self.layer.get_case(self.case_id)["draft_version"])
        nonce_before = self.layer.latest_draft(self.case_id)["nonce"]
        with patch(
            "bt_intake_proof.desk_plus_result_send.format_plus_combined_result",
            side_effect=RuntimeError("injected format boom"),
        ):
            with self.assertRaises(RuntimeError):
                process_discovered_plus_control(self.layer, "atom-fmt")
        self.assertEqual(int(self.layer.get_case(self.case_id)["draft_version"]), before)
        self.assertEqual(self.layer.latest_draft(self.case_id)["nonce"], nonce_before)
        self.assertEqual(self.layer.conn.execute("SELECT COUNT(*) AS n FROM plus_result_outbox").fetchone()["n"], 0)
        self.assertEqual(self.layer.conn.execute("SELECT COUNT(*) AS n FROM desk_control_consumed").fetchone()["n"], 0)
        self.assertEqual(get_seen(self.layer, "atom-fmt")["status"], STATUS_PROCESSING)
        self.assertNotIn("atom-fmt", pending_seen_ids(self.layer))

    def test_fail_after_result_insert_before_commit_rolls_back_unit(self) -> None:
        client = FakePlusLoopClient()
        self._install_control("atom-ins", client)
        before = int(self.layer.get_case(self.case_id)["draft_version"])
        set_test_fail_after_result_insert(True)
        try:
            with self.assertRaises(RuntimeError):
                process_discovered_plus_control(self.layer, "atom-ins")
        finally:
            set_test_fail_after_result_insert(False)
        self.assertEqual(int(self.layer.get_case(self.case_id)["draft_version"]), before)
        self.assertEqual(self.layer.conn.execute("SELECT COUNT(*) AS n FROM plus_result_outbox").fetchone()["n"], 0)
        self.assertEqual(self.layer.conn.execute("SELECT COUNT(*) AS n FROM desk_control_consumed").fetchone()["n"], 0)
        self.assertEqual(get_seen(self.layer, "atom-ins")["status"], STATUS_PROCESSING)

    def test_history_events_checkpointed_before_cursor_survives_metadata_death(self) -> None:
        client = FakePlusLoopClient()
        self._install_control("review-control", client)
        save_plus_cursor(self.layer, "10")
        client.history_pages = [
            {
                "historyId": "20",
                "history": [{"messagesAdded": [{"message": {"id": "review-control"}}]}],
            }
        ]
        with patch(
            "bt_intake_proof.desk_plus_discover._get_metadata",
            side_effect=RuntimeError("process death during metadata"),
        ):
            discover_plus_controls(self.layer, client=client)
        self.assertEqual(str(get_plus_cursor(self.layer)["history_id"]), "20")
        self.assertIsNotNone(get_seen(self.layer, "review-control"))
        client.history_pages = []
        recovered = poll_plus_controls_once(self.layer, client=client)
        self.assertTrue(
            any(item.get("ok") and item.get("control_gmail_id") == "review-control" for item in recovered["processed"]),
            recovered,
        )
        self.assertEqual(int(self.layer.get_case(self.case_id)["draft_version"]), 2)

    def test_lease_recovers_death_before_save_and_after_save_before_seen(self) -> None:
        client = FakePlusLoopClient()
        self._install_control("lease-before", client)
        before = int(self.layer.get_case(self.case_id)["draft_version"])
        with patch(
            "bt_intake_proof.desk_plus_result_send.format_plus_combined_result",
            side_effect=RuntimeError("death before save"),
        ):
            with self.assertRaises(RuntimeError):
                process_discovered_plus_control(self.layer, "lease-before")
        self.assertEqual(int(self.layer.get_case(self.case_id)["draft_version"]), before)
        self.assertEqual(get_seen(self.layer, "lease-before")["status"], STATUS_PROCESSING)
        self._expire_claim("lease-before")
        self.assertIn("lease-before", pending_seen_ids(self.layer))
        replay = process_discovered_plus_control(self.layer, "lease-before")
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(int(self.layer.get_case(self.case_id)["draft_version"]), 2)

        client2 = FakePlusLoopClient()
        mail2 = format_control_mail(
            INTENT_REVISE,
            compute_packet_binding(self.layer.get_case(self.case_id), self.layer.latest_draft(self.case_id)),
            note="DRAFT - NOT SENT\n\nSecond lease revision.",
            transport=TRANSPORT_PLUS,
        )
        raw2 = _plus_raw_with_headers(
            "lease-after",
            mail2["subject"],
            mail2["body"],
            self.sent_at,
            ["SENT", LEAD_DESK_CONTROL_LABEL_ID],
        )
        client2.messages["lease-after"] = raw2
        set_test_plus_client(client2)
        set_test_plus_discover_client(client2)
        import bt_intake_proof.desk_plus_loop as loop_mod

        real_update = loop_mod.update_seen

        def _boom(layer, gmail_message_id, **kwargs):
            if kwargs.get("status") == "processed":
                raise RuntimeError("death after save before seen")
            return real_update(layer, gmail_message_id, **kwargs)

        with patch.object(loop_mod, "update_seen", side_effect=_boom):
            with self.assertRaises(RuntimeError):
                process_discovered_plus_control(self.layer, "lease-after")
        self.assertEqual(int(self.layer.get_case(self.case_id)["draft_version"]), 3)
        self.assertEqual(self.layer.conn.execute("SELECT COUNT(*) AS n FROM plus_result_outbox").fetchone()["n"], 2)
        self.assertEqual(get_seen(self.layer, "lease-after")["status"], STATUS_PROCESSING)
        self._expire_claim("lease-after")
        again = process_discovered_plus_control(self.layer, "lease-after")
        self.assertTrue(again.get("replayed") or again.get("ok"), again)
        self.assertEqual(int(self.layer.get_case(self.case_id)["draft_version"]), 3)
        self.assertEqual(self.layer.conn.execute("SELECT COUNT(*) AS n FROM plus_result_outbox").fetchone()["n"], 2)

    def test_normal_mail_stays_awaiting_label_without_raw_fetch(self) -> None:
        client = FakePlusLoopClient()
        ordinary = _plus_raw_with_headers(
            "normal-mail",
            "hello",
            "ordinary customer mail",
            self.sent_at,
            ["SENT"],
        )
        client.messages["normal-mail"] = ordinary
        set_test_plus_client(client)
        set_test_plus_discover_client(client)
        save_plus_cursor(self.layer, "10")
        client.history_pages = [
            {"historyId": "11", "history": [{"messagesAdded": [{"message": {"id": "normal-mail"}}]}]}
        ]
        before = int(self.layer.get_case(self.case_id)["draft_version"])
        result = poll_plus_controls_once(self.layer, client=client)
        self.assertEqual(get_seen(self.layer, "normal-mail")["status"], STATUS_AWAITING_LABEL)
        self.assertNotIn("normal-mail", result["discovery"]["candidates"])
        self.assertNotIn("normal-mail", client.raw_fetches)
        self.assertEqual(int(self.layer.get_case(self.case_id)["draft_version"]), before)

    def test_control_label_delay_then_removal(self) -> None:
        client = FakePlusLoopClient()
        delayed = _plus_raw_with_headers(
            "label-delay",
            self.mail["subject"],
            self.mail["body"],
            self.sent_at,
            ["SENT"],
        )
        client.messages["label-delay"] = delayed
        set_test_plus_client(client)
        set_test_plus_discover_client(client)
        save_plus_cursor(self.layer, "10")
        client.history_pages = [
            {"historyId": "12", "history": [{"messagesAdded": [{"message": {"id": "label-delay"}}]}]}
        ]
        first = poll_plus_controls_once(self.layer, client=client)
        self.assertEqual(get_seen(self.layer, "label-delay")["status"], STATUS_AWAITING_LABEL)
        self.assertFalse(any(item.get("ok") for item in first["processed"]))
        client.messages["label-delay"]["labelIds"] = ["SENT", LEAD_DESK_CONTROL_LABEL_ID]
        client.history_pages = []
        authorized = discover_plus_controls(self.layer, client=client)
        self.assertIn("label-delay", authorized["candidates"])
        client.messages["label-delay"]["labelIds"] = ["SENT"]
        removed = process_discovered_plus_control(self.layer, "label-delay", client=client)
        self.assertTrue(removed.get("awaiting_label"), removed)
        self.assertFalse(removed.get("ok"))
        self.assertNotIn("label-delay", client.raw_fetches)
        self.assertEqual(int(self.layer.get_case(self.case_id)["draft_version"]), 1)
        client.messages["label-delay"]["labelIds"] = ["SENT", LEAD_DESK_CONTROL_LABEL_ID]
        second = poll_plus_controls_once(self.layer, client=client)
        self.assertTrue(any(item.get("ok") and item.get("control_gmail_id") == "label-delay" for item in second["processed"]), second)

    def test_changed_control_label_id_resolved_by_name(self) -> None:
        client = FakePlusLoopClient()
        new_id = "Label_CHANGED_CONTROL"
        client.labels = [
            {"id": new_id, "name": "B&T Lead Desk/Control"},
            {"id": LEAD_DESK_RESULTS_LABEL_ID, "name": "B&T Lead Desk/Results"},
        ]
        raw = _plus_raw_with_headers(
            "changed-id",
            self.mail["subject"],
            self.mail["body"],
            self.sent_at,
            ["SENT", new_id],
        )
        client.messages["changed-id"] = raw
        set_test_plus_client(client)
        set_test_plus_discover_client(client)
        save_plus_cursor(self.layer, "10")
        client.history_error = PlusHistoryExpired("historyId no longer valid")
        client.search_ids = ["changed-id"]
        result = poll_plus_controls_once(self.layer, client=client)
        self.assertTrue(client.search_calls)
        self.assertNotIn("Label_", client.searches[0])
        self.assertIn(new_id, client.search_calls[0].get("label_ids") or [])
        self.assertTrue(any(item.get("ok") for item in result["processed"]), result)

    def test_recovery_paginates_beyond_one_page(self) -> None:
        client = FakePlusLoopClient()
        set_test_plus_client(client)
        set_test_plus_discover_client(client)
        save_plus_cursor(self.layer, "10")
        client.history_error = PlusHistoryExpired("historyId no longer valid")
        client.search_pages = [["page-a"], ["page-b"], ["page-c"]]
        report = discover_plus_controls(self.layer, client=client)
        self.assertGreaterEqual(len(client.search_calls), 3, client.search_calls)
        self.assertIsNotNone(get_seen(self.layer, "page-a"))
        self.assertIsNotNone(get_seen(self.layer, "page-b"))
        self.assertIsNotNone(get_seen(self.layer, "page-c"))
        self.assertNotIn("label:", report.get("reconcile_query") or "")

    def test_reconcile_keeps_ambiguous_sends_unknown(self) -> None:
        client = FakePlusLoopClient()
        self._install_control("res-amb", client)
        processed = process_discovered_plus_control(self.layer, "res-amb")
        self.assertTrue(processed["ok"], processed)
        self.layer.conn.execute("UPDATE plus_result_outbox SET status = 'sending'")
        row = dict(self.layer.conn.execute("SELECT * FROM plus_result_outbox").fetchone())

        set_test_plus_result_sent_lookup(lambda _row: {"ok": True, "matches": []})
        empty = reconcile_plus_result_outbox(self.layer, [])
        self.assertTrue(empty[0]["unknown"])
        self.assertFalse(empty[0]["retried"])
        self.assertEqual(empty[0]["reason"], "still_unconfirmed")
        self.assertEqual(self.layer.conn.execute("SELECT status FROM plus_result_outbox").fetchone()["status"], "unknown")
        self.assertEqual(deliver_plus_results(self.layer, MemoryPlusResultTransport()), [])

        def _wrong_to(_row):
            return {
                "ok": True,
                "matches": [
                    {
                        "from": ALLOWED_SENDER,
                        "to": ["amy@example.com"],
                        "subject": row["subject"],
                        "body": row["body"],
                        "rfc_message_id": row["rfc_message_id"],
                        "provider_message_id": "wrong-to",
                    }
                ],
            }

        self.layer.conn.execute("UPDATE plus_result_outbox SET status = 'sending'")
        set_test_plus_result_sent_lookup(_wrong_to)
        wrong = reconcile_plus_result_outbox(self.layer)
        self.assertEqual(wrong[0]["reason"], "still_unconfirmed")
        self.assertEqual(self.layer.conn.execute("SELECT status FROM plus_result_outbox").fetchone()["status"], "unknown")

        def _wrong_body(_row):
            return {
                "ok": True,
                "matches": [
                    {
                        "from": ALLOWED_SENDER,
                        "to": [LEAD_DESK_PLUS_RESULTS_MAILBOX],
                        "subject": row["subject"],
                        "body": "different body",
                        "rfc_message_id": row["rfc_message_id"],
                        "provider_message_id": "wrong-body",
                    }
                ],
            }

        self.layer.conn.execute("UPDATE plus_result_outbox SET status = 'unknown'")
        set_test_plus_result_sent_lookup(_wrong_body)
        body = reconcile_plus_result_outbox(self.layer)
        self.assertEqual(body[0]["reason"], "still_unconfirmed")

        exact = {
            "from": ALLOWED_SENDER,
            "to": [LEAD_DESK_PLUS_RESULTS_MAILBOX],
            "cc": [],
            "bcc": [],
            "subject": row["subject"],
            "body": row["body"],
            "rfc_message_id": row["rfc_message_id"],
            "provider_message_id": "dup-1",
        }
        set_test_plus_result_sent_lookup(lambda _row: {"ok": True, "matches": [exact, {**exact, "provider_message_id": "dup-2"}]})
        dup = reconcile_plus_result_outbox(self.layer)
        self.assertEqual(dup[0]["reason"], "ambiguous_provider_match")
        self.assertFalse(dup[0]["retried"])

        def _boom(_row):
            raise RuntimeError("lookup exploded")

        set_test_plus_result_sent_lookup(_boom)
        crashed = reconcile_plus_result_outbox(self.layer)
        self.assertEqual(crashed[0]["reason"], "plus_result_lookup_error")
        self.assertFalse(crashed[0]["retried"])
        self.assertEqual(self.layer.conn.execute("SELECT status FROM plus_result_outbox").fetchone()["status"], "unknown")

    def test_blocked_result_returns_to_pending_when_sender_ready(self) -> None:
        client = FakePlusLoopClient()
        self._install_control("res-block", client)
        processed = process_discovered_plus_control(self.layer, "res-block")
        self.assertTrue(processed["ok"], processed)
        self.layer.conn.execute("UPDATE plus_result_outbox SET status = 'blocked'")
        from bt_intake_proof.desk_plus_loop import recover_plus_result_sends

        recovered = recover_plus_result_sends(self.layer)
        self.assertGreaterEqual(recovered["unblocked_results"], 1)
        self.assertTrue(any(item.get("ok") for item in recovered["delivered"]))
        self.assertEqual(self.layer.conn.execute("SELECT status FROM plus_result_outbox").fetchone()["status"], "sent")

    def test_result_mime_includes_persisted_rfc_message_id(self) -> None:
        from email import message_from_bytes

        from bt_intake_proof.bounded_send import mime_from_binding

        client = FakePlusLoopClient()
        self._install_control("mime-1", client)
        processed = process_discovered_plus_control(self.layer, "mime-1")
        self.assertTrue(processed["ok"], processed)
        row = dict(self.layer.conn.execute("SELECT * FROM plus_result_outbox").fetchone())
        self.assertTrue(row["rfc_message_id"])
        self.assertTrue(row["body_digest"])
        self.assertTrue(row["payload_digest"])
        raw = mime_from_binding(
            {
                "from_addr": ALLOWED_SENDER,
                "to_addr": LEAD_DESK_PLUS_RESULTS_MAILBOX,
                "subject": row["subject"],
                "body": row["body"],
                "rfc_message_id": row["rfc_message_id"],
            }
        )
        parsed = message_from_bytes(raw)
        self.assertIn(row["rfc_message_id"].encode("ascii"), raw)
        self.assertEqual(
            str(parsed["Message-ID"] or "").replace("\n", "").replace("\r", "").replace(" ", ""),
            row["rfc_message_id"],
        )
        self.assertEqual(plus_result_payload_digest(
            {"from": ALLOWED_SENDER, "to": LEAD_DESK_PLUS_RESULTS_MAILBOX, "cc": "", "bcc": "", "subject": row["subject"], "body": row["body"]},
            row["rfc_message_id"],
        ), row["payload_digest"])

    def test_sender_readiness_uses_live_identity_not_token_file(self) -> None:
        from bt_intake_proof.desk_plus_result_send import GMAIL_SEND_SCOPE
        from bt_intake_proof.gmail_readonly import GmailAuthError

        dest = Path(self.tmp.name) / "plus_send_token.json"
        dest.write_text(
            json.dumps(
                {
                    "email": ALLOWED_SENDER,
                    "scopes": [GMAIL_SEND_SCOPE],
                    "refresh_token": "not-live-proof",
                }
            ),
            encoding="utf-8",
        )
        set_test_plus_result_ready(None)
        set_test_plus_result_transport(None)
        with patch.dict("os.environ", {"BT_DANIEL_PLUS_RESULT_SEND_TOKEN": str(dest)}):
            set_test_plus_sender_identity(GmailAuthError("invalid_grant"))
            blocked = plus_result_channel_ready()
            self.assertFalse(blocked["ready"])
            self.assertEqual(blocked["blocker"], "plus_result_sender_unusable")
            set_test_plus_sender_identity({"email": "amy@example.com", "scopes": [GMAIL_SEND_SCOPE]})
            wrong = plus_result_channel_ready()
            self.assertFalse(wrong["ready"])
            set_test_plus_sender_identity({"email": ALLOWED_SENDER, "scopes": [GMAIL_SEND_SCOPE]})
            ready = plus_result_channel_ready()
            self.assertTrue(ready["ready"])
            self.assertEqual(ready["identity_via"], "test_tokeninfo")

    def test_preflight_requires_results_label_and_label_lookup(self) -> None:
        set_test_plus_result_ready(True)
        set_test_plus_preflight(
            labels=[{"id": LEAD_DESK_CONTROL_LABEL_ID, "name": "B&T Lead Desk/Control"}],
            filters="forbidden",
            profile={"emailAddress": ALLOWED_SENDER, "historyId": "9"},
        )
        missing = plus_control_preflight()
        self.assertEqual(missing["status"], "BLOCKED")
        self.assertIn("results_label_missing", missing["activation_blockers"])
        set_test_plus_preflight(
            labels="fail",
            filters="forbidden",
            profile={"emailAddress": ALLOWED_SENDER, "historyId": "9"},
        )
        failed = plus_control_preflight()
        self.assertEqual(failed["status"], "BLOCKED")
        self.assertIn("plus_label_lookup_failed", failed["activation_blockers"])
        set_test_plus_preflight(
            labels=[
                {"id": LEAD_DESK_CONTROL_LABEL_ID, "name": "B&T Lead Desk/Control"},
                {"id": LEAD_DESK_RESULTS_LABEL_ID, "name": "B&T Lead Desk/Results"},
            ],
            filters="forbidden",
            profile={"emailAddress": ALLOWED_SENDER, "historyId": "9"},
        )
        ready = plus_control_preflight()
        self.assertEqual(ready["status"], "READY")
        self.assertTrue(ready["discovery"]["ready"])
        self.assertNotIn("Label_", ready["discovery"]["query"])


if __name__ == "__main__":
    unittest.main()
