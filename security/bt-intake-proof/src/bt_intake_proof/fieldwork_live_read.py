"""Explicit bounded Fieldwork live-read runner. Does not draft, enqueue, or send."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .fieldwork_booking import LABEL_FIXTURE, LABEL_LIVE
from .fieldwork_fixture import GrokBotFieldwork
from .fieldwork_match import (
    MATCH_AMBIGUOUS,
    MATCH_BLOCKED,
    MATCH_EXISTING,
    MATCH_FORMER,
    MATCH_INCOMPLETE,
    MATCH_INSUFFICIENT,
    MATCH_NONE,
    _status,
    digits,
    filter_window,
    match_and_context,
    street_matches,
    window_bounds,
)
from .fieldwork_readonly import (
    RUNNER_MAX_REQUESTS,
    FieldworkReadError,
    ReadOnlyFieldworkClient,
    as_fetch,
    live_read_client,
)
from .store import utc_now

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_MANIFEST = ROOT / "config" / "live_fw_read_manifest.example.json"
SYNTHETIC_CATALOG = ROOT / "config" / "live_fw_read_catalog.json"
HOST_DIR = Path(os.environ.get("BT_LIVE_FW_READ_DIR", "/var/lib/bt-intake-proof/live-fw-read"))
HOST_MANIFEST = HOST_DIR / "manifest.json"
HOST_EVIDENCE = HOST_DIR / "evidence"

AUTHORIZED_LABELS = (
    {"key": "authorized_case_1", "search_name": "Shelley Robinson"},
    {"key": "authorized_case_2", "search_name": "Jordan Suminski"},
    {"key": "authorized_case_3", "search_name": "Mariah Burgess"},
)
SYNTHETIC_NO_MATCH_QUERY = "ZZZ-NO-CUSTOMER-PROOF-9F3A"
MAX_REAL_CASES = 3
MAX_AMBIGUITY_PROBES = 2
MAX_SYNTHETIC_NO_MATCH = 1
MAX_NAME_CANDIDATES = 5
DEFAULT_DATE_WINDOW_DAYS = 365

PROOF_SOURCE = "source_evidence"
PROOF_PROVIDER = "provider_derived_probe"
PROOF_FIXTURE = "synthetic_fixture"


def fixture_client(catalog_path: Path | None = None) -> GrokBotFieldwork:
    client = GrokBotFieldwork(catalog_path=catalog_path or SYNTHETIC_CATALOG)
    client.max_requests = RUNNER_MAX_REQUESTS
    return client


def _ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def _write_private(path: Path, payload: dict[str, Any], mode: int = 0o600) -> None:
    _ensure_private_dir(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, default=str) + "\n")
    os.chmod(path, mode)


def preflight(mode: str = "live") -> dict[str, Any]:
    """Host connectivity check. Never prints a token. Does not search customers."""
    if mode == "fixture":
        client = fixture_client()
        conn = client.check_connection()
        return {
            "ok": True,
            "status": "PASS",
            "mode": "fixture",
            "live": False,
            "source_label": LABEL_FIXTURE,
            "connection_ok": bool(conn.get("ok")),
            "adapter_enforced_read_only": True,
            "provider_token_scope_verified": False,
            "write_attempts": client.write_attempts,
        }
    if os.environ.get("BT_FIELDWORK_LIVE_READ") != "1":
        return {
            "ok": False,
            "status": "BLOCKED",
            "mode": "live",
            "live": False,
            "reason": "live_read_not_enabled",
            "provisioning": "existing_host_fieldwork_credential_required",
        }
    token_file = os.environ.get("FIELDWORK_API_KEY_FILE") or ""
    has_env_token = bool(os.environ.get("FIELDWORK_API_KEY"))
    if not has_env_token and not token_file:
        return {
            "ok": False,
            "status": "BLOCKED",
            "mode": "live",
            "reason": "fieldwork_api_key_not_issued",
            "token_file_configured": False,
            "provisioning": "existing_host_fieldwork_credential_required",
        }
    if token_file and not Path(token_file).exists():
        return {
            "ok": False,
            "status": "BLOCKED",
            "mode": "live",
            "reason": "token_file_missing",
            "token_file_configured": True,
            "token_file_exists": False,
            "provisioning": "existing_host_fieldwork_credential_required",
        }
    try:
        client = live_read_client()
    except FieldworkReadError as exc:
        return {"ok": False, "status": "BLOCKED", "mode": "live", "reason": exc.reason}
    conn = client.check_connection()
    return {
        "ok": bool(conn.get("ok")),
        "status": "PASS" if conn.get("ok") else "BLOCKED",
        "mode": "live",
        "live": True,
        "source_label": LABEL_LIVE,
        "connection_ok": bool(conn.get("ok")),
        "reason": conn.get("reason"),
        "adapter_enforced_read_only": True,
        "provider_token_scope_verified": False,
        "write_attempts": client.write_attempts,
        "request_count": len(client.calls),
    }


def name_search_aliases(full_name: str) -> list[dict[str, str]]:
    text = " ".join(str(full_name or "").split())
    if not text:
        return []
    parts = text.split(" ")
    aliases = [{"form": "full", "query": text}]
    if len(parts) >= 2:
        first, last = parts[0], parts[-1]
        aliases.extend(
            [
                {"form": "last_first", "query": f"{last}, {first}"},
                {"form": "surname", "query": last},
                {"form": "first", "query": first},
            ]
        )
    seen = set()
    out = []
    for item in aliases:
        key = (item["form"], item["query"].lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _independent_identifiers(identifiers: dict[str, Any] | None) -> bool:
    ids = identifiers or {}
    return bool(ids.get("emails") or ids.get("phones") or ids.get("addresses"))


def _locations_of(customer: dict[str, Any]) -> list[dict[str, Any]]:
    locs = customer.get("service_locations")
    if locs is None:
        locs = customer.get("locations") or []
    return [item for item in locs if isinstance(item, dict)]


def _corroborates(detail: dict[str, Any], locations: list[dict[str, Any]], identifiers: dict[str, Any]) -> list[str]:
    hits = []
    emails = {item.lower() for item in identifiers.get("emails") or []}
    if emails and str(detail.get("email") or "").lower() in emails:
        hits.append("email")
    phones = {digits(item) for item in identifiers.get("phones") or [] if digits(item)}
    if phones and digits(detail.get("phone")) in phones:
        hits.append("phone")
    for loc in locations:
        addr = loc.get("address") or loc.get("address_attributes") or {}
        blob = " ".join(str(addr.get(key) or "") for key in ("street", "city", "zip")).lower()
        for reported in identifiers.get("addresses") or []:
            if street_matches(str(reported.get("street") or ""), blob):
                hits.append("street")
    return sorted(set(hits))


def _select_location(locations: list[dict[str, Any]], identifiers: dict[str, Any] | None) -> str | None:
    addresses = (identifiers or {}).get("addresses") or []
    if not addresses:
        if len(locations) == 1 and locations[0].get("id") is not None:
            return str(locations[0]["id"])
        return None
    hits = []
    for loc in locations:
        addr = loc.get("address") or loc.get("address_attributes") or {}
        blob = " ".join(str(addr.get(key) or "") for key in ("street", "city", "zip")).lower()
        if street_matches(str(addresses[0].get("street") or ""), blob):
            hits.append(loc)
    if len(hits) == 1 and hits[0].get("id") is not None:
        return str(hits[0]["id"])
    return None


def _search_normalized(client: ReadOnlyFieldworkClient, name: str) -> dict[str, Any]:
    attempts = []
    ids: list[str] = []
    full_count = None
    for alias in name_search_aliases(name):
        fetched = as_fetch(client.search_customers(alias["query"]))
        attempts.append(
            {
                "form": alias["form"],
                "ok": fetched.ok,
                "count": len(fetched) if fetched.ok else 0,
                "truncated": fetched.truncated,
                "incomplete": fetched.incomplete,
                "reason": fetched.reason,
            }
        )
        if alias["form"] == "full":
            full_count = len(fetched) if fetched.ok else 0
        if not fetched.ok:
            return {"status": "BLOCKED", "reason": fetched.reason or "read_failed", "attempts": attempts, "candidate_ids": []}
        if fetched.incomplete or fetched.truncated:
            return {
                "status": "BLOCKED",
                "reason": fetched.reason or "pagination_truncated",
                "attempts": attempts,
                "candidate_ids": ids,
            }
        for row in fetched:
            cid = str(row.get("id") or row.get("customer_id") or "")
            if cid and cid not in ids:
                ids.append(cid)
        if len(ids) > MAX_NAME_CANDIDATES:
            return {
                "status": "BLOCKED",
                "reason": "name_search_exceeded_candidate_bound",
                "attempts": attempts,
                "candidate_ids": ids[:MAX_NAME_CANDIDATES],
            }
    if not ids:
        return {
            "status": "BLOCKED",
            "reason": "authorized_name_no_candidates_after_aliases",
            "attempts": attempts,
            "candidate_ids": [],
            "full_name_count": full_count,
        }
    return {
        "status": "needs_corroboration",
        "reason": "name_alone_is_not_identity",
        "attempts": attempts,
        "candidate_ids": ids,
        "full_name_count": full_count,
        "hit_count": len(ids),
    }


def _corroborate_candidates(
    client: ReadOnlyFieldworkClient,
    candidate_ids: list[str],
    identifiers: dict[str, Any],
) -> dict[str, Any]:
    matched = []
    for cid in candidate_ids[:MAX_NAME_CANDIDATES]:
        try:
            detail = client.get_customer(cid)
        except FieldworkReadError as exc:
            return {"status": "BLOCKED", "reason": exc.reason, "matched_ids": []}
        locs = as_fetch(client.list_locations(cid))
        if not locs.ok:
            return {"status": "BLOCKED", "reason": locs.reason or "read_failed", "matched_ids": []}
        hits = _corroborates(detail, list(locs), identifiers)
        if hits:
            matched.append({"customer_id": cid, "hits": hits, "location_ids": [str(row.get("id")) for row in locs if row.get("id") is not None]})
    if len(matched) == 1:
        return {"status": "PASS", "reason": None, "matched_ids": [matched[0]["customer_id"]], "best": matched[0]}
    if not matched:
        return {"status": "BLOCKED", "reason": "no_corroborated_identity", "matched_ids": []}
    return {"status": "BLOCKED", "reason": "not_unique_after_corroboration", "matched_ids": [item["customer_id"] for item in matched]}


def resolve_authorized(
    client: ReadOnlyFieldworkClient,
    *,
    labels: tuple[dict[str, Any], ...] | list[dict[str, Any]] = AUTHORIZED_LABELS,
    out_path: Path | None = None,
) -> dict[str, Any]:
    """Resolve authorized labels. A unique name is not identity proof."""
    resolved = []
    blocked = False
    live = bool(getattr(client, "live", False))
    proof = PROOF_FIXTURE if not live else PROOF_SOURCE
    for label in labels[:MAX_REAL_CASES]:
        found = _search_normalized(client, label["search_name"])
        item = {
            "key": label["key"],
            "status": found["status"],
            "reason": found.get("reason"),
            "hit_count": found.get("hit_count") or len(found.get("candidate_ids") or []),
            "full_name_count": found.get("full_name_count"),
            "search_forms": [row.get("form") for row in found.get("attempts") or []],
            "customer_id": None,
            "location_id": None,
        }
        identifiers = label.get("identifiers") or {}
        if found.get("status") == "BLOCKED":
            blocked = True
        elif not _independent_identifiers(identifiers):
            item["status"] = "BLOCKED"
            item["reason"] = "name_alone_is_not_identity"
            blocked = True
        else:
            confirmed = _corroborate_candidates(client, found.get("candidate_ids") or [], identifiers)
            item["status"] = confirmed["status"]
            item["reason"] = confirmed.get("reason")
            if confirmed.get("status") == "PASS":
                item["customer_id"] = confirmed["best"]["customer_id"]
                locs = as_fetch(client.list_locations(item["customer_id"]))
                item["location_count"] = len(locs) if locs.ok else None
                item["location_ids"] = [str(row.get("id")) for row in locs if row.get("id") is not None] if locs.ok else []
                item["locations_ok"] = locs.ok
                item["location_id"] = _select_location(list(locs) if locs.ok else [], identifiers)
                if not locs.ok:
                    item["status"] = "BLOCKED"
                    item["reason"] = locs.reason
                    blocked = True
                elif not item["location_id"]:
                    item["status"] = "BLOCKED"
                    item["reason"] = "selected_property_unresolved"
                    blocked = True
            else:
                blocked = True
        item["proof_class"] = proof
        item["identifiers_present"] = {
            "names": bool((identifiers.get("names") or [])),
            "emails": bool((identifiers.get("emails") or [])),
            "phones": bool((identifiers.get("phones") or [])),
            "addresses": bool((identifiers.get("addresses") or [])),
        }
        resolved.append(item)

    probes = _derive_probes(resolved, [label.get("identifiers") or {} for label in labels[:MAX_REAL_CASES]], live)
    scenarios = []
    for item, label in zip(resolved, labels[:MAX_REAL_CASES]):
        scenarios.append(
            {
                "key": item["key"],
                "kind": "authorized_identity",
                "proof_class": item["proof_class"],
                "customer_id": item.get("customer_id"),
                "location_id": item.get("location_id"),
                "status": item["status"],
                "reason": item.get("reason"),
                "identifiers": label.get("identifiers") or {},
            }
        )
    for probe in probes[:MAX_AMBIGUITY_PROBES]:
        scenarios.append(probe)
    scenarios.append(
        {
            "key": "synthetic_no_match",
            "kind": "synthetic_no_match",
            "proof_class": PROOF_FIXTURE,
            "query": SYNTHETIC_NO_MATCH_QUERY,
            "customer_id": None,
            "expect": MATCH_NONE,
        }
    )
    if sum(1 for row in scenarios if row.get("kind") == "authorized_identity") > MAX_REAL_CASES:
        raise RuntimeError("manifest_real_case_limit")
    if sum(1 for row in scenarios if str(row.get("kind") or "").startswith("ambiguity")) > MAX_AMBIGUITY_PROBES:
        raise RuntimeError("manifest_ambiguity_limit")
    if sum(1 for row in scenarios if row.get("kind") == "synthetic_no_match") > MAX_SYNTHETIC_NO_MATCH:
        raise RuntimeError("manifest_synthetic_limit")

    manifest = {
        "version": 1,
        "created_at": utc_now(),
        "live": live,
        "source_label": LABEL_LIVE if live else LABEL_FIXTURE,
        "max_real_cases": MAX_REAL_CASES,
        "max_ambiguity_probes": MAX_AMBIGUITY_PROBES,
        "max_synthetic_no_match": MAX_SYNTHETIC_NO_MATCH,
        "date_window_days": DEFAULT_DATE_WINDOW_DAYS,
        "authorized": [{k: v for k, v in item.items() if k != "location_ids"} for item in resolved],
        "scenarios": scenarios,
        "write_attempted": False,
        "client_write_attempts": client.write_attempts,
        "request_count": len(getattr(client, "calls", []) or []),
    }
    dest = out_path or HOST_MANIFEST
    _write_private(dest, manifest, 0o600)
    public = {
        "ok": not blocked,
        "status": "PASS" if not blocked else "BLOCKED",
        "manifest_written": dest.exists(),
        "authorized": [
            {
                "key": item["key"],
                "status": item["status"],
                "reason": item.get("reason"),
                "hit_count": item.get("hit_count"),
                "full_name_count": item.get("full_name_count"),
                "customer_id_present": bool(item.get("customer_id")),
                "location_id_present": bool(item.get("location_id")),
                "location_count": item.get("location_count"),
                "proof_class": item.get("proof_class"),
            }
            for item in resolved
        ],
        "probe_keys": [row["key"] for row in probes],
        "write_attempts": client.write_attempts,
        "request_count": len(getattr(client, "calls", []) or []),
    }
    return public


def _derive_probes(resolved: list[dict[str, Any]], identifier_sets: list[dict[str, Any]], live: bool) -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []
    proof = PROOF_PROVIDER if live else PROOF_FIXTURE
    usable = [
        (item, ids)
        for item, ids in zip(resolved, identifier_sets)
        if item.get("status") == "PASS" and item.get("customer_id") and _independent_identifiers(ids)
    ]
    multi = [(item, ids) for item, ids in usable if int(item.get("location_count") or 0) > 1]
    if multi:
        first, ids = multi[0]
        no_street = {
            "names": list(ids.get("names") or []),
            "emails": list(ids.get("emails") or []),
            "phones": list(ids.get("phones") or []),
        }
        probes.append(
            {
                "key": "ambiguity_probe_1",
                "kind": "ambiguity_multi_property",
                "proof_class": proof,
                "customer_id": first["customer_id"],
                "location_id": None,
                "expect": MATCH_AMBIGUOUS,
                "omit_street": True,
                "coverage": "available",
                "identifiers": no_street,
            }
        )
        probes.append(
            {
                "key": "ambiguity_probe_2",
                "kind": "ambiguity_name_only",
                "proof_class": proof,
                "customer_id": first["customer_id"],
                "expect": MATCH_AMBIGUOUS,
                "coverage": "available",
                "identifiers": {"names": list(ids.get("names") or [])},
            }
        )
    elif usable:
        first, ids = usable[0]
        probes.append(
            {
                "key": "ambiguity_probe_1",
                "kind": "ambiguity_name_only",
                "proof_class": proof,
                "customer_id": first["customer_id"],
                "expect": MATCH_AMBIGUOUS,
                "coverage": "available",
                "identifiers": {"names": list(ids.get("names") or [])},
            }
        )
        probes.append(
            {
                "key": "ambiguity_probe_2",
                "kind": "multiple_property_coverage",
                "proof_class": proof,
                "coverage": "unavailable",
                "reason": "no_multiple_property_in_bounded_set",
                "expect": None,
            }
        )
    else:
        probes.append(
            {
                "key": "ambiguity_probe_1",
                "kind": "ambiguity_unavailable",
                "proof_class": proof,
                "coverage": "unavailable",
                "reason": "authorized_cases_not_resolved",
                "expect": None,
            }
        )
        probes.append(
            {
                "key": "ambiguity_probe_2",
                "kind": "multiple_property_coverage",
                "proof_class": proof,
                "coverage": "unavailable",
                "reason": "authorized_cases_not_resolved",
                "expect": None,
            }
        )
    return probes[:MAX_AMBIGUITY_PROBES]


def load_manifest(path: Path) -> dict[str, Any]:
    blob = json.loads(path.read_text(encoding="utf-8"))
    real = [row for row in blob.get("scenarios") or [] if row.get("kind") == "authorized_identity"]
    ambig = [row for row in blob.get("scenarios") or [] if str(row.get("kind") or "").startswith("ambiguity")]
    synth = [row for row in blob.get("scenarios") or [] if row.get("kind") == "synthetic_no_match"]
    if len(real) > MAX_REAL_CASES or len(ambig) > MAX_AMBIGUITY_PROBES or len(synth) > MAX_SYNTHETIC_NO_MATCH:
        raise RuntimeError("manifest_limit_exceeded")
    return blob


def scenario_receipt(scenario: dict[str, Any], customer: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Build a receipt from scenario identifiers only. Never invent live stand-ins."""
    del customer  # caller-supplied HQ rows are not inbound evidence
    kind = scenario.get("kind")
    if kind == "synthetic_no_match":
        query = scenario.get("query") or SYNTHETIC_NO_MATCH_QUERY
        body = (
            f"This is Nobody Proof at 999 Missing Avenue, Nowhere NC 00000. "
            f"910-555-0000 nobody.proof.syn@example.org {query}"
        )
        return {"sender": "nobody.proof.syn@example.org", "subject": query, "body_text": body}
    ids = scenario.get("identifiers") or {}
    names = [str(item) for item in ids.get("names") or [] if item]
    emails = [str(item) for item in ids.get("emails") or [] if item]
    phones = [str(item) for item in ids.get("phones") or [] if item]
    addresses = [item for item in ids.get("addresses") or [] if isinstance(item, dict)]
    if not names and not emails and not phones and not addresses:
        return None
    parts = []
    if names:
        parts.append(f"This is {names[0]}.")
    if addresses:
        street = addresses[0].get("street") or ""
        city = addresses[0].get("city") or ""
        zipc = addresses[0].get("zip") or ""
        if street:
            parts.append(f"Ants at {street}" + (f", {city} NC {zipc}" if city or zipc else "."))
    if phones:
        parts.append(str(phones[0]))
    if emails:
        parts.append(str(emails[0]))
    sender = emails[0] if emails else "daniel@btpestcontrol.com"
    return {"sender": sender, "subject": str(kind or "scenario"), "body_text": " ".join(parts)}


