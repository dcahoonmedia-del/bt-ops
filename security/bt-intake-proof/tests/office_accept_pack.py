"""Isolated office-ownership acceptance pack. Synthetic records only.

Does not open production SQLite, send mail, write Fieldwork, or grow backend
phrase lists. ChatGPT interpretation in the walkthrough is simulated.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from bt_intake_proof.bounded_send import MemorySendTransport, execute_desk_queued_sends, execute_due_sends
from bt_intake_proof.cases import (
    APPROVAL_APPROVED,
    APPROVAL_PENDING,
    DECISION_APPROVE,
    DRAFT_NOT_SENT,
    CaseLayer,
)
from bt_intake_proof.constants import ALLOWED_SENDER, CLASS_NEW, CLASS_REPLY, DETECTION_EVENT_DRIVEN, MAILBOX
from bt_intake_proof.desk_bridge import (
    compute_packet_binding,
    format_control_mail,
    install_desk_send_draft,
    process_control_mail,
)
from bt_intake_proof.desk_control import INTENT_APPROVE_SEND, INTENT_HOLD, INTENT_OFFICE, INTENT_REVISE
from bt_intake_proof.desk_origin import daniel_origin_evidence
from bt_intake_proof.desk_sent_proof import fixture_sent_lookup
from bt_intake_proof.lead_desk import LeadDesk
from bt_intake_proof.production_intake import captured_event, classify_after_capture
from bt_intake_proof.review import format_review_email
from bt_intake_proof.send_bind import ensure_send_tables, latest_action, queue_desk_send, queue_phasee_send
from bt_intake_proof.store import ReceiptStore, body_hash

MARKER_NEW = "BT-INTAKE-PROOF-CASEMGR-OFFICE-NEW-E9A8"
MARKER_EXISTING = "BT-INTAKE-PROOF-CASEMGR-OFFICE-EXISTING-E9A8"
MARKER_REPLY = "BT-INTAKE-PROOF-CASEMGR-OFFICE-REPLY-E9A8"

SAFE_NEW_DRAFT = (
    f"{DRAFT_NOT_SENT}\n\n"
    "Thanks for writing about ants in the kitchen in Jacksonville. "
    "I have your note. The office will call to talk through options. "
    "Reply with a callback number if you have a preferred one. "
    "This is not a quote and not a scheduled visit."
)
SAFE_EXISTING_DRAFT = (
    f"{DRAFT_NOT_SENT}\n\n"
    "Thanks for telling us the mice are back in the garage. "
    "I have this as an existing-service follow-up, not a new sales lead. "
    "The office will review the account and call you. "
    "This is not a quote and not a scheduled visit."
)
REVISED_DRAFT = (
    f"{DRAFT_NOT_SENT}\n\n"
    "Thanks. Please reply with a callback number and we will have the office follow up."
)
INVENTED_DRAFT = (
    f"{DRAFT_NOT_SENT}\n\n"
    "We can do Tuesday at 3pm for $999. You are booked."
)
_INVENTED_PRICE = re.compile(r"\$\s*\d")
_APPOINTMENT_PROMISE = re.compile(
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b.{0,40}\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b",
    re.I,
)


def pack_flags_invented_promises(text: str) -> bool:
    """Reviewer-side check for this pack only. Not backend speech parsing."""
    return bool(_INVENTED_PRICE.search(text or "") or _APPOINTMENT_PROMISE.search(text or ""))


def _receipt(message_id: str, *, thread_id: str, marker: str, body: str, subject: str, classification: str = CLASS_NEW) -> dict[str, Any]:
    return {
        "eligible": True,
        "mailbox": MAILBOX,
        "gmail_message_id": message_id,
        "thread_id": thread_id,
        "rfc_message_id": f"<{message_id}@bt>",
        "sender": "neighbor@example.com",
        "recipients": [MAILBOX],
        "subject": subject,
        "gmail_received_at": "2026-09-12T18:00:00+00:00",
        "detected_at": "2026-09-12T18:00:05+00:00",
        "body_text": body,
        "raw_message": body,
        "body_hash": body_hash(body),
        "labels_before": ["INBOX", "UNREAD"],
        "labels_after": ["INBOX", "UNREAD"],
        "classification": classification,
        "test_marker": marker,
        "reasons": [],
    }


def _commit(store: ReceiptStore, receipt: dict[str, Any]) -> dict[str, Any]:
    store.commit_notification(
        mailbox=MAILBOX,
        history_id=str(receipt["gmail_message_id"]),
        detection_path=DETECTION_EVENT_DRIVEN,
        pubsub_message_id=f"n-{receipt['gmail_message_id']}",
        receipts=[receipt],
    )
    row = store.get_receipt(MAILBOX, receipt["gmail_message_id"])
    assert row is not None
    return row


def _apply_control(layer: CaseLayer, intent: str, binding: dict[str, Any], **extra) -> dict[str, Any]:
    mail = format_control_mail(intent, binding, owner=extra.get("owner"), note=extra.get("note"))
    mid = extra.get("gmail_message_id", f"ctrl-{intent}-{binding.get('nonce')}")
    body = extra.get("body", mail["body"])
    rfc = extra.get("rfc_message_id", f"<{mid}@desk.btpestcontrol.com>")
    received = extra.get("received_at", "2026-09-12T18:10:00+00:00")
    evidence = extra.get("provider_evidence", daniel_origin_evidence(mid))
    if evidence is not None:
        evidence = {**evidence, "rfc_message_id": rfc, "received_at": received, "recipients": [MAILBOX]}
    lookup = extra.get("sent_lookup")
    if lookup is None:
        lookup = fixture_sent_lookup(mail["subject"], body, rfc_message_id=rfc, received_at=received)
    return process_control_mail(
        layer,
        sender=extra.get("sender", ALLOWED_SENDER),
        subject=mail["subject"],
        body=body,
        gmail_message_id=mid,
        provider_evidence=evidence,
        rfc_message_id=rfc,
        recipients=[MAILBOX],
        received_at=received,
        sent_lookup=lookup,
    )


def _scenario(name: str, status: str, **extra) -> dict[str, Any]:
    return {"name": name, "status": status, **extra}


def run_office_accept_pack(store_path: Path) -> dict[str, Any]:
    """Exercise the five acceptance scenarios on a throwaway store."""
    store = ReceiptStore(store_path)
    layer = CaseLayer(store)
    ensure_send_tables(layer)
    scenarios: list[dict[str, Any]] = []
    try:
        new_row = _commit(
            store,
            _receipt(
                "office-new-1",
                thread_id="thr-office-new",
                marker=MARKER_NEW,
                subject=f"{MARKER_NEW} ants in kitchen",
                body="Hi, ants in the kitchen in Jacksonville. What do you recommend?",
            ),
        )
        opened_new = layer.upsert_from_receipt(new_row)
        saved_new = layer.save_draft(
            opened_new["case_id"],
            {
                "classification": "new_customer_lead",
                "known_facts": ["Jacksonville kitchen ants", "email inquiry"],
                "missing_info": ["callback number"],
                "recommended_next_step": "office callback; no quote yet",
                "proposed_response": SAFE_NEW_DRAFT,
                "channel": "email",
                "judgment_needed": "Daniel reviews wording only. No price or appointment is offered.",
                "reasoning_summary": "New inquiry. Do not invent pricing or book a time.",
            },
            "nonce-office-new",
        )
        review_new = format_review_email(layer.review_packet(opened_new["case_id"]))
        invented = layer.save_draft(
            opened_new["case_id"],
            {
                "classification": "new_customer_lead",
                "known_facts": ["Jacksonville kitchen ants"],
                "missing_info": ["callback number"],
                "recommended_next_step": "Daniel must reject invented promises",
                "proposed_response": INVENTED_DRAFT,
                "channel": "email",
                "judgment_needed": "Invented price and appointment. Do not approve or send.",
                "reasoning_summary": "Contrast draft kept visible for review, not discarded.",
            },
            "nonce-office-invented",
        )
        layer.save_draft(
            opened_new["case_id"],
            {
                "classification": "new_customer_lead",
                "known_facts": ["Jacksonville kitchen ants", "email inquiry"],
                "missing_info": ["callback number"],
                "recommended_next_step": "office callback; no quote yet",
                "proposed_response": SAFE_NEW_DRAFT,
                "channel": "email",
                "judgment_needed": "Daniel reviews wording only. No price or appointment is offered.",
                "reasoning_summary": "Restore conservative draft after contrast.",
            },
            "nonce-office-new-restored",
        )
        new_queued = queue_desk_send(layer, opened_new["case_id"])
        new_phasee = queue_phasee_send(layer, opened_new["case_id"])
        new_executed = execute_desk_queued_sends(layer, MemorySendTransport())
        due = execute_due_sends(layer, MemorySendTransport())
        new_ok = (
            opened_new.get("created")
            and saved_new["proposed_response"].startswith(DRAFT_NOT_SENT)
            and not pack_flags_invented_promises(SAFE_NEW_DRAFT)
            and pack_flags_invented_promises(INVENTED_DRAFT)
            and invented["version"] == 2
            and layer.get_case(opened_new["case_id"])["stage"] == "awaiting_review"
            and not new_queued.get("ok")
            and not new_phasee.get("ok")
            and new_executed == []
            and due == []
            and "DRAFT - NOT SENT" in review_new["body"]
        )
        scenarios.append(
            _scenario(
                "new_inquiry_reviewable_draft",
                "PASS" if new_ok else "FAIL",
                case_id=opened_new["case_id"],
                draft_version=int(layer.get_case(opened_new["case_id"])["draft_version"]),
                invented_contrast_kept=True,
                customer_send_queued=False,
                notes="Conservative draft has no price or appointment. Invented contrast stayed reviewable and was not sent.",
            )
        )

        captured = captured_event(
            mailbox=MAILBOX,
            gmail_message_id="office-exist-cap",
            thread_id="thr-office-exist",
            sender="oldcust@example.com",
            recipients=[MAILBOX],
            subject="mice are back",
            body="We have been on service for years. Mice are back in the garage.",
            known_existing_customer=True,
        )
        classified = classify_after_capture(captured["event"], suggested="existing_customer_service_issue")
        exist_row = _commit(
            store,
            _receipt(
                "office-exist-1",
                thread_id="thr-office-exist",
                marker=MARKER_EXISTING,
                subject=f"{MARKER_EXISTING} mice are back",
                body="We have been on service for years. Mice are back in the garage. Can someone look?",
            ),
        )
        opened_exist = layer.upsert_from_receipt(exist_row)
        saved_exist = layer.save_draft(
            opened_exist["case_id"],
            {
                "classification": "existing_customer_service_issue",
                "known_facts": ["existing service customer", "mice in garage"],
                "missing_info": ["callback window"],
                "recommended_next_step": "office account follow-up; not a new PestGuard pitch",
                "proposed_response": SAFE_EXISTING_DRAFT,
                "channel": "email",
                "judgment_needed": "Existing customer. Do not treat as a marketing lead.",
                "reasoning_summary": "Service issue stays eligible for draft.",
            },
            "nonce-office-exist",
        )
        exist_ok = (
            classified["disposition"] == "existing_customer_service_issue"
            and classified["visible"]
            and not classified["suppressed"]
            and not classified["dropped"]
            and opened_exist.get("created")
            and saved_exist["proposed_response"].startswith(DRAFT_NOT_SENT)
            and not pack_flags_invented_promises(SAFE_EXISTING_DRAFT)
            and layer.get_case(opened_exist["case_id"])["stage"] == "awaiting_review"
        )
        scenarios.append(
            _scenario(
                "existing_customer_service_issue_not_discarded",
                "PASS" if exist_ok else "FAIL",
                case_id=opened_exist["case_id"],
                disposition=classified["disposition"],
                visible=classified["visible"],
                suppressed=classified["suppressed"],
                notes="Existing-service inbound stayed visible and received a reviewable draft.",
            )
        )

        ownership: dict[str, Any] = {}
        for key, mid, thread in (
            ("hold", "office-hold-1", "thr-office-hold"),
            ("brenda", "office-brenda-1", "thr-office-brenda"),
            ("ally", "office-ally-1", "thr-office-ally"),
        ):
            row = _commit(
                store,
                _receipt(
                    mid,
                    thread_id=thread,
                    marker=MARKER_NEW,
                    subject=f"{MARKER_NEW} {key}",
                    body=f"Internal ownership fixture for {key}.",
                ),
            )
            opened = layer.upsert_from_receipt(row)
            install_desk_send_draft(layer, opened["case_id"], f"nonce-{key}")
            binding = compute_packet_binding(layer.get_case(opened["case_id"]), layer.latest_draft(opened["case_id"]))
            if key == "hold":
                applied = _apply_control(layer, INTENT_HOLD, binding, gmail_message_id=f"ctrl-{key}")
            else:
                applied = _apply_control(layer, INTENT_OFFICE, binding, owner=key, gmail_message_id=f"ctrl-{key}")
            send_binding = compute_packet_binding(layer.get_case(opened["case_id"]), layer.latest_draft(opened["case_id"]))
            competing = _apply_control(
                layer,
                INTENT_APPROVE_SEND,
                send_binding,
                gmail_message_id=f"ctrl-send-{key}",
            )
            queued = queue_desk_send(layer, opened["case_id"])
            executed = execute_desk_queued_sends(layer, MemorySendTransport())
            case = layer.get_case(opened["case_id"])
            ownership[key] = {
                "case_id": opened["case_id"],
                "applied_ok": bool(applied.get("ok")),
                "send_ok": bool(competing.get("ok")),
                "send_blocks": competing.get("blocks") or [],
                "queued_ok": bool(queued.get("ok")),
                "executed": executed,
                "hold": int(case.get("hold") or 0),
                "owner": case.get("owner"),
                "action": latest_action(layer, opened["case_id"]),
            }
        own_ok = (
            ownership["hold"]["applied_ok"]
            and ownership["hold"]["hold"] == 1
            and not ownership["hold"]["send_ok"]
            and "hold" in ownership["hold"]["send_blocks"]
            and ownership["brenda"]["applied_ok"]
            and ownership["brenda"]["owner"] == "brenda"
            and not ownership["brenda"]["send_ok"]
            and "office_owned" in ownership["brenda"]["send_blocks"]
            and ownership["ally"]["applied_ok"]
            and ownership["ally"]["owner"] == "ally"
            and not ownership["ally"]["send_ok"]
            and "office_owned" in ownership["ally"]["send_blocks"]
            and all(not item["queued_ok"] for item in ownership.values())
            and all(item["executed"] == [] for item in ownership.values())
            and all(item["action"] is None for item in ownership.values())
        )
        scenarios.append(
            _scenario(
                "office_ownership_and_hold_block_send",
                "PASS" if own_ok else "FAIL",
                owners=ownership,
                notes="Hold, Brenda, and Ally each blocked approve-and-send and left no queued action.",
            )
        )

        stale_row = _commit(
            store,
            _receipt(
                "office-stale-1",
                thread_id="thr-office-stale",
                marker=MARKER_NEW,
                subject=f"{MARKER_NEW} stale approval",
                body="Need a follow-up about ants.",
            ),
        )
        opened_stale = layer.upsert_from_receipt(stale_row)
        layer.save_draft(
            opened_stale["case_id"],
            {
                "classification": "new_customer_lead",
                "known_facts": ["ants"],
                "missing_info": ["phone"],
                "recommended_next_step": "callback",
                "proposed_response": SAFE_NEW_DRAFT,
                "channel": "email",
                "judgment_needed": None,
                "reasoning_summary": "version 1",
            },
            "nonce-stale-v1",
        )
        approved = layer.apply_decision(
            opened_stale["case_id"],
            DECISION_APPROVE,
            draft_version=1,
            actor=ALLOWED_SENDER,
            gmail_message_id="decision-stale-v1",
        )
        reply = _commit(
            store,
            _receipt(
                "office-stale-2",
                thread_id="thr-office-stale",
                marker=MARKER_REPLY,
                subject=f"Re: ants {MARKER_REPLY}",
                body="Also in the bathroom now.",
                classification=CLASS_REPLY,
            ),
        )
        reopened = layer.upsert_from_receipt(reply)
        stale_again = layer.apply_decision(
            opened_stale["case_id"],
            DECISION_APPROVE,
            draft_version=1,
            actor=ALLOWED_SENDER,
            gmail_message_id="decision-stale-v1-retry",
        )
        layer.save_draft(
            opened_stale["case_id"],
            {
                "classification": "new_customer_lead",
                "known_facts": ["ants", "bathroom too"],
                "missing_info": ["phone"],
                "recommended_next_step": "callback",
                "proposed_response": SAFE_NEW_DRAFT,
                "channel": "email",
                "judgment_needed": "New inbound after approval.",
                "reasoning_summary": "version 2 after reopen",
            },
            "nonce-stale-v2",
        )
        stale_case = layer.get_case(opened_stale["case_id"])
        stale_ok = (
            approved.get("ok")
            and approved.get("send_triggered") is False
            and reopened.get("reopened")
            and reopened.get("approval_superseded")
            and not stale_again.get("ok")
            and stale_again.get("reason") in {"approval_superseded", "stale_draft_version"}
            and stale_case["approval_state"] == APPROVAL_PENDING
            and int(stale_case["draft_version"]) == 2
        )
        scenarios.append(
            _scenario(
                "new_inbound_or_changed_draft_invalidates_authorization",
                "PASS" if stale_ok else "FAIL",
                case_id=opened_stale["case_id"],
                first_approval=approved,
                reopen=reopened,
                stale_retry=stale_again,
                notes="New inbound superseded the old approval. Version 1 can no longer authorize.",
            )
        )

        repeat_row = _commit(
            store,
            _receipt(
                "office-repeat-1",
                thread_id="thr-office-repeat",
                marker=MARKER_NEW,
                subject=f"{MARKER_NEW} repeat",
                body="Repeat and restart fixture.",
            ),
        )
        opened_repeat = layer.upsert_from_receipt(repeat_row)
        install_desk_send_draft(layer, opened_repeat["case_id"], "nonce-repeat")
        repeat_binding = compute_packet_binding(
            layer.get_case(opened_repeat["case_id"]),
            layer.latest_draft(opened_repeat["case_id"]),
        )
        first_hold = _apply_control(layer, INTENT_HOLD, repeat_binding, gmail_message_id="ctrl-hold-repeat")
        repeat_hold = _apply_control(layer, INTENT_HOLD, repeat_binding, gmail_message_id="ctrl-hold-repeat")
        hold_events = [
            event
            for event in layer.list_events(opened_repeat["case_id"])
            if event.get("event_type") == "desk_hold"
        ]
        revise = _apply_control(
            layer,
            INTENT_REVISE,
            compute_packet_binding(layer.get_case(opened_new["case_id"]), layer.latest_draft(opened_new["case_id"])),
            note=REVISED_DRAFT,
            gmail_message_id="ctrl-revise-new",
        )
        after_revise = layer.get_case(opened_new["case_id"])
        first_decision = layer.apply_decision(
            opened_exist["case_id"],
            DECISION_APPROVE,
            draft_version=int(layer.get_case(opened_exist["case_id"])["draft_version"]),
            actor=ALLOWED_SENDER,
            gmail_message_id="decision-exist-1",
        )
        repeat_decision = layer.apply_decision(
            opened_exist["case_id"],
            DECISION_APPROVE,
            draft_version=int(layer.get_case(opened_exist["case_id"])["draft_version"]),
            actor=ALLOWED_SENDER,
            gmail_message_id="decision-exist-1",
        )
        decisions_before = layer.decisions(opened_exist["case_id"])
        store.close()
        store2 = ReceiptStore(store_path)
        layer2 = CaseLayer(store2)
        ensure_send_tables(layer2)
        restart_decision = layer2.apply_decision(
            opened_exist["case_id"],
            DECISION_APPROVE,
            draft_version=int(layer2.get_case(opened_exist["case_id"])["draft_version"]),
            actor=ALLOWED_SENDER,
            gmail_message_id="decision-exist-1",
        )
        decisions_after = layer2.decisions(opened_exist["case_id"])
        restart_hold = _apply_control(
            layer2,
            INTENT_HOLD,
            compute_packet_binding(layer2.get_case(opened_repeat["case_id"]), layer2.latest_draft(opened_repeat["case_id"])),
            gmail_message_id="ctrl-hold-repeat",
        )
        exist_after = layer2.get_case(opened_exist["case_id"])
        restart_ok = (
            first_hold.get("ok")
            and repeat_hold.get("ok")
            and repeat_hold.get("replayed")
            and restart_hold.get("ok")
            and restart_hold.get("replayed")
            and len(hold_events) == 1
            and revise.get("ok")
            and int(after_revise["draft_version"]) >= 4
            and first_decision.get("ok")
            and first_decision.get("send_triggered") is False
            and repeat_decision.get("skipped")
            and restart_decision.get("skipped")
            and len(decisions_before) == 1
            and len(decisions_after) == 1
            and exist_after["approval_state"] == APPROVAL_APPROVED
            and latest_action(layer2, opened_exist["case_id"]) is None
            and latest_action(layer2, opened_repeat["case_id"]) is None
            and execute_desk_queued_sends(layer2, MemorySendTransport()) == []
        )
        desk = LeadDesk(store_path, service_probe=lambda: {"observed": False, "active": None, "summary": "isolated pack"})
        listed = desk.list_cases(limit=50)
        views = {item["case_id"]: desk.get_case(item["case_id"]) for item in listed["cases"]}
        office_attention = {
            item["case_id"]: item["attention_reason"]
            for item in listed["cases"]
            if item.get("office_hold")
        }
        own_display_ok = bool(office_attention) and all(
            "waiting on Daniel" not in reason for reason in office_attention.values()
        )
        desk.close()
        store2.close()
        for item in scenarios:
            if item["name"] == "office_ownership_and_hold_block_send":
                if not own_display_ok:
                    item["status"] = "FAIL"
                    item["notes"] = "Held/office cases still presented as waiting on Daniel."
                else:
                    item["notes"] = (
                        "Hold, Brenda, and Ally each blocked approve-and-send and left no queued action. "
                        "Console names the owner or hold instead of waiting on Daniel."
                    )
        scenarios.append(
            _scenario(
                "repeat_decision_and_restart_no_duplicate_action",
                "PASS" if restart_ok else "FAIL",
                decision_count=len(decisions_after),
                revise_ok=bool(revise.get("ok")),
                notes="Same control/decision ids stayed skipped after restart. No send action was created.",
            )
        )
        passed = all(item["status"] == "PASS" for item in scenarios)
        return {
            "ok": passed,
            "isolation": {
                "store": str(store_path),
                "production_sqlite": False,
                "customer_sends": "off",
                "broad_capture": "off",
                "live_messages": False,
                "actions_1_and_2_untouched": True,
            },
            "scenarios": scenarios,
            "unsupported": [
                {
                    "id": "live_unmarked_customer_mail",
                    "status": "BLOCKED",
                    "detail": "Live receiver still uses BT-INTAKE-PROOF-* + daniel@. Unmarked real customer service mail is ineligible and stripped. This pack does not enable shadow intake.",
                },
                {
                    "id": "generic_office_owner_without_name",
                    "status": "UNSUPPORTED",
                    "detail": "Existing office_owned intent requires Brenda or Ally. Generic hold covers 'leave it with the office'. No new ownership policy was added.",
                },
                {
                    "id": "backend_price_phrase_parser",
                    "status": "UNSUPPORTED",
                    "detail": "Backend does not parse Codex drafts for invented prices. This pack uses a local reviewer check and conservative fixtures. ChatGPT still interprets; backend still binds.",
                },
                {
                    "id": "codex_live_draft_model",
                    "status": "BLOCKED",
                    "detail": "host_case_draft / live Codex drafting was not invoked. Drafts here are synthetic local fixtures.",
                },
                {
                    "id": "live_voice_or_phone",
                    "status": "BLOCKED",
                    "detail": "No live voice or Mac-off proof. Operator walkthrough is simulated interpretation only.",
                },
            ],
            "console": {
                "count": listed["count"],
                "cases": [
                    {
                        "case_id": item["case_id"],
                        "contact_name": item["contact_name"],
                        "owner": item["owner"],
                        "office_hold": item["office_hold"],
                        "stage": item["stage"],
                        "draft_exists": item["draft_exists"],
                        "attention_reason": item["attention_reason"],
                    }
                    for item in listed["cases"]
                ],
                "details": {
                    case_id: {
                        "owner": view["owner"],
                        "office_hold": view["office_hold"],
                        "stage": view["stage"],
                        "draft_version": view["draft_version"],
                        "approval_state": view["approval_state"],
                        "next_action": view["next_action"],
                        "attention_reason": view["attention_reason"],
                        "proposed_response": (view.get("draft") or {}).get("proposed_response"),
                        "decisions": view.get("decisions") or [],
                        "send": view.get("send"),
                    }
                    for case_id, view in views.items()
                },
            },
            "review_email": {
                "subject": review_new.get("subject"),
                "body": review_new.get("body"),
            },
        }
    finally:
        try:
            store.close()
        except Exception:
            pass
