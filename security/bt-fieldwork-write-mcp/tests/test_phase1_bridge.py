"""Phase 1 checks on the FastMCP Auth0 bridge call path. Offline only."""

from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from starlette.testclient import TestClient

from bt_fieldwork_write_mcp.digest import proposal_digest
from bt_fieldwork_write_mcp.secrets import InMemoryApiKey
from bt_fieldwork_write_mcp.server import build_bridge_server
from tests.test_auth0_asgi import BridgeAsgiTests
from tests.test_auth0_bridge import _bridge
from tests.test_write_mcp import IDENTITY, OTHER


def _payload(text: str) -> dict:
    start = text.find("{")
    return json.loads(text[start:])


def _tool(text: str) -> dict:
    message = _payload(text)
    data = message["result"]["content"][0]["text"]
    return json.loads(data)


class Phase1BridgeTests(unittest.TestCase):
    """Own TestCase so the Auth0 ASGI suite is not re-run against phase-1 settings."""

    setUp = BridgeAsgiTests.setUp
    tearDown = BridgeAsgiTests.tearDown
    _discovery = BridgeAsgiTests._discovery
    _sign = BridgeAsgiTests._sign
    _set_identity = BridgeAsgiTests._set_identity
    _login = BridgeAsgiTests._login
    _call = BridgeAsgiTests._call

    def _prepare(self, *, role: str = "writer", writes: bool = True, mapping: bool = True, approval: str = "chatgpt_confirmation") -> None:
        self.h.service.settings = replace(
            self.h.settings,
            writes_enabled=writes,
            mapping_verified=mapping,
            approval_mode=approval,
            api_role=role if role in {"writer", "readonly"} else "readonly",
        )
        self.h.transport.api_role = role
        self.h.transport._key = InMemoryApiKey("phase1-fake-key")
        self._bridge_settings = _bridge(
            self.root,
            writes_enabled=writes,
            mapping_verified=mapping,
            approval_mode=approval,
        )

    def _app(self):
        if not hasattr(self, "_bridge_settings"):
            self._prepare()
        mcp = build_bridge_server(self._bridge_settings, self.h.service, fieldwork_key="fieldwork-not-oauth")
        return mcp.http_app(transport="http", allowed_hosts=["*"])

    def _session(self) -> tuple[TestClient, str]:
        client = TestClient(self._app(), base_url="https://write.example.test")
        client.__enter__()
        _client_id, access, _refresh, _code = self._login(client)
        return client, access

    def _propose(self, client: TestClient, access: str, notes: str = "porch light") -> dict:
        raw = self._call(
            client,
            access,
            "propose_write",
            {"operation": "update_service_location_notes", "payload": {"customer_id": 41, "location_id": 77, "notes": notes}},
        )
        return _tool(raw)

    def test_explicit_confirmation_and_rejections(self) -> None:
        self._prepare()
        client, access = self._session()
        try:
            proposed = self._propose(client, access)
            self.assertTrue(proposed["ok"], proposed)
            digest = proposed["digest"]
            proposal_id = proposed["proposal_id"]
            missing_approval = _tool(self._call(client, access, "execute_approved_write", {"proposal_id": proposal_id, "expected_digest": digest}))
            self.assertEqual(missing_approval["gate"], "operator_approval_required")
            missing_digest = _tool(self._call(client, access, "execute_approved_write", {"proposal_id": proposal_id, "approved": True}))
            self.assertEqual(missing_digest["gate"], "operator_approval_required")
            wrong = _tool(self._call(client, access, "execute_approved_write", {"proposal_id": proposal_id, "approved": True, "expected_digest": "0" * 64}))
            self.assertEqual(wrong["gate"], "operator_approval_required")
            self.h.transport.locations["41:77"]["address"]["notes"] = "changed underfoot"
            stale = _tool(self._call(client, access, "execute_approved_write", {"proposal_id": proposal_id, "approved": True, "expected_digest": digest}))
            self.assertEqual(stale["gate"], "stale_state")
        finally:
            client.__exit__(None, None, None)

    def test_expired_tamper_cross_identity_replay_and_flags(self) -> None:
        self._prepare()
        client, access = self._session()
        try:
            first = self._propose(client, access, "first note")
            self.h.transport.locations["41:77"]["address"]["notes"] = "old note"
            self.h.store.release_open_guard(first["gates"].get("subject", "location:41:77") if False else "location:41:77", first["proposal_id"])
            self.h.store.set_status(first["proposal_id"], "expired")
            self.h.store._conn.execute(
                "UPDATE proposals SET status='proposed', expires_at=? WHERE proposal_id=?",
                ("2020-01-01T00:00:00Z", first["proposal_id"]),
            )
            # expiry is inside the digest, so a shortened expiry is a stored mismatch and is not rewritten
            before = self.h.store.get_proposal(first["proposal_id"])
            expired = _tool(self._call(client, access, "execute_approved_write", {"proposal_id": first["proposal_id"], "approved": True, "expected_digest": first["digest"]}))
            self.assertEqual(expired["reason"], "stored_proposal_digest_mismatch")
            after = self.h.store.get_proposal(first["proposal_id"])
            self.assertEqual(after["status"], before["status"])
            self.assertEqual(after["expires_at"], before["expires_at"])
            self.assertEqual(after["digest"], before["digest"])

            self.h.store.release_open_guard("location:41:77", first["proposal_id"])
            self.h.store.set_status(first["proposal_id"], "stale")
            clocked = self._propose(client, access, "clock note")
            expires_at = self.h.store.get_proposal(clocked["proposal_id"])["expires_at"]
            self.h.service._now = lambda: datetime.fromisoformat(expires_at.replace("Z", "+00:00")) + timedelta(seconds=1)
            aged = _tool(self._call(client, access, "execute_approved_write", {"proposal_id": clocked["proposal_id"], "approved": True, "expected_digest": clocked["digest"]}))
            self.assertEqual(aged["gate"], "approval_or_proposal_expired")
            self.assertEqual(self.h.store.get_proposal(clocked["proposal_id"])["status"], "expired")
            self.h.service._now = lambda: datetime.now(timezone.utc)

            live = self._propose(client, access, "live note")
            row = self.h.store.get_proposal(live["proposal_id"])
            self.h.store._conn.execute(
                "UPDATE proposals SET payload_json=?, after_json=? WHERE proposal_id=?",
                (json.dumps({"customer_id": 41, "location_id": 77, "notes": "tampered"}), json.dumps({**row["after"], "notes": "tampered"}), live["proposal_id"]),
            )
            tampered = _tool(self._call(client, access, "execute_approved_write", {"proposal_id": live["proposal_id"], "approved": True, "expected_digest": live["digest"]}))
            self.assertEqual(tampered["reason"], "stored_proposal_digest_mismatch")
            self.assertEqual(self.h.store.get_proposal(live["proposal_id"])["digest"], live["digest"])

            self.h.store.release_open_guard("location:41:77", live["proposal_id"])
            self.h.store.set_status(live["proposal_id"], "stale")
            one = self._propose(client, access, "same change")
            self.h.store.release_open_guard("location:41:77", one["proposal_id"])
            self.h.store.set_status(one["proposal_id"], "stale")
            two = self._propose(client, access, "same change")
            self.assertNotEqual(one["proposal_id"], two["proposal_id"])
            self.assertNotEqual(one["digest"], two["digest"])
            crossed = _tool(self._call(client, access, "execute_approved_write", {"proposal_id": two["proposal_id"], "approved": True, "expected_digest": one["digest"]}))
            self.assertEqual(crossed["gate"], "operator_approval_required")

            foreign_id = "foreign-owned"
            foreign_fields = {
                "proposal_id": foreign_id,
                "operation": "update_service_location_notes",
                "identity": OTHER,
                "target": "location:9:9",
                "before": {"notes": "theirs"},
                "after": {"notes": "edited"},
                "payload": {"customer_id": 9, "location_id": 9, "notes": "edited"},
                "created_at": "2020-01-01T00:00:00Z",
                "expires_at": "2099-01-01T00:00:00Z",
            }
            foreign_digest = proposal_digest(**foreign_fields)
            self.h.store.create_proposal(
                {
                    "proposal_id": foreign_id,
                    "operation": foreign_fields["operation"],
                    "identity_sub": OTHER["sub"],
                    "identity_email": OTHER["email"],
                    "subject_key": foreign_fields["target"],
                    "before": foreign_fields["before"],
                    "after": foreign_fields["after"],
                    "payload": foreign_fields["payload"],
                    "digest": foreign_digest,
                    "created_at": foreign_fields["created_at"],
                    "expires_at": foreign_fields["expires_at"],
                }
            )
            foreign = _tool(self._call(client, access, "execute_approved_write", {"proposal_id": foreign_id, "approved": True, "expected_digest": foreign_digest}))
            self.assertEqual(foreign["gate"], "identity_mismatch")
            self.assertEqual(self.h.store.get_proposal(foreign_id)["status"], "proposed")
            self.assertEqual(self.h.store.get_proposal(foreign_id)["digest"], foreign_digest)

            done = _tool(self._call(client, access, "execute_approved_write", {"proposal_id": two["proposal_id"], "approved": True, "expected_digest": two["digest"]}))
            self.assertTrue(done["ok"], done)
            self.assertIn("readback", done)
            replay = _tool(self._call(client, access, "execute_approved_write", {"proposal_id": two["proposal_id"], "approved": True, "expected_digest": two["digest"]}))
            self.assertEqual(replay["gate"], "approval_replayed")
        finally:
            client.__exit__(None, None, None)

    def test_disabled_flag_wrong_pair_unknown_role_and_legacy_mode(self) -> None:
        self._prepare(writes=False)
        client, access = self._session()
        try:
            proposed = self._propose(client, access, "while disabled")
            self.assertTrue(proposed["ok"], proposed)
            blocked = _tool(self._call(client, access, "execute_approved_write", {"proposal_id": proposed["proposal_id"], "approved": True, "expected_digest": proposed["digest"]}))
            self.assertEqual(blocked["gate"], "writes_disabled")
            pair = _tool(self._call(client, access, "propose_write", {"operation": "update_work_order_notes", "payload": {"work_order_id": "10", "service_appointment_id": "99", "instructions": "no"}}))
            self.assertFalse(pair["ok"])
            self.h.service.settings = replace(self.h.service.settings, writes_enabled=True)
            self.h.transport.api_role = "unknown"
            self.h.service._readiness = None
            unknown = _tool(self._call(client, access, "execute_approved_write", {"proposal_id": proposed["proposal_id"], "approved": True, "expected_digest": proposed["digest"]}))
            self.assertEqual(unknown["gate"], "api_role_unverified")
        finally:
            client.__exit__(None, None, None)
        self._prepare(approval="operator")
        client, access = self._session()
        try:
            legacy = _tool(self._call(client, access, "execute_approved_write", {"proposal_id": "none", "approved": True, "expected_digest": "abc"}))
            self.assertEqual(legacy["gate"], "approval_mode_unsupported")
            self.assertEqual(legacy["reason"], "mcp_execution_requires_chatgpt_confirmation")
            self.assertNotIn("operator_approval", self._call(client, access, "report_gates"))
        finally:
            client.__exit__(None, None, None)

    def test_readiness_snapshot_is_single_and_consistent(self) -> None:
        cases = ("writer", "readonly", "fail")
        for role in cases:
            self._prepare(role="writer" if role == "fail" else role)
            self.h.transport.api_role = role
            self.h.service._readiness = None
            client, access = self._session()
            try:
                before = len([call for call in self.h.transport.calls if call["path"] == "/profile"])
                report = _tool(self._call(client, access, "report_gates"))
                after = len([call for call in self.h.transport.calls if call["path"] == "/profile"])
                self.assertEqual(after - before, 1, role)
                nested = report["gates"]
                for key in ("live_ready", "credential_ready", "oauth_ready", "fieldwork_api_auth_verified", "writes_enabled", "approval_mode"):
                    self.assertEqual(report[key], nested[key], role)
                if role == "writer":
                    self.assertTrue(report["live_ready"])
                else:
                    self.assertFalse(report["live_ready"])
                self.assertEqual(nested["operations"]["update_work_order_notes"]["propose"], True)
                self.assertEqual(nested["operations"]["list_users"]["reason"], "not_implemented/not_live_verified")
            finally:
                client.__exit__(None, None, None)
        missing = replace(self._bridge_settings, oauth_issuer="", oauth_audience="", oauth_resource="", auth_mode="jwt", auth0_config_url="")
        self.h.service._readiness = None
        body = self.h.service.readiness(missing)
        self.assertFalse(body["live_ready"])
        self.assertEqual(body["live_ready"], body["gates"]["live_ready"])
        self.assertFalse(body["gates"]["oauth_ready"])

    def test_old_v7_proposal_is_not_executed_or_modified(self) -> None:
        self._prepare()
        record = {
            "proposal_id": "v7-old",
            "operation": "update_service_location_notes",
            "identity_sub": IDENTITY["sub"],
            "identity_email": IDENTITY["email"],
            "subject_key": "location:41:77",
            "before": {"notes": "old"},
            "after": {"notes": "new"},
            "payload": {"customer_id": 41, "location_id": 77, "notes": "new"},
            "digest": "a" * 64,
            "created_at": "2026-09-24T20:00:00Z",
            "expires_at": "2026-09-24T21:00:00Z",
        }
        self.h.store.create_proposal(record)
        client, access = self._session()
        try:
            result = _tool(self._call(client, access, "execute_approved_write", {"proposal_id": "v7-old", "approved": True, "expected_digest": "a" * 64}))
        finally:
            client.__exit__(None, None, None)
        self.assertEqual(result["reason"], "stored_proposal_digest_mismatch")
        stored = self.h.store.get_proposal("v7-old")
        self.assertEqual(stored["status"], "proposed")
        self.assertEqual(stored["digest"], "a" * 64)
        self.assertEqual(stored["expires_at"], record["expires_at"])
        self.assertFalse(any(call["method"] == "PATCH" for call in self.h.transport.calls))


if __name__ == "__main__":
    unittest.main()
