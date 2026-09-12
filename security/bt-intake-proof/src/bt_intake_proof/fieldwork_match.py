"""Multi-identifier Fieldwork matching. Failed one-id search is not 'new customer'."""

from __future__ import annotations

import re
from typing import Any

from .fieldwork_booking import LABEL_FIXTURE, booking_state_from_records, draft_booking_guidance
from .fieldwork_readonly import ReadOnlyFieldworkClient, redact
from .store import utc_now

STRONG_HITS = {"email", "phone", "name", "street"}

MATCH_EXISTING = "matched_existing_customer"
MATCH_FORMER = "matched_former_customer"
MATCH_NONE = "no_match_after_multi_identifier_search"
MATCH_AMBIGUOUS = "ambiguous_match_needs_daniel"

FORMER_STATUSES = {"inactive", "sent_to_collections", "former", "cancelled"}
EXISTING_STATUSES = {"active", "financial_hold", "lead"}

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}")
ADDR_RE = re.compile(
    r"\b(\d{1,5}\s+[A-Za-z0-9.' ]+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Court|Ct|Boulevard|Blvd|Way|Pike)\.?)"
    r"(?:\s*,?\s*([A-Za-z .]+))?(?:\s*,?\s*([A-Z]{2}))?(?:\s+(\d{5}))?",
    re.I,
)


