"""Explicit bounded Fieldwork live-read runner. Does not draft, enqueue, or send."""

from __future__ import annotations

import json
import os
import stat
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
    match_and_context,
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
DEFAULT_DATE_WINDOW_DAYS = 365

def fixture_client(catalog_path: Path | None = None) -> GrokBotFieldwork:
    client = GrokBotFieldwork(catalog_path=catalog_path or SYNTHETIC_CATALOG)
    client.max_requests = RUNNER_MAX_REQUESTS
    return client


def _write_private(path: Path, payload: dict[str, Any], mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    path.chmod(mode)


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
            "host_command": (
                "On the approved host only: "
                "BT_FIELDWORK_LIVE_READ=1 FIELDWORK_API_KEY_FILE=<host-secret-file> "
                "PYTHONPATH=src python3 -m bt_intake_proof.cli live-fw-preflight --mode live"
            ),
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
        }
    if token_file and not Path(token_file).exists():
        return {
            "ok": False,
            "status": "BLOCKED",
            "mode": "live",
            "reason": "token_file_missing",
            "token_file_configured": True,
            "token_file_exists": False,
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


def issue_key_to_file(path: str) -> dict[str, Any]:
    """Host-only: write an API key to a 0600 file. Never returns the key."""
    if os.environ.get("BT_FIELDWORK_LIVE_READ") != "1":
        return {"ok": False, "status": "BLOCKED", "reason": "live_read_not_enabled"}
    dest = Path(path)
    client = ReadOnlyFieldworkClient(live=True)
    issued = client.login_for_token()
    if not issued.get("ok") or not client.token:
        return {
            "ok": False,
            "status": "BLOCKED",
            "reason": issued.get("reason") or "fieldwork_api_key_not_issued",
            "file_written": False,
        }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(client.token + "\n", encoding="utf-8")
    dest.chmod(0o600)
    client.token = None
    return {
        "ok": True,
        "status": "PASS",
        "file_written": dest.exists(),
        "file_mode": oct(stat.S_IMODE(dest.stat().st_mode)),
        "user_id": issued.get("user_id"),
        "roles": issued.get("roles"),
        "customer_access": issued.get("customer_access"),
        "provider_token_scope_verified": False,
        "adapter_enforced_read_only": True,
    }


def _search_unique_customer(client: ReadOnlyFieldworkClient, name: str) -> dict[str, Any]:
    fetched = as_fetch(client.search_customers(name))
    if not fetched.ok:
        return {"status": "BLOCKED", "reason": fetched.reason or "read_failed", "hit_count": 0}
    if fetched.incomplete or fetched.truncated:
        return {"status": "BLOCKED", "reason": fetched.reason or "pagination_truncated", "hit_count": len(fetched)}
    ids = []
    for row in fetched:
        cid = str(row.get("id") or row.get("customer_id") or "")
        if cid and cid not in ids:
            ids.append(cid)
    if len(ids) == 1:
        return {"status": "PASS", "reason": None, "hit_count": 1, "customer_id": ids[0]}
    if len(ids) == 0:
        return {"status": "BLOCKED", "reason": "authorized_name_not_found", "hit_count": 0}
    return {"status": "BLOCKED", "reason": "authorized_name_not_unique", "hit_count": len(ids)}


def _location_count(client: ReadOnlyFieldworkClient, customer_id: str) -> dict[str, Any]:
    fetched = as_fetch(client.list_locations(customer_id))
    if not fetched.ok:
        return {"ok": False, "count": 0, "reason": fetched.reason, "location_ids": []}
    ids = [str(row.get("id")) for row in fetched if row.get("id") is not None]
    return {
        "ok": True,
        "count": len(ids),
        "reason": fetched.reason if fetched.incomplete else None,
        "location_ids": ids,
        "incomplete": fetched.incomplete,
        "streets_present": [
            bool((row.get("address") or row.get("address_attributes") or {}).get("street")) for row in fetched
        ],
    }


def resolve_authorized(
    client: ReadOnlyFieldworkClient,
    *,
    labels: tuple[dict[str, str], ...] | list[dict[str, str]] = AUTHORIZED_LABELS,
    out_path: Path | None = None,
) -> dict[str, Any]:
    """Resolve at most the 3 authorized labels to native IDs. Stdout stays redacted."""
    resolved = []
    blocked = False
    for label in labels[:MAX_REAL_CASES]:
        found = _search_unique_customer(client, label["search_name"])
        item = {
            "key": label["key"],
            "status": found["status"],
            "reason": found.get("reason"),
            "hit_count": found.get("hit_count") or 0,
            "customer_id": found.get("customer_id"),
        }
        if found.get("customer_id"):
            locs = _location_count(client, found["customer_id"])
            item["location_count"] = locs.get("count")
            item["location_ids"] = locs.get("location_ids")
            item["locations_ok"] = locs.get("ok")
            if not locs.get("ok"):
                item["status"] = "BLOCKED"
                item["reason"] = locs.get("reason")
        if item["status"] != "PASS":
            blocked = True
        resolved.append(item)

    probes = _derive_probes(client, resolved)
    scenarios = []
    for item in resolved:
        scenarios.append(
            {
                "key": item["key"],
                "kind": "authorized_identity",
                "customer_id": item.get("customer_id"),
                "location_id": (item.get("location_ids") or [None])[0] if item.get("location_count") == 1 else None,
                "status": item["status"],
                "reason": item.get("reason"),
            }
        )
    for probe in probes[:MAX_AMBIGUITY_PROBES]:
        scenarios.append(probe)
    scenarios.append(
        {
            "key": "synthetic_no_match",
            "kind": "synthetic_no_match",
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
        "live": bool(getattr(client, "live", False)),
        "source_label": LABEL_LIVE if getattr(client, "live", False) else LABEL_FIXTURE,
        "max_real_cases": MAX_REAL_CASES,
        "max_ambiguity_probes": MAX_AMBIGUITY_PROBES,
        "max_synthetic_no_match": MAX_SYNTHETIC_NO_MATCH,
        "date_window_days": DEFAULT_DATE_WINDOW_DAYS,
        "authorized": resolved,
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
                "customer_id_present": bool(item.get("customer_id")),
                "location_count": item.get("location_count"),
            }
            for item in resolved
        ],
        "probe_keys": [row["key"] for row in probes],
        "write_attempts": client.write_attempts,
        "request_count": len(getattr(client, "calls", []) or []),
    }
    return public


