"""Multi-identifier Fieldwork matching. Failed one-id search is not 'new customer'."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from .fieldwork_booking import LABEL_FIXTURE, LABEL_LIVE, booking_state_from_records, draft_booking_guidance
from .fieldwork_readonly import FieldworkReadError, ListFetch, ReadOnlyFieldworkClient, as_fetch, redact
from .store import utc_now

STRONG_HITS = {"email", "phone", "name", "street"}

MATCH_EXISTING = "matched_existing_customer"
MATCH_FORMER = "matched_former_customer"
MATCH_NONE = "no_match_after_multi_identifier_search"
MATCH_AMBIGUOUS = "ambiguous_match_needs_daniel"
MATCH_BLOCKED = "blocked"
MATCH_INCOMPLETE = "incomplete"
MATCH_INSUFFICIENT = "insufficient_identifiers"

FORMER_STATUSES = {"inactive", "sent_to_collections", "former", "cancelled"}
EXISTING_STATUSES = {"active", "financial_hold", "lead"}
STREET_SKIP = {"n", "s", "e", "w", "ne", "nw", "se", "sw", "north", "south", "east", "west"}

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}")
ADDR_RE = re.compile(
    r"\b(\d{1,5}\s+[A-Za-z0-9.' ]+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Court|Ct|Boulevard|Blvd|Way|Pike)\.?)"
    r"(?:\s*,?\s*([A-Za-z .]+))?(?:\s*,?\s*([A-Z]{2}))?(?:\s+(\d{5}))?",
    re.I,
)


def digits(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")[-10:]


def window_bounds(days: int) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    span = timedelta(days=int(days))
    return now - span, now + span


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def row_in_window(row: dict[str, Any], start: datetime, end: datetime, keys: tuple[str, ...] = (
    "starts_at",
    "start_time",
    "created_at",
    "date",
    "completed_at",
    "updated_at",
)) -> bool | None:
    raw = None
    for key in keys:
        if row.get(key):
            raw = row.get(key)
            break
    parsed = parse_dt(raw)
    if parsed is None:
        return None
    return start <= parsed <= end


def filter_window(
    rows: list[dict[str, Any]],
    start: datetime | None,
    end: datetime | None,
) -> tuple[list[dict[str, Any]], int, int]:
    if start is None or end is None:
        return list(rows), 0, 0
    inside = []
    undated = 0
    outside = 0
    for row in rows:
        decision = row_in_window(row, start, end)
        if decision is True:
            inside.append(row)
        elif decision is False:
            outside += 1
        else:
            undated += 1
    return inside, undated, outside


def extract_identifiers(receipt: dict[str, Any]) -> dict[str, Any]:
    sender = str(receipt.get("sender") or "")
    subject = str(receipt.get("subject") or "")
    body = str(receipt.get("body_text") or "")
    blob = f"{sender}\n{subject}\n{body}"
    emails = []
    for item in EMAIL_RE.findall(blob):
        lower = item.lower()
        if lower.endswith("@btpestcontrol.com") and "fwd" not in lower:
            continue
        if lower not in emails:
            emails.append(lower)
    phones = []
    for item in PHONE_RE.findall(blob):
        num = digits(item)
        if len(num) == 10 and num not in phones and num != "9103291337":
            phones.append(num)
    addresses = []
    for match in ADDR_RE.finditer(blob):
        addresses.append(
            {
                "street": re.sub(r"\s+", " ", match.group(1)).strip(),
                "city": (match.group(2) or "").strip(" ,"),
                "state": (match.group(3) or "").strip(),
                "zip": match.group(4) or "",
            }
        )
    names = []
    name_match = re.search(r"(?:this is|my name is|i am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", body, re.I)
    if name_match:
        names.append(re.sub(r"\s+", " ", name_match.group(1)).strip())
    return {
        "emails": emails,
        "phones": phones,
        "names": names,
        "addresses": addresses,
        "sender": sender.lower(),
        "source": "customer_reported",
    }


def _status(customer: dict[str, Any]) -> str:
    raw = customer.get("customer_status")
    if raw is None:
        raw = customer.get("status")
    if raw is None or str(raw).strip() == "":
        return "unknown"
    return str(raw).lower()


def _customer_id(customer: dict[str, Any]) -> str:
    return str(customer.get("id") or customer.get("customer_id") or "")


def _addr_blob(location: dict[str, Any]) -> str:
    addr = location.get("address") or location.get("address_attributes") or location
    if not isinstance(addr, dict):
        return ""
    return " ".join(
        str(addr.get(key) or "")
        for key in ("street", "street1", "street2", "city", "state", "zip", "postal_code")
    ).lower()


def street_parts(street: str) -> tuple[str, str]:
    parts = [part for part in re.sub(r"\s+", " ", street or "").strip().lower().split(" ") if part]
    if not parts:
        return "", ""
    number = parts[0]
    name = ""
    for part in parts[1:]:
        token = part.strip(".,")
        if token and token not in STREET_SKIP:
            name = token
            break
    return number, name


def street_number_in_blob(number: str, blob: str) -> bool:
    if not number or not blob:
        return False
    return re.search(rf"(?<!\d){re.escape(number)}(?!\d)", blob) is not None


def street_matches(street: str, blob: str) -> bool:
    number, name = street_parts(street)
    if not number or not name:
        return False
    return street_number_in_blob(number, blob) and name in blob


def _has_identifiers(identifiers: dict[str, Any]) -> bool:
    return any(identifiers.get(key) for key in ("emails", "phones", "names", "addresses"))


def _client_provenance(client: ReadOnlyFieldworkClient) -> tuple[str, bool]:
    identity = getattr(client, "identity", None)
    if isinstance(identity, dict) and identity.get("label"):
        return str(identity.get("label") or LABEL_FIXTURE), bool(identity.get("live"))
    live = bool(getattr(client, "live", False))
    return (LABEL_LIVE if live else LABEL_FIXTURE), live


def score_candidate(customer: dict[str, Any], locations: list[dict[str, Any]], identifiers: dict[str, Any]) -> dict[str, Any]:
    hits: list[str] = []
    score = 0
    emails = {item.lower() for item in identifiers.get("emails") or []}
    cust_email = str(customer.get("email") or customer.get("billing_email") or "").lower()
    if cust_email and cust_email in emails:
        score += 40
        hits.append("email")
    phones = set(identifiers.get("phones") or [])
    phone_values = [customer.get("phone"), customer.get("billing_phone")]
    if isinstance(customer.get("phones"), list):
        phone_values.extend(customer.get("phones") or [])
    for contact in customer.get("contacts") or []:
        if isinstance(contact, dict):
            phone_values.append(contact.get("phone"))
            contact_email = str(contact.get("email") or "").lower()
            if contact_email and contact_email in emails and "email" not in hits:
                score += 40
                hits.append("email")
    for raw in phone_values:
        num = digits(str(raw or ""))
        if num and num in phones:
            score += 35
            hits.append("phone")
            break
    best_loc_score = 0
    best_loc_hits: list[str] = []
    for loc in locations:
        loc_score = 0
        loc_hits: list[str] = []
        loc_email = str(loc.get("email") or "").lower()
        if loc_email and loc_email in emails:
            loc_score += 40
            loc_hits.append("email")
        addr = loc.get("address") if isinstance(loc.get("address"), dict) else {}
        loc_phone = digits(str((addr or {}).get("phone") if addr else loc.get("phone") or ""))
        if loc_phone and loc_phone in phones:
            loc_score += 35
            loc_hits.append("phone")
        blob = _addr_blob(loc)
        for addr_id in identifiers.get("addresses") or []:
            street = str(addr_id.get("street") or "").lower()
            city = str(addr_id.get("city") or "").lower()
            zipc = str(addr_id.get("zip") or "")
            if street and street_matches(street, blob):
                loc_score += 20
                loc_hits.append("street")
                if city and city in blob:
                    loc_score += 10
                    loc_hits.append("city")
                if zipc and zipc in blob:
                    loc_score += 10
                    loc_hits.append("zip")
        if loc_score > best_loc_score:
            best_loc_score = loc_score
            best_loc_hits = loc_hits
    score += best_loc_score
    for hit in best_loc_hits:
        if hit not in hits:
            hits.append(hit)
    name = str(customer.get("name") or "").strip().lower()
    for reported in identifiers.get("names") or []:
        if reported.lower() and reported.lower() == name:
            score += 15
            hits.append("name")
        elif reported.lower() and reported.lower() in name:
            score += 8
            hits.append("name_partial")
    return {"score": score, "hits": sorted(set(hits)), "customer": customer, "locations": locations}


def classify(scored: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = sorted(scored, key=lambda item: item["score"], reverse=True)
    if not ranked or ranked[0]["score"] < 25:
        return {"status": MATCH_NONE, "confidence": "none", "candidates": ranked[:3]}
    top = ranked[0]
    strong = [hit for hit in (top.get("hits") or []) if hit in STRONG_HITS]
    if len(strong) < 2:
        return {
            "status": MATCH_AMBIGUOUS,
            "confidence": "low",
            "reason": "single_identifier_is_not_enough",
            "candidates": ranked[:3],
        }
    second = ranked[1]["score"] if len(ranked) > 1 else 0
    if second and top["score"] - second < 15:
        return {"status": MATCH_AMBIGUOUS, "confidence": "low", "candidates": ranked[:3]}
    status = _status(top["customer"])
    outcome = MATCH_FORMER if status in FORMER_STATUSES else MATCH_EXISTING
    confidence = "high" if top["score"] >= 50 and len(strong) >= 2 else "medium"
    return {"status": outcome, "confidence": confidence, "best": top, "candidates": ranked[:3]}


def location_for(best: dict[str, Any], identifiers: dict[str, Any]) -> dict[str, Any] | None:
    locations = best.get("locations") or []
    if not locations:
        return None
    if len(locations) == 1:
        return locations[0]
    addresses = identifiers.get("addresses") or []
    if not addresses:
        return None
    street = str(addresses[0].get("street") or "").lower()
    if not street:
        return None
    full_hits = []
    for loc in locations:
        if street_matches(street, _addr_blob(loc)):
            full_hits.append(loc)
    if len(full_hits) == 1:
        return full_hits[0]
    return None


def office_hold(notes: list[dict[str, Any]], customer: dict[str, Any]) -> dict[str, Any] | None:
    texts = [str(customer.get("notes") or "")]
    for note in notes:
        texts.append(str(note.get("body") or note.get("text") or note.get("note") or ""))
    blob = " ".join(texts).lower()
    if any(token in blob for token in ("office-owned", "office owned", "do not contact", "stop contact", "no-action", "no action", "hold")):
        return {"kind": "office_or_hold", "source": "fieldwork_verified"}
    return None


def _wo_customer_id(work_order: dict[str, Any]) -> str | None:
    raw = work_order.get("customer_id") or work_order.get("customer")
    if isinstance(raw, dict):
        raw = raw.get("id")
    if raw is None or str(raw).strip() == "":
        return None
    return str(raw)


def scope_work_orders(rows: list[dict[str, Any]], customer_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not rows:
        return [], {"ok": True, "foreign": 0, "unscoped": 0, "reason": None}
    scoped = []
    foreign = 0
    unscoped = 0
    for wo in rows:
        wo_cid = _wo_customer_id(wo)
        if wo_cid is None:
            unscoped += 1
            continue
        if wo_cid != str(customer_id):
            foreign += 1
            continue
        scoped.append(wo)
    if unscoped == len(rows):
        return [], {"ok": False, "foreign": foreign, "unscoped": unscoped, "reason": "work_orders_unscoped"}
    if foreign == len(rows) or (foreign and not scoped):
        return [], {"ok": False, "foreign": foreign, "unscoped": unscoped, "reason": "work_orders_unscoped"}
    return scoped, {"ok": True, "foreign": foreign, "unscoped": unscoped, "reason": None}


def _compact_work_order(wo: dict[str, Any]) -> dict[str, Any]:
    status = str(wo.get("status") or wo.get("state") or "").lower()
    return {
        "id": wo.get("id"),
        "status": wo.get("status") or wo.get("state"),
        "starts_at": wo.get("starts_at") or wo.get("start_time"),
        "ends_at": wo.get("ends_at"),
        "technician": wo.get("technician"),
        "amount": wo.get("amount"),
        "service": wo.get("service") or wo.get("name"),
        "location_id": wo.get("service_location_id") or wo.get("location_id"),
        "sold": bool(wo.get("sold")),
        "scheduled": bool(wo.get("scheduled") or status in {"scheduled", "confirmed", "dispatched"}),
        "completed": bool(wo.get("completed") or status in {"completed", "done", "finished"}),
    }


def match_and_context(
    client: ReadOnlyFieldworkClient,
    receipt: dict[str, Any],
    *,
    date_window_days: int | None = None,
) -> dict[str, Any]:
    identifiers = extract_identifiers(receipt)
    found: dict[str, dict[str, Any]] = {}
    searches: list[dict[str, Any]] = []
    search_state = "ok"
    search_reason: str | None = None
    source_label, live = _client_provenance(client)
    snapshot = getattr(client, "snapshot_meta", lambda: {})()
    omitted: dict[str, Any] = {}

    def mark_search(fetched: ListFetch, via: str) -> None:
        nonlocal search_state, search_reason
        searches.append(
            {
                "via": via,
                "count": len(fetched) if fetched.ok else 0,
                "ok": fetched.ok,
                "incomplete": fetched.incomplete,
                "truncated": fetched.truncated,
                "reason": fetched.reason,
            }
        )
        if not fetched.ok:
            search_state = "blocked"
            search_reason = fetched.reason or "read_failed"
            return
        if fetched.incomplete or fetched.truncated:
            if search_state == "ok":
                search_state = "incomplete"
                search_reason = fetched.reason or "pagination_truncated"

    def remember(result: Any, via: str) -> None:
        fetched = as_fetch(result)
        mark_search(fetched, via)
        if not fetched.ok:
            return
        for row in fetched:
            cid = _customer_id(row)
            if cid:
                found[cid] = row

    def base_evidence(status: str, confidence: str, reason: str | None) -> dict[str, Any]:
        return {
            "status": status,
            "confidence": confidence,
            "reason": reason,
            "identifiers": identifiers,
            "searches": searches,
            "retrieved_at": utc_now(),
            "write_attempted": False,
            "client_write_attempts": client.write_attempts,
            "customer_id": None,
            "location_id": None,
            "active_agreement": None,
            "upcoming_work_orders": [],
            "last_service": None,
            "office_context": None,
            "source_label": source_label,
            "live": live,
            "omitted": omitted,
            "proposed_write": snapshot.get("proposed_write"),
            "customer_email_reported_sent": bool(snapshot.get("customer_email_reported_sent")),
            "snapshot_booking_state": snapshot.get("booking_state"),
        }

    if not _has_identifiers(identifiers):
        return redact(base_evidence(MATCH_INSUFFICIENT, "none", "insufficient_identifiers"))

    for email in identifiers.get("emails") or []:
        remember(client.search_customers(email), f"email:{email}")
    for phone in identifiers.get("phones") or []:
        remember(client.search_customers_by_phone(phone), f"phone:{phone}")
        remembered_phones = {item.split(":")[-1] for item in [s["via"] for s in searches if s["via"].startswith("phone")]}
        if phone not in remembered_phones:
            remember(client.search_customers(phone), f"phone_query:{phone}")
    for addr in identifiers.get("addresses") or []:
        query = " ".join(part for part in (addr.get("street"), addr.get("city"), addr.get("zip")) if part)
        if query:
            remember(client.search_customers(query), f"address:{query}")
    for name in identifiers.get("names") or []:
        remember(client.search_customers(name), f"name:{name}")

    if search_state == "blocked":
        return redact(base_evidence(MATCH_BLOCKED, "none", search_reason))
    if search_state == "incomplete" and not found:
        return redact(base_evidence(MATCH_INCOMPLETE, "none", search_reason))

    scored = []
    for customer in found.values():
        cid = _customer_id(customer)
        try:
            detail = client.get_customer(cid)
        except FieldworkReadError as exc:
            return redact(base_evidence(MATCH_BLOCKED, "none", exc.reason))
        except Exception as exc:  # noqa: BLE001
            return redact(base_evidence(MATCH_BLOCKED, "none", type(exc).__name__))
        locations = as_fetch(client.list_locations(cid))
        contacts = as_fetch(client.list_contacts(cid))
        if not locations.ok or not contacts.ok:
            return redact(base_evidence(MATCH_BLOCKED, "none", locations.reason or contacts.reason))
        if locations.incomplete:
            omitted["locations"] = locations.reason or "pagination_truncated"
        detail = {**detail, "contacts": list(contacts)}
        scored.append(score_candidate(detail, list(locations), identifiers))

    decision = classify(scored)
    if search_state == "incomplete" and decision["status"] == MATCH_NONE:
        return redact(base_evidence(MATCH_INCOMPLETE, "none", search_reason))
    if omitted.get("locations") and decision["status"] == MATCH_NONE:
        return redact(base_evidence(MATCH_INCOMPLETE, "none", omitted["locations"]))

    evidence = base_evidence(decision["status"], decision.get("confidence") or "none", decision.get("reason"))
    if decision["status"] in {MATCH_EXISTING, MATCH_FORMER}:
        best = decision["best"]
        customer = best["customer"]
        loc = location_for(best, identifiers)
        cid = _customer_id(customer)
        notes = as_fetch(client.list_notes(cid))
        if not notes.ok:
            omitted["notes"] = notes.reason or "read_failed"
            note_rows: list[dict[str, Any]] = []
        else:
            if notes.incomplete:
                omitted["notes"] = notes.reason or "pagination_truncated"
            note_rows = list(notes)
        win_start = win_end = None
        if date_window_days:
            win_start, win_end = window_bounds(date_window_days)
        wo_supported = bool(getattr(client, "work_order_query_supported", False))
        wos: list[dict[str, Any]] = []
        if not wo_supported:
            omitted["work_orders"] = "work_order_customer_filter_unsupported"
        else:
            wo_params: dict[str, Any] = {"filter[customer_id]": cid}
            if win_start and win_end:
                wo_params["start_date"] = win_start.date().isoformat()
                wo_params["end_date"] = win_end.date().isoformat()
            wos_fetch = as_fetch(client.search_work_orders(**wo_params))
            if not wos_fetch.ok:
                omitted["work_orders"] = wos_fetch.reason or "read_failed"
            else:
                wos, wo_meta = scope_work_orders(list(wos_fetch), cid)
                if not wo_meta["ok"]:
                    omitted["work_orders"] = wo_meta["reason"]
                    wos = []
                elif wos_fetch.incomplete or wos_fetch.truncated:
                    omitted["work_orders"] = wos_fetch.reason or "pagination_truncated"
                else:
                    wos, wo_undated, wo_outside = filter_window(wos, win_start, win_end)
                    if wo_undated or wo_outside:
                        omitted["work_orders_window"] = {"undated": wo_undated, "outside": wo_outside}
        agreements = as_fetch(client.list_agreements(**{"filter[customer_id]": cid}))
        if not agreements.ok:
            omitted["agreements"] = agreements.reason or "read_failed"
            agr_rows: list[dict[str, Any]] = []
        else:
            if agreements.incomplete:
                omitted["agreements"] = agreements.reason or "pagination_truncated"
            agr_rows = list(agreements)
        estimates = as_fetch(client.list_estimates(**{"filter[customer_id]": cid}))
        if not estimates.ok:
            omitted["estimates"] = estimates.reason or "read_failed"
        elif estimates.incomplete:
            omitted["estimates"] = estimates.reason or "pagination_truncated"
        est_rows, est_undated, est_outside = filter_window(list(estimates) if estimates.ok else [], win_start, win_end)
        if estimates.ok and (est_undated or est_outside):
            omitted["estimates_window"] = {"undated": est_undated, "outside": est_outside}
        upcoming = []
        last = None
        for wo in wos:
            compact = _compact_work_order(wo)
            status = str(compact.get("status") or "").lower()
            if compact["completed"]:
                last = compact
            elif status not in {"cancelled", "canceled"}:
                upcoming.append(compact)
        active = None
        if "agreements" not in omitted:
            for agr in agr_rows:
                name = str(agr.get("name") or agr.get("service") or agr.get("agreement") or "")
                status = str(agr.get("status") or agr.get("state") or "").lower()
                if "pestguard" in name.lower() or status in {"active", "current"}:
                    active = {
                        "id": agr.get("id"),
                        "name": name or "service_agreement",
                        "status": agr.get("status") or agr.get("state"),
                    }
                    break
        appointments: list[dict[str, Any]] = []
        if "agreements" in omitted:
            omitted["appointments"] = omitted["agreements"]
        else:
            for agr in agr_rows[:5]:
                if agr.get("id") is None:
                    continue
                fetched = as_fetch(client.list_agreement_appointments(agr["id"]))
                if not fetched.ok:
                    omitted["appointments"] = fetched.reason or "read_failed"
                    appointments = []
                    break
                appointments.extend(list(fetched))
            else:
                appointments, appt_undated, appt_outside = filter_window(appointments, win_start, win_end)
                if appt_undated or appt_outside:
                    omitted["appointments_window"] = {"undated": appt_undated, "outside": appt_outside}
        if "work_orders" in omitted:
            booking = None
        else:
            booking = booking_state_from_records(
                upcoming + ([last] if last else []),
                proposed_write=evidence.get("proposed_write"),
                snapshot_state=evidence.get("snapshot_booking_state"),
            )
        evidence.update(
            {
                "customer_id": cid,
                "fixture_id": customer.get("fixture_id"),
                "identity_kind": customer.get("identity_kind") or "customer",
                "customer_name": customer.get("name"),
                "customer_status": _status(customer),
                "location_id": (loc or {}).get("id"),
                "location_name": (loc or {}).get("name"),
                "location_count": len(best.get("locations") or []),
                "match_hits": best.get("hits"),
                "near_matches_investigated": customer.get("near_matches_investigated") or [],
                "pipeline": customer.get("pipeline"),
                "booking_state": booking,
                "active_agreement": active,
                "upcoming_work_orders": upcoming[:5],
                "upcoming_appointments": [
                    {"id": row.get("id"), "status": row.get("status") or row.get("state"), "starts_at": row.get("starts_at") or row.get("start_time")}
                    for row in appointments[:5]
                ],
                "last_service": last,
                "notes_ok": notes.ok,
                "notes_count": len(note_rows) if notes.ok else None,
                "agreements_ok": agreements.ok,
                "estimates_ok": estimates.ok,
                "estimates_count": len(est_rows) if estimates.ok else None,
                "appointments_ok": "appointments" not in omitted,
                "work_orders_ok": "work_orders" not in omitted,
                "date_window_days": date_window_days,
                "office_context": office_hold(note_rows, customer) if "notes" not in omitted or note_rows else None,
                "contacts": [
                    {
                        "name": " ".join(str(c.get(k) or "") for k in ("first_name", "last_name")).strip() or c.get("name"),
                        "email": c.get("email"),
                        "relationship": c.get("description") or c.get("title"),
                    }
                    for c in (customer.get("contacts") or [])[:6]
                ],
                "omitted": omitted,
            }
        )
        evidence["draft_guidance"] = draft_booking_guidance(evidence)
        if evidence["location_count"] > 1 and not evidence["location_id"]:
            evidence["status"] = MATCH_AMBIGUOUS
            evidence["confidence"] = "low"
            evidence["reason"] = "multiple_locations_unresolved"
        if omitted.get("locations") and evidence["location_count"] <= 1 and not evidence["location_id"]:
            evidence["status"] = MATCH_INCOMPLETE
            evidence["confidence"] = "none"
            evidence["reason"] = omitted["locations"]
    elif decision["status"] == MATCH_AMBIGUOUS:
        evidence["candidates"] = [
            {
                "customer_id": _customer_id(item["customer"]),
                "name": item["customer"].get("name"),
                "score": item["score"],
                "hits": item["hits"],
            }
            for item in decision.get("candidates") or []
        ]
    return redact(evidence)