def digits(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")[-10:]


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
    return str(customer.get("customer_status") or customer.get("status") or "active").lower()


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


def score_candidate(customer: dict[str, Any], locations: list[dict[str, Any]], identifiers: dict[str, Any]) -> dict[str, Any]:
    hits = []
    score = 0
    emails = {item.lower() for item in identifiers.get("emails") or []}
    cust_email = str(customer.get("email") or customer.get("billing_email") or "").lower()
    if cust_email and cust_email in emails:
        score += 40
        hits.append("email")
    phones = set(identifiers.get("phones") or [])
    for raw in [customer.get("phone"), customer.get("billing_phone"), *((customer.get("phones") or []) if isinstance(customer.get("phones"), list) else [])]:
        num = digits(str(raw or ""))
        if num and num in phones:
            score += 35
            hits.append("phone")
            break
    for loc in locations:
        loc_email = str(loc.get("email") or "").lower()
        if loc_email and loc_email in emails and "email" not in hits:
            score += 40
            hits.append("email")
        loc_phone = digits(str((loc.get("address") or {}).get("phone") if isinstance(loc.get("address"), dict) else loc.get("phone") or ""))
        if loc_phone and loc_phone in phones and "phone" not in hits:
            score += 35
            hits.append("phone")
        blob = _addr_blob(loc)
        for addr in identifiers.get("addresses") or []:
            street = str(addr.get("street") or "").lower()
            city = str(addr.get("city") or "").lower()
            zipc = str(addr.get("zip") or "")
            if street and street.split()[0] in blob and any(part in blob for part in street.split()[1:2]):
                score += 20
                hits.append("street")
                if city and city in blob:
                    score += 10
                    hits.append("city")
                if zipc and zipc in blob:
                    score += 10
                    hits.append("zip")
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
    for loc in locations:
        blob = _addr_blob(loc)
        street = str(addresses[0].get("street") or "").lower()
        if street and street.split()[0] in blob:
            return loc
    return None


def office_hold(notes: list[dict[str, Any]], customer: dict[str, Any]) -> dict[str, Any] | None:
    texts = [str(customer.get("notes") or "")]
    for note in notes:
        texts.append(str(note.get("body") or note.get("text") or note.get("note") or ""))
    blob = " ".join(texts).lower()
    if any(token in blob for token in ("office-owned", "office owned", "do not contact", "stop contact", "no-action", "no action", "hold")):
        return {"kind": "office_or_hold", "source": "fieldwork_verified"}
    return None


def match_and_context(client: ReadOnlyFieldworkClient, receipt: dict[str, Any]) -> dict[str, Any]:
    identifiers = extract_identifiers(receipt)
    found: dict[str, dict[str, Any]] = {}
    searches = []

    def remember(rows: list[dict[str, Any]], via: str) -> None:
        searches.append({"via": via, "count": len(rows)})
        for row in rows:
            cid = _customer_id(row)
            if cid:
                found[cid] = row

    for email in identifiers.get("emails") or []:
        remember(client.search_customers(email), f"email:{email}")
    for phone in identifiers.get("phones") or []:
        remember(client.search_customers_by_phone(phone), f"phone:{phone}")
        if phone not in {item.split(":")[-1] for item in [s["via"] for s in searches if s["via"].startswith("phone")]}:
            remember(client.search_customers(phone), f"phone_query:{phone}")
    for addr in identifiers.get("addresses") or []:
        query = " ".join(part for part in (addr.get("street"), addr.get("city"), addr.get("zip")) if part)
        if query:
            remember(client.search_customers(query), f"address:{query}")
    for name in identifiers.get("names") or []:
        remember(client.search_customers(name), f"name:{name}")

    scored = []
    for customer in found.values():
        cid = _customer_id(customer)
        detail = client.get_customer(cid) or customer
        locations = client.list_locations(cid)
        contacts = client.list_contacts(cid)
        detail = {**detail, "contacts": contacts}
        scored.append(score_candidate(detail, locations, identifiers))

    decision = classify(scored)
    retrieved = utc_now()
    snapshot = getattr(client, "snapshot_meta", lambda: {})()
    evidence: dict[str, Any] = {
        "status": decision["status"],
        "confidence": decision["confidence"],
        "reason": decision.get("reason"),
        "identifiers": identifiers,
        "searches": searches,
        "retrieved_at": retrieved,
        "write_attempted": False,
        "client_write_attempts": client.write_attempts,
        "customer_id": None,
        "location_id": None,
        "active_agreement": None,
        "upcoming_work_orders": [],
        "last_service": None,
        "office_context": None,
        "source_label": LABEL_FIXTURE,
        "live": False,
        "proposed_write": snapshot.get("proposed_write"),
        "customer_email_reported_sent": bool(snapshot.get("customer_email_reported_sent")),
        "snapshot_booking_state": snapshot.get("booking_state"),
    }
    if decision["status"] in {MATCH_EXISTING, MATCH_FORMER}:
        best = decision["best"]
        customer = best["customer"]
        loc = location_for(best, identifiers)
        cid = _customer_id(customer)
        notes = client.list_notes(cid)
        wos = []
        try:
            wos = client.search_work_orders(**{"filter[customer_id]": cid})
        except Exception:
            wos = []
        agreements = []
        try:
            agreements = client.list_agreements(**{"filter[customer_id]": cid})
        except Exception:
            agreements = []
        upcoming = []
        last = None
        for wo in wos:
            status = str(wo.get("status") or wo.get("state") or "").lower()
            compact = {
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
            if compact["completed"]:
                last = compact
            elif status not in {"cancelled", "canceled"}:
                upcoming.append(compact)
        active = None
        for agr in agreements:
            name = str(agr.get("name") or agr.get("service") or agr.get("agreement") or "")
            status = str(agr.get("status") or agr.get("state") or "").lower()
            if "pestguard" in name.lower() or status in {"active", "current"}:
                active = {"name": name or "service_agreement", "status": agr.get("status") or agr.get("state")}
                break
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
                "last_service": last,
                "office_context": office_hold(notes, customer),
                "contacts": [
                    {"name": " ".join(str(c.get(k) or "") for k in ("first_name", "last_name")).strip() or c.get("name"), "email": c.get("email"), "relationship": c.get("description") or c.get("title")}
                    for c in (customer.get("contacts") or [])[:6]
                ],
            }
        )
        evidence["draft_guidance"] = draft_booking_guidance(evidence)
        if evidence["location_count"] > 1 and not evidence["location_id"]:
            evidence["status"] = MATCH_AMBIGUOUS
            evidence["confidence"] = "low"
            evidence["reason"] = "multiple_locations_unresolved"
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
