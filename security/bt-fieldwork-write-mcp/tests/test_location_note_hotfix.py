"""Location-note 204 readback and structural token redaction. No live calls."""

from __future__ import annotations

import base64
import json
import unittest
from urllib.request import Request

from bt_fieldwork_write_mcp.fieldwork import HttpTransport, TypedFieldworkClient
from bt_fieldwork_write_mcp.redact import redact
from bt_fieldwork_write_mcp.secrets import InMemoryApiKey
from tests.test_write_mcp import IDENTITY, Harness

NOTE = "leave the gate open"
SPIDER = "Customer is very afraid of spiders. Please be especially attentive to spider activity and webbing during service."


def _segment(value: dict | str) -> str:
    raw = value if isinstance(value, str) else json.dumps(value, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _token() -> str:
    return f"{_segment({'alg': 'none', 'typ': 'JWT'})}.{_segment({'sub': '1'})}.{_segment('sig')}"


class _Response:
    def __init__(self, status: int, body: bytes = b"") -> None:
        self.status = status
        self.headers = {"Content-Type": "application/json"}
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> bool:
        return False


class Script:
    def __init__(self, patch_status: int = 204, *, land: bool = True, get_note: str | None = None, get_name: str = "House", fail_readback: bool = False, drop_patch: bool = False) -> None:
        self.requests: list[Request] = []
        self.patch_status = patch_status
        self.land = land
        self.get_note = get_note
        self.get_name = get_name
        self.fail_readback = fail_readback
        self.drop_patch = drop_patch
        self.patched = False
        self.notes = "old note"

    def open(self, req: Request, timeout: int = 30) -> _Response:
        path = req.full_url.split("api3.fieldworkhq.com")[-1].split("?")[0].split("/v3.1", 1)[-1]
        if req.method == "PATCH" and path.endswith("/service_locations/77"):
            self.requests.append(req)
            self.patched = True
            if self.land:
                self.notes = NOTE
            if self.drop_patch:
                raise TimeoutError("drop")
            return _Response(self.patch_status, b"")
        self.requests.append(req)
        if self.fail_readback and self.patched and req.method == "GET" and path.endswith("/service_locations/77"):
            return _Response(500, b"")
        return _Response(200, json.dumps(self._get(path)).encode())

    def _get(self, path: str):
        if path == "/profile":
            return {"roles": ["schedule", "customers", "invoicing", "reporting", "agreements", "tasks", "work_orders"]}
        if path == "/customers/41":
            return {"id": 41, "customer_status": "Active", "name": "Existing"}
        if path == "/customers/41/service_locations/77":
            note = self.get_note if self.patched and self.get_note is not None else self.notes
            return {"service_location": {"id": 77, "customer_id": 41, "name": self.get_name, "tax_rate_id": 3, "address": {"id": 900, "notes": note}}}
        return []

    def patches(self) -> int:
        return sum(1 for req in self.requests if req.method == "PATCH")


class LocationNoteHotfixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness(writes_enabled=True, api_role="writer")

    def tearDown(self) -> None:
        self.h.close()

    def _run(self, script: Script) -> dict:
        self.script = script
        self.h.service.client = TypedFieldworkClient(HttpTransport(InMemoryApiKey("hidden-key"), opener=script))
        proposed = self.h.propose_notes(NOTE)
        self.assertTrue(proposed["ok"], proposed)
        self.proposal = proposed
        token = self.h.approve(proposed["proposal_id"])
        return self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=token)

    def test_204_and_matching_get_executes(self) -> None:
        done = self._run(Script())
        self.assertTrue(done["ok"], done)
        self.assertEqual(done["readback"]["notes"], NOTE)
        self.assertEqual(done["readback"]["name"], "House")
        self.assertEqual(done["readback"]["tax_rate_id"], 3)
        self.assertEqual(done["readback"]["address_id"], 900)
        self.assertEqual(self.h.store.get_proposal(self.proposal["proposal_id"])["status"], "executed")
        self.assertEqual(self.script.patches(), 1)

    def test_204_and_failed_get_stays_ambiguous(self) -> None:
        failed = self._run(Script(fail_readback=True))
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["retry"], False)
        self.assertEqual(self.h.store.get_proposal(self.proposal["proposal_id"])["status"], "ambiguous")
        self.assertEqual(self.script.patches(), 1)

    def test_204_and_mismatched_get_stays_ambiguous(self) -> None:
        mismatched = self._run(Script(get_note="different note", get_name="Shed"))
        self.assertFalse(mismatched["ok"])
        self.assertEqual(mismatched["retry"], False)
        self.assertEqual(self.h.store.get_proposal(self.proposal["proposal_id"])["status"], "ambiguous")
        self.assertEqual(self.script.patches(), 1)

    def test_ambiguous_patch_reconciles_from_get_without_a_second_patch(self) -> None:
        done = self._run(Script(drop_patch=True))
        self.assertTrue(done["ok"], done)
        self.assertTrue(done["ambiguity_reconciled"])
        self.assertEqual(done["readback"]["notes"], NOTE)
        self.assertEqual(self.script.patches(), 1)
        self.assertEqual(self.h.store.get_proposal(self.proposal["proposal_id"])["status"], "executed")

    def test_explicit_rejection_stays_rejected(self) -> None:
        rejected = self._run(Script(patch_status=422, land=False))
        self.assertEqual(rejected["gate"], "location_patch_rejected")
        self.assertEqual(rejected["retry"], False)
        self.assertEqual(self.h.store.get_proposal(self.proposal["proposal_id"])["status"], "rejected")
        self.assertEqual(self.script.patches(), 1)

    def test_ordinary_note_survives_and_tokens_stay_redacted(self) -> None:
        token = _token()
        self.assertEqual(redact(SPIDER), SPIDER)
        self.assertEqual(redact(token), "[redacted-jwt]")
        self.assertEqual(redact(f"Before {token} after."), "Before [redacted-jwt] after.")
        masked = redact({"password": "hunter2", "note": SPIDER, "nested": {"api_key": token, "token": "plain"}})
        self.assertEqual(masked["password"], "[redacted]")
        self.assertEqual(masked["note"], SPIDER)
        self.assertEqual(masked["nested"]["api_key"], "[redacted]")
        self.assertEqual(masked["nested"]["token"], "[redacted]")