def _derive_probes(client: ReadOnlyFieldworkClient, resolved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []
    usable = [item for item in resolved if item.get("status") == "PASS" and item.get("customer_id")]
    multi = [item for item in usable if int(item.get("location_count") or 0) > 1]
    if multi:
        first = multi[0]
        probes.append(
            {
                "key": "ambiguity_probe_1",
                "kind": "ambiguity_multi_property",
                "customer_id": first["customer_id"],
                "location_id": None,
                "expect": MATCH_AMBIGUOUS,
                "omit_street": True,
                "coverage": "available",
            }
        )
        streets = []
        locs = as_fetch(client.list_locations(first["customer_id"]))
        if locs.ok:
            for loc in locs:
                addr = loc.get("address") or loc.get("address_attributes") or {}
                streets.append(str(addr.get("street") or ""))
        numbers = [row.split()[0] for row in streets if row.split()]
        collision = False
        for idx, num in enumerate(numbers):
            for other in numbers[idx + 1 :]:
                if num != other and (num in other or other in num):
                    collision = True
        if collision:
            probes.append(
                {
                    "key": "ambiguity_probe_2",
                    "kind": "ambiguity_street_number",
                    "customer_id": first["customer_id"],
                    "location_id": None,
                    "expect": MATCH_AMBIGUOUS,
                    "street_number_only": True,
                    "coverage": "available",
                }
            )
        else:
            probes.append(
                {
                    "key": "ambiguity_probe_2",
                    "kind": "ambiguity_name_only",
                    "customer_id": first["customer_id"],
                    "expect": MATCH_AMBIGUOUS,
                    "coverage": "available",
                    "note": "multiple-property street-number collision not established; name-only probe used",
                }
            )
    elif usable:
        first = usable[0]
        probes.append(
            {
                "key": "ambiguity_probe_1",
                "kind": "ambiguity_name_only",
                "customer_id": first["customer_id"],
                "expect": MATCH_AMBIGUOUS,
                "coverage": "available",
            }
        )
        probes.append(
            {
                "key": "ambiguity_probe_2",
                "kind": "multiple_property_coverage",
                "customer_id": None,
                "expect": None,
                "coverage": "unavailable",
                "reason": "no_multiple_property_in_bounded_set",
            }
        )
    else:
        probes.append(
            {
                "key": "ambiguity_probe_1",
                "kind": "ambiguity_unavailable",
                "coverage": "unavailable",
                "reason": "authorized_cases_not_resolved",
                "expect": None,
            }
        )
        probes.append(
            {
                "key": "ambiguity_probe_2",
                "kind": "multiple_property_coverage",
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


def scenario_receipt(scenario: dict[str, Any], customer: dict[str, Any] | None = None) -> dict[str, Any]:
    kind = scenario.get("kind")
    if kind == "synthetic_no_match":
        query = scenario.get("query") or SYNTHETIC_NO_MATCH_QUERY
        body = (
            f"This is Nobody Proof at 999 Missing Avenue, Nowhere NC 00000. "
            f"910-555-0000 nobody.proof.syn@example.org {query}"
        )
        return {"sender": "nobody.proof.syn@example.org", "subject": query, "body_text": body}
    if kind == "ambiguity_name_only":
        name = (customer or {}).get("name") or "Authorized Customer"
        return {"sender": "daniel@btpestcontrol.com", "subject": "name only", "body_text": f"This is {name}."}
    if kind == "ambiguity_multi_property":
        name = (customer or {}).get("name") or "Authorized Customer"
        email = (customer or {}).get("email") or "auth.syn@example.com"
        phone = (customer or {}).get("phone") or "9105550001"
        return {
            "sender": email,
            "subject": "multi property",
            "body_text": f"This is {name}. Please call {phone}. {email}",
        }
    if kind == "ambiguity_street_number":
        name = (customer or {}).get("name") or "Authorized Customer"
        email = (customer or {}).get("email") or "auth.syn@example.com"
        phone = (customer or {}).get("phone") or "9105550001"
        return {
            "sender": email,
            "subject": "street number only",
            "body_text": f"This is {name}. Ants at 14 Court, Holly Ridge NC 28445. {phone} {email}",
        }
    name = (customer or {}).get("name") or "Authorized Customer"
    email = (customer or {}).get("email") or "auth.syn@example.com"
    phone = (customer or {}).get("phone") or "9105550001"
    loc = ((customer or {}).get("locations") or [{}])[0]
    addr = (loc.get("address") or {}) if isinstance(loc, dict) else {}
    street = addr.get("street") or "14 Fixture Lane"
    city = addr.get("city") or "Holly Ridge"
    zipc = addr.get("zip") or "28445"
    return {
        "sender": email,
        "subject": "authorized identity",
        "body_text": f"This is {name}. Ants at {street}, {city} NC {zipc}. {phone} {email}",
    }


def direct_read_bundle(
    client: ReadOnlyFieldworkClient,
    customer_id: str | None,
    location_id: str | None = None,
    *,
    date_window_days: int = DEFAULT_DATE_WINDOW_DAYS,
) -> dict[str, Any]:
    """Native-ID reads. Does not call matcher, score, or classify."""
    if not customer_id:
        return {"ok": False, "reason": "no_customer_id", "live": bool(getattr(client, "live", False))}
    try:
        customer = client.get_customer(customer_id)
    except FieldworkReadError as exc:
        return {"ok": False, "reason": exc.reason, "customer_id": customer_id, "live": bool(getattr(client, "live", False))}
    location = None
    location_reason = None
    if location_id:
        try:
            location = client.get_location(location_id, customer_id)
        except FieldworkReadError as exc:
            location_reason = exc.reason
    locations = as_fetch(client.list_locations(customer_id))
    notes = as_fetch(client.list_notes(customer_id))
    agreements = as_fetch(client.list_agreements(**{"filter[customer_id]": customer_id}))
    estimates = as_fetch(client.list_estimates(**{"filter[customer_id]": customer_id}))
    work_orders = as_fetch(client.search_work_orders(**{"filter[customer_id]": customer_id}))
    appointments = []
    appt_ok = True
    appt_reason = None
    if agreements.ok:
        for agr in list(agreements)[:5]:
            if agr.get("id") is None:
                continue
            fetched = as_fetch(client.list_agreement_appointments(agr["id"]))
            if not fetched.ok:
                appt_ok = False
                appt_reason = fetched.reason
                break
            appointments.extend(list(fetched))
    return {
        "ok": True,
        "live": bool(getattr(client, "live", False)),
        "retrieved_at": utc_now(),
        "date_window_days": date_window_days,
        "customer_id": str(customer.get("id") or customer_id),
        "customer_status": _status(customer),
        "location_id": str(location.get("id")) if isinstance(location, dict) and location.get("id") is not None else None,
        "location_reason": location_reason,
        "location_count": len(locations) if locations.ok else None,
        "notes_ok": notes.ok,
        "notes_count": len(notes) if notes.ok else None,
        "agreements_ok": agreements.ok,
        "agreements_count": len(agreements) if agreements.ok else None,
        "active_agreement_present": bool(
            agreements.ok
            and any(str(row.get("status") or row.get("state") or "").lower() in {"active", "current"} for row in agreements)
        ),
        "estimates_ok": estimates.ok,
        "estimates_count": len(estimates) if estimates.ok else None,
        "work_orders_ok": work_orders.ok,
        "work_orders_count": len(work_orders) if work_orders.ok else None,
        "appointments_ok": appt_ok,
        "appointments_count": len(appointments) if appt_ok else None,
        "appointments_reason": appt_reason,
        "locations_ok": locations.ok,
        "request_count": len(getattr(client, "calls", []) or []),
        "write_attempts": client.write_attempts,
    }


def compare_to_direct(matcher: dict[str, Any], direct: dict[str, Any]) -> dict[str, Any]:
    """Compare matcher identity fields to a separate native-ID read. Not a self-check."""
    checks = []
    if matcher.get("status") in {MATCH_EXISTING, MATCH_FORMER}:
        checks.append(("customer_id", str(matcher.get("customer_id") or "") == str(direct.get("customer_id") or "")))
        checks.append(("customer_status", matcher.get("customer_status") == direct.get("customer_status")))
        if matcher.get("location_id") and direct.get("location_id"):
            checks.append(("location_id", str(matcher.get("location_id")) == str(direct.get("location_id"))))
        if direct.get("agreements_ok"):
            matcher_omitted = bool((matcher.get("omitted") or {}).get("agreements"))
            if not matcher_omitted:
                checks.append(
                    (
                        "active_agreement_presence",
                        bool(matcher.get("active_agreement")) == bool(direct.get("active_agreement_present"))
                        or bool(matcher.get("active_agreement"))
                        or not direct.get("active_agreement_present"),
                    )
                )
        if matcher.get("live") != direct.get("live"):
            checks.append(("live_provenance", False))
        else:
            checks.append(("live_provenance", True))
    failed = [name for name, ok in checks if not ok]
    return {"ok": not failed, "failed": failed, "checks": [{"name": name, "ok": ok} for name, ok in checks]}


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
        "last_service",
    }
    out = {key: evidence.get(key) for key in keep}
    if out.get("active_agreement"):
        out["active_agreement"] = {
            "present": True,
            "status": (evidence.get("active_agreement") or {}).get("status"),
        }
    if out.get("upcoming_work_orders"):
        out["upcoming_work_orders"] = [
            {"id": row.get("id"), "status": row.get("status"), "location_id": row.get("location_id")}
            for row in (evidence.get("upcoming_work_orders") or [])
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
    expect = scenario.get("expect")
    status = matcher.get("status")
    if status in {MATCH_BLOCKED, MATCH_INCOMPLETE, MATCH_INSUFFICIENT}:
        return "BLOCKED" if status == MATCH_BLOCKED else status.upper() if status == MATCH_INCOMPLETE else "FAIL"
    if expect and status != expect:
        return "FAIL"
    if scenario.get("kind") == "authorized_identity":
        if status not in {MATCH_EXISTING, MATCH_FORMER, MATCH_AMBIGUOUS}:
            return "FAIL"
        if comparison and not comparison.get("ok") and status in {MATCH_EXISTING, MATCH_FORMER}:
            return "FAIL"
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
    dest.mkdir(parents=True, exist_ok=True)
    dest.chmod(0o700)
    window = int(manifest.get("date_window_days") or DEFAULT_DATE_WINDOW_DAYS)
    rows = []
    for scenario in manifest.get("scenarios") or []:
        if scenario.get("coverage") == "unavailable":
            rows.append(
                {
                    "key": scenario["key"],
                    "kind": scenario.get("kind"),
                    "result": "BLOCKED",
                    "reason": scenario.get("reason") or "coverage_unavailable",
                    "matcher_status": None,
                    "live": bool(getattr(client, "live", False)),
                }
            )
            continue
        customer = None
        if scenario.get("customer_id"):
            try:
                customer = client.get_customer(scenario["customer_id"])
            except FieldworkReadError as exc:
                rows.append(
                    {
                        "key": scenario["key"],
                        "kind": scenario.get("kind"),
                        "result": "BLOCKED",
                        "reason": exc.reason,
                        "matcher_status": MATCH_BLOCKED,
                        "live": bool(getattr(client, "live", False)),
                    }
                )
                continue
        receipt = scenario_receipt(scenario, customer)
        matcher = match_and_context(client, receipt)
        comparison = None
        direct = None
        if scenario.get("kind") == "authorized_identity" and matcher.get("customer_id"):
            direct = direct_read_bundle(
                client,
                matcher.get("customer_id"),
                matcher.get("location_id"),
                date_window_days=window,
            )
            comparison = compare_to_direct(matcher, direct)
        result = _scenario_result(scenario, matcher, comparison)
        private = {
            "key": scenario["key"],
            "kind": scenario.get("kind"),
            "result": result,
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
                "result": result,
                "reason": matcher.get("reason") or scenario.get("reason"),
                "matcher_status": matcher.get("status"),
                "live": bool(matcher.get("live")),
                "source_label": matcher.get("source_label"),
                "customer_id_present": bool(matcher.get("customer_id")),
                "location_id_present": bool(matcher.get("location_id")),
                "comparison_ok": None if comparison is None else comparison.get("ok"),
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
    }
    _write_private(dest / "scorecard.json", scorecard, 0o600)
    return scorecard


def client_for_mode(mode: str) -> ReadOnlyFieldworkClient:
    if mode == "fixture":
        return fixture_client()
    return live_read_client()