def _component(ok: bool, *, reason: str | None = None, count: int | None = None, unsupported: bool = False, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    status = "unsupported" if unsupported else ("ok" if ok else "failed")
    payload = {"ok": ok and not unsupported, "status": status, "reason": reason, "count": count}
    if extra:
        payload.update(extra)
    return payload


def direct_read_bundle(
    client: ReadOnlyFieldworkClient,
    customer_id: str | None,
    location_id: str | None = None,
    *,
    date_window_days: int = DEFAULT_DATE_WINDOW_DAYS,
) -> dict[str, Any]:
    """Native-ID reads. Does not call matcher, score, or classify."""
    live = bool(getattr(client, "live", False))
    start, end = window_bounds(date_window_days)
    window = {"start": start.isoformat(), "end": end.isoformat(), "days": date_window_days}
    if not customer_id:
        return {"ok": False, "reason": "no_customer_id", "live": live, "date_window": window}
    try:
        customer = client.get_customer(customer_id)
    except FieldworkReadError as exc:
        return {"ok": False, "reason": exc.reason, "customer_id": customer_id, "live": live, "date_window": window}
    location = None
    location_reason = None
    if location_id:
        try:
            location = client.get_location(location_id, customer_id)
        except FieldworkReadError as exc:
            location_reason = exc.reason
    elif location_id is None:
        location_reason = "selected_property_missing"
    locations = as_fetch(client.list_locations(customer_id))
    notes = as_fetch(client.list_notes(customer_id))
    agreements = as_fetch(client.list_agreements(**{"filter[customer_id]": customer_id}))
    estimates = as_fetch(client.list_estimates(**{"filter[customer_id]": customer_id}))
    wo_supported = bool(getattr(client, "work_order_query_supported", False))
    work_orders = None
    if wo_supported:
        work_orders = as_fetch(
            client.search_work_orders(
                **{
                    "filter[customer_id]": customer_id,
                    "start_date": start.date().isoformat(),
                    "end_date": end.date().isoformat(),
                }
            )
        )
    appointments: list[dict[str, Any]] = []
    appt_ok = False
    appt_reason = None
    if not agreements.ok:
        appt_ok = False
        appt_reason = agreements.reason or "agreements_unavailable"
    else:
        appt_ok = True
        for agr in list(agreements)[:5]:
            if agr.get("id") is None:
                continue
            fetched = as_fetch(client.list_agreement_appointments(agr["id"]))
            if not fetched.ok:
                appt_ok = False
                appt_reason = fetched.reason
                appointments = []
                break
            appointments.extend(list(fetched))
    appt_in, appt_undated, appt_outside = filter_window(appointments, start, end)
    est_in, est_undated, est_outside = filter_window(list(estimates) if estimates.ok else [], start, end)
    last_service = None
    upcoming_wos: list[dict[str, Any]] = []
    wo_component = _component(False, unsupported=True, reason="work_order_customer_filter_unsupported")
    if wo_supported and work_orders is not None:
        if not work_orders.ok:
            wo_component = _component(False, reason=work_orders.reason)
        else:
            in_win, undated, outside = filter_window(list(work_orders), start, end)
            for wo in in_win:
                compact = {
                    "id": wo.get("id"),
                    "status": wo.get("status") or wo.get("state"),
                    "starts_at": wo.get("starts_at") or wo.get("start_time"),
                    "location_id": wo.get("service_location_id") or wo.get("location_id"),
                    "completed": str(wo.get("status") or "").lower() in {"completed", "done", "finished"} or wo.get("completed") is True,
                }
                if compact["completed"]:
                    last_service = compact
                else:
                    upcoming_wos.append(compact)
            wo_component = _component(
                True,
                count=len(in_win),
                extra={"undated": undated, "outside": outside, "last_service_id": (last_service or {}).get("id")},
            )
    identity_ok = True
    property_ok = bool(location_id) and isinstance(location, dict) and location.get("id") is not None
    if location_id and not property_ok:
        identity_ok = True
    return {
        "ok": True,
        "live": live,
        "retrieved_at": utc_now(),
        "date_window": window,
        "date_window_days": date_window_days,
        "date_window_applied": True,
        "customer_id": str(customer.get("id") or customer_id),
        "customer_status": _status(customer),
        "location_id": str(location.get("id")) if isinstance(location, dict) and location.get("id") is not None else None,
        "location_reason": location_reason,
        "property_ok": property_ok,
        "notes": _component(notes.ok, reason=notes.reason, count=len(notes) if notes.ok else None),
        "agreements": _component(
            agreements.ok,
            reason=agreements.reason,
            count=len(agreements) if agreements.ok else None,
            extra={
                "active_present": bool(
                    agreements.ok
                    and any(str(row.get("status") or row.get("state") or "").lower() in {"active", "current"} for row in agreements)
                )
            },
        ),
        "estimates": _component(
            estimates.ok,
            reason=estimates.reason,
            count=len(est_in) if estimates.ok else None,
            extra={"undated": est_undated, "outside": est_outside},
        ),
        "appointments": _component(
            appt_ok,
            reason=appt_reason,
            count=len(appt_in) if appt_ok else None,
            extra={"undated": appt_undated, "outside": appt_outside, "ids": [row.get("id") for row in appt_in[:5]]},
        ),
        "work_orders": wo_component,
        "recent_service": (
            {"status": "unsupported", "ok": False, "reason": "work_order_customer_filter_unsupported"}
            if not wo_supported
            else {"status": "ok" if wo_component["ok"] else "failed", "ok": wo_component["ok"], "id": (last_service or {}).get("id")}
        ),
        "upcoming": (
            {"status": "ok" if appt_ok else "failed", "ok": appt_ok, "count": len(appt_in) if appt_ok else None, "source": "agreement_appointments"}
        ),
        "notes_ok": notes.ok,
        "notes_count": len(notes) if notes.ok else None,
        "agreements_ok": agreements.ok,
        "agreements_count": len(agreements) if agreements.ok else None,
        "active_agreement_present": bool(
            agreements.ok
            and any(str(row.get("status") or row.get("state") or "").lower() in {"active", "current"} for row in agreements)
        ),
        "estimates_ok": estimates.ok,
        "estimates_count": len(est_in) if estimates.ok else None,
        "work_orders_ok": wo_component["ok"],
        "appointments_ok": appt_ok,
        "appointments_count": len(appt_in) if appt_ok else None,
        "appointments_reason": appt_reason,
        "locations_ok": locations.ok,
        "location_count": len(locations) if locations.ok else None,
        "last_service_id": (last_service or {}).get("id"),
        "request_count": len(getattr(client, "calls", []) or []),
        "write_attempts": client.write_attempts,
        "context_complete": bool(
            notes.ok
            and agreements.ok
            and estimates.ok
            and appt_ok
            and wo_component["ok"]
            and property_ok
        ),
    }


def compare_to_direct(
    matcher: dict[str, Any],
    direct: dict[str, Any],
    expected: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare matcher and independent native-ID read against the selected manifest IDs."""
    expected = expected or {}
    if not direct.get("ok"):
        return {
            "ok": False,
            "identity_ok": False,
            "context_ok": False,
            "status": "BLOCKED",
            "reason": direct.get("reason") or "direct_read_failed",
            "failed": ["direct_ok"],
            "checks": [{"name": "direct_ok", "ok": False}],
        }
    checks: list[tuple[str, bool]] = [("direct_ok", True)]
    exp_cid = expected.get("customer_id")
    exp_lid = expected.get("location_id")
    if exp_cid in (None, ""):
        return {
            "ok": False,
            "identity_ok": False,
            "context_ok": False,
            "status": "BLOCKED",
            "reason": "expected_customer_id_missing",
            "failed": ["expected_customer_id"],
            "checks": [{"name": "expected_customer_id", "ok": False}],
        }
    checks.append(("matcher_customer_id", str(matcher.get("customer_id") or "") == str(exp_cid)))
    checks.append(("direct_customer_id", str(direct.get("customer_id") or "") == str(exp_cid)))
    checks.append(("customer_status", matcher.get("customer_status") == direct.get("customer_status")))
    checks.append(("live_provenance", bool(matcher.get("live")) == bool(direct.get("live"))))
    if exp_lid in (None, ""):
        checks.append(("expected_location_id", False))
        property_status = "BLOCKED"
        property_reason = "selected_property_missing"
    else:
        if not matcher.get("location_id"):
            checks.append(("matcher_location_id", False))
        else:
            checks.append(("matcher_location_id", str(matcher.get("location_id")) == str(exp_lid)))
        if not direct.get("location_id"):
            checks.append(("direct_location_id", False))
            property_status = "INCOMPLETE"
            property_reason = direct.get("location_reason") or "direct_property_unavailable"
        else:
            checks.append(("direct_location_id", str(direct.get("location_id")) == str(exp_lid)))
            property_status = "ok"
            property_reason = None
    identity_failed = [name for name, ok in checks if not ok and name in {
        "matcher_customer_id",
        "direct_customer_id",
        "customer_status",
        "live_provenance",
        "expected_location_id",
        "matcher_location_id",
        "direct_location_id",
    }]
    if property_reason == "selected_property_missing":
        return {
            "ok": False,
            "identity_ok": False,
            "context_ok": False,
            "status": "BLOCKED",
            "reason": property_reason,
            "failed": identity_failed,
            "checks": [{"name": name, "ok": ok} for name, ok in checks],
        }
    if not direct.get("location_id") and exp_lid:
        return {
            "ok": False,
            "identity_ok": False,
            "context_ok": False,
            "status": "INCOMPLETE",
            "reason": property_reason,
            "failed": identity_failed,
            "checks": [{"name": name, "ok": ok} for name, ok in checks],
        }

    def _require_component(name: str, matcher_ok: bool | None, direct_ok: bool | None, extra: bool | None = None) -> None:
        if direct_ok is False:
            checks.append((f"direct_{name}", False))
            return
        if matcher_ok is False:
            checks.append((f"matcher_{name}", False))
            return
        if extra is False:
            checks.append((name, False))
            return
        checks.append((name, True))

    matcher_omitted = matcher.get("omitted") or {}
    _require_component("notes", matcher.get("notes_ok"), (direct.get("notes") or {}).get("ok") if isinstance(direct.get("notes"), dict) else direct.get("notes_ok"))
    if not direct.get("agreements_ok"):
        checks.append(("direct_agreements", False))
    elif matcher_omitted.get("agreements"):
        checks.append(("matcher_agreements", False))
    else:
        checks.append(("active_agreement_presence", bool(matcher.get("active_agreement")) == bool(direct.get("active_agreement_present"))))
    _require_component(
        "estimates",
        matcher.get("estimates_ok"),
        (direct.get("estimates") or {}).get("ok") if isinstance(direct.get("estimates"), dict) else direct.get("estimates_ok"),
    )
    _require_component(
        "appointments",
        matcher.get("appointments_ok"),
        (direct.get("appointments") or {}).get("ok") if isinstance(direct.get("appointments"), dict) else direct.get("appointments_ok"),
    )
    recent = direct.get("recent_service") or {}
    if recent.get("status") == "unsupported" or (direct.get("work_orders") or {}).get("status") == "unsupported":
        checks.append(("recent_service", False))
        recent_reason = "work_order_customer_filter_unsupported"
    else:
        matcher_last = (matcher.get("last_service") or {}).get("id")
        direct_last = direct.get("last_service_id") or recent.get("id")
        checks.append(("recent_service", matcher_last == direct_last))
        recent_reason = None
    if not direct.get("date_window_applied"):
        checks.append(("date_window_applied", False))
    else:
        checks.append(("date_window_applied", True))

    failed = [name for name, ok in checks if not ok]
    identity_ok = not any(name in failed for name in (
        "matcher_customer_id",
        "direct_customer_id",
        "customer_status",
        "live_provenance",
        "matcher_location_id",
        "direct_location_id",
        "expected_location_id",
    ))
    context_ok = identity_ok and not any(name in failed for name in (
        "notes",
        "direct_notes",
        "matcher_notes",
        "direct_agreements",
        "matcher_agreements",
        "active_agreement_presence",
        "estimates",
        "direct_estimates",
        "matcher_estimates",
        "appointments",
        "direct_appointments",
        "matcher_appointments",
        "recent_service",
        "date_window_applied",
    ))
    if not identity_ok:
        status = "FAIL"
        reason = "identity_or_property_mismatch"
    elif not context_ok:
        status = "INCOMPLETE"
        reason = recent_reason or "context_component_unavailable"
    else:
        status = "PASS"
        reason = None
    return {
        "ok": context_ok,
        "identity_ok": identity_ok,
        "context_ok": context_ok,
        "status": status,
        "reason": reason,
        "failed": failed,
        "checks": [{"name": name, "ok": ok} for name, ok in checks],
    }


def redact_private(evidence: dict[str, Any]) -> dict[str, Any]:
    keep = {
        "status",
        "confidence",
        "reason",
        "customer_id",
        "location_id",
        "customer_status",
        "location_count",
        "match_hits",
        "live",
        "source_label",
        "omitted",
        "booking_state",
        "fixture_id",
        "identity_kind",
        "retrieved_at",
        "write_attempted",
        "client_write_attempts",
        "estimates_count",
        "active_agreement",
        "upcoming_work_orders",
        "upcoming_appointments",
        "last_service",
        "notes_ok",
        "notes_count",
        "agreements_ok",
        "estimates_ok",
        "appointments_ok",
        "work_orders_ok",
        "date_window_days",
    }
    out = {key: evidence.get(key) for key in keep}
    if out.get("active_agreement"):
        out["active_agreement"] = {
            "present": True,
            "status": (evidence.get("active_agreement") or {}).get("status"),
            "id": (evidence.get("active_agreement") or {}).get("id"),
        }
    if out.get("upcoming_work_orders"):
        out["upcoming_work_orders"] = [
            {"id": row.get("id"), "status": row.get("status"), "location_id": row.get("location_id")}
            for row in (evidence.get("upcoming_work_orders") or [])
        ]
    if out.get("upcoming_appointments"):
        out["upcoming_appointments"] = [
            {"id": row.get("id"), "status": row.get("status")} for row in (evidence.get("upcoming_appointments") or [])
        ]
    if out.get("last_service"):
        out["last_service"] = {
            "id": (evidence.get("last_service") or {}).get("id"),
            "status": (evidence.get("last_service") or {}).get("status"),
        }
    out["searches"] = [
        {k: row.get(k) for k in ("count", "ok", "incomplete", "truncated", "reason")}
        for row in (evidence.get("searches") or [])
    ]
    return out


def _scenario_result(scenario: dict[str, Any], matcher: dict[str, Any], comparison: dict[str, Any] | None) -> str:
    if scenario.get("coverage") == "unavailable":
        return "BLOCKED"
    if scenario.get("proof_class") == PROOF_PROVIDER and scenario.get("kind") == "authorized_identity":
        return "INCOMPLETE"
    expect = scenario.get("expect")
    status = matcher.get("status")
    if status == MATCH_BLOCKED:
        return "BLOCKED"
    if status == MATCH_INCOMPLETE:
        return "INCOMPLETE"
    if status == MATCH_INSUFFICIENT:
        return "BLOCKED"
    if expect and status != expect:
        return "FAIL"
    if scenario.get("kind") == "authorized_identity":
        if comparison is None:
            return "BLOCKED"
        if comparison.get("status") == "BLOCKED":
            return "BLOCKED"
        if comparison.get("status") == "INCOMPLETE" or not comparison.get("context_ok"):
            return "INCOMPLETE"
        if not comparison.get("identity_ok"):
            return "FAIL"
        if status not in {MATCH_EXISTING, MATCH_FORMER, MATCH_AMBIGUOUS}:
            return "FAIL"
        return "PASS" if comparison.get("ok") else "FAIL"
    if scenario.get("kind") == "synthetic_no_match" and status != MATCH_NONE:
        return "FAIL"
    return "PASS"


def run_bounded_read(
    client: ReadOnlyFieldworkClient,
    manifest: dict[str, Any],
    *,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    dest = evidence_dir or HOST_EVIDENCE
    _ensure_private_dir(dest)
    window = int(manifest.get("date_window_days") or DEFAULT_DATE_WINDOW_DAYS)
    rows = []
    for scenario in manifest.get("scenarios") or []:
        if scenario.get("coverage") == "unavailable":
            rows.append(
                {
                    "key": scenario["key"],
                    "kind": scenario.get("kind"),
                    "proof_class": scenario.get("proof_class"),
                    "result": "BLOCKED",
                    "reason": scenario.get("reason") or "coverage_unavailable",
                    "matcher_status": None,
                    "live": bool(getattr(client, "live", False)),
                    "inbound_matching_proof": False,
                }
            )
            continue
        receipt = scenario_receipt(scenario)
        if receipt is None:
            rows.append(
                {
                    "key": scenario["key"],
                    "kind": scenario.get("kind"),
                    "proof_class": scenario.get("proof_class"),
                    "result": "BLOCKED",
                    "reason": "insufficient_identifiers",
                    "matcher_status": MATCH_INSUFFICIENT,
                    "live": bool(getattr(client, "live", False)),
                    "inbound_matching_proof": False,
                }
            )
            continue
        matcher = match_and_context(client, receipt, date_window_days=window)
        comparison = None
        direct = None
        if scenario.get("kind") == "authorized_identity":
            direct = direct_read_bundle(
                client,
                scenario.get("customer_id"),
                scenario.get("location_id"),
                date_window_days=window,
            )
            comparison = compare_to_direct(matcher, direct, expected=scenario)
        result = _scenario_result(scenario, matcher, comparison)
        inbound_proof = scenario.get("proof_class") == PROOF_SOURCE and result == "PASS"
        private = {
            "key": scenario["key"],
            "kind": scenario.get("kind"),
            "proof_class": scenario.get("proof_class"),
            "result": result,
            "inbound_matching_proof": inbound_proof,
            "matcher": redact_private(matcher),
            "direct": direct,
            "comparison": comparison,
            "date_window_days": window,
            "request_count": len(getattr(client, "calls", []) or []),
            "write_attempts": client.write_attempts,
        }
        _write_private(dest / f"{scenario['key']}.json", private, 0o600)
        rows.append(
            {
                "key": scenario["key"],
                "kind": scenario.get("kind"),
                "proof_class": scenario.get("proof_class"),
                "result": result,
                "reason": (comparison or {}).get("reason") or matcher.get("reason") or scenario.get("reason"),
                "matcher_status": matcher.get("status"),
                "live": bool(matcher.get("live")),
                "source_label": matcher.get("source_label"),
                "customer_id_present": bool(matcher.get("customer_id")),
                "location_id_present": bool(matcher.get("location_id")),
                "comparison_ok": None if comparison is None else comparison.get("ok"),
                "identity_ok": None if comparison is None else comparison.get("identity_ok"),
                "context_ok": None if comparison is None else comparison.get("context_ok"),
                "inbound_matching_proof": inbound_proof,
                "omitted_keys": sorted((matcher.get("omitted") or {}).keys()),
            }
        )
    overall = "PASS"
    if any(row["result"] == "FAIL" for row in rows):
        overall = "FAIL"
    elif any(row["result"] in {"BLOCKED", "INCOMPLETE"} for row in rows):
        overall = "BLOCKED" if any(row["result"] == "BLOCKED" for row in rows) else "INCOMPLETE"
    if client.write_attempts:
        overall = "FAIL"
    scorecard = {
        "overall": overall,
        "live": bool(getattr(client, "live", False)),
        "source_label": LABEL_LIVE if getattr(client, "live", False) else LABEL_FIXTURE,
        "date_window_days": window,
        "write_attempts": client.write_attempts,
        "request_count": len(getattr(client, "calls", []) or []),
        "retrieved_at": utc_now(),
        "scenarios": rows,
        "drafted": False,
        "enqueued": False,
        "sent": False,
        "receiver_unchanged": True,
        "coverage": {
            "identity": all(row.get("identity_ok") is not False for row in rows if row.get("kind") == "authorized_identity"),
            "context": all(row.get("context_ok") for row in rows if row.get("kind") == "authorized_identity" and row.get("result") == "PASS"),
            "provenance": all(row.get("live") is bool(getattr(client, "live", False)) for row in rows if row.get("matcher_status")),
            "inbound_matching_proof": any(row.get("inbound_matching_proof") for row in rows),
        },
    }
    _write_private(dest / "scorecard.json", scorecard, 0o600)
    return scorecard


def client_for_mode(mode: str) -> ReadOnlyFieldworkClient:
    if mode == "fixture":
        return fixture_client()
    return live_read_client()
