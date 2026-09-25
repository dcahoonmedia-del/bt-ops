"""Verified GET shapes and query-parameter auth. No live calls."""

from __future__ import annotations

import io
import unittest
import urllib.error
from urllib.request import Request

from bt_fieldwork_write_mcp.fieldwork import (
    FakeTransport,
    HttpTransport,
    TypedFieldworkClient,
    occurrence_ids,
    unwrap_occurrence,
    unwrap_service_location,
)
from bt_fieldwork_write_mcp.secrets import InMemoryApiKey


SECRET = "query-key-must-not-leak"


class _Capture:
    def __init__(self, status: int, body: bytes, headers: dict | None = None) -> None:
        self.status = status
        self._body = body
        self.headers = headers or {}
        self.requests: list[Request] = []

    def open(self, req: Request, timeout: int = 30):
        self.requests.append(req)
        if self.status >= 400:
            raise urllib.error.HTTPError(req.full_url, self.status, "boom-with-url", hdrs=None, fp=io.BytesIO(self._body))  # type: ignore[arg-type]
        return io.BytesIO(self._body)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._body


class ShapeTests(unittest.TestCase):
    def test_location_wrapper_and_patch_form(self) -> None:
        transport = FakeTransport()
        transport.add_customer(
            {"id": 9, "customer_status": "Active"},
            {"id": 3, "name": "Shop", "tax_rate_id": 4, "address": {"id": 8, "notes": "old"}},
        )
        client = TypedFieldworkClient(transport)
        location = client.get_location("9", "3")
        self.assertEqual(location["name"], "Shop")
        self.assertNotIn("service_location", location)
        client.patch_location_notes(
            {"customer_id": 9, "location_id": 3, "name": "Shop", "tax_rate_id": 4, "address_id": 8},
            "standing",
        )
        body = transport.calls[-1]["body"]["service_location"]
        self.assertEqual(body["name"], "Shop")
        self.assertEqual(body["tax_rate_id"], 4)
        self.assertEqual(body["address_attributes"]["id"], 8)
        self.assertEqual(body["address_attributes"]["notes"], "standing")

    def test_work_order_list_and_wrapped_pair(self) -> None:
        payload = {
            "appointment_occurrence": {
                "id": 100,
                "service_appointment_id": 200,
                "customer_id": 9,
                "service_location_id": 3,
                "arrival_time_window": ["2026-10-01T13:00:00Z", "2026-10-01T17:00:00Z"],
                "arrival_time_window_start": "2026-10-01T13:00:00Z",
                "arrival_time_window_end": "2026-10-01T17:00:00Z",
            }
        }
        row = unwrap_occurrence(payload)
        ids = occurrence_ids(payload)
        self.assertEqual(row["id"], 100)
        self.assertNotEqual(ids["work_order_id"], ids["service_appointment_id"])
        transport = FakeTransport()
        transport.work_orders["100"] = payload["appointment_occurrence"]
        client = TypedFieldworkClient(transport)
        listed = client.search_work_orders()
        self.assertIsInstance(listed, list)
        self.assertEqual(listed[0]["id"], 100)

    def test_query_param_auth_does_not_leak_on_http_error(self) -> None:
        capture = _Capture(401, b"{}")
        transport = HttpTransport(InMemoryApiKey(SECRET), opener=capture)
        status, _body = transport.request("GET", "/customers")
        self.assertEqual(status, 401)
        sent = capture.requests[0]
        self.assertIsNone(sent.get_header("Authorization"))
        self.assertIn("api_key=", sent.full_url)
        self.assertNotIn(SECRET, str(status))

    def test_redirect_and_transport_errors_hide_url(self) -> None:
        capture = _Capture(302, b"")
        transport = HttpTransport(InMemoryApiKey(SECRET), opener=capture)
        try:
            transport.request("GET", "/customers")
        except Exception as exc:
            text = f"{type(exc).__name__}:{exc}"
            self.assertNotIn(SECRET, text)
            self.assertNotIn("http", text.lower())
            self.assertNotIn("api_key", text)
        else:
            self.fail("redirect must fail closed")

    def test_unwrap_plain_location(self) -> None:
        self.assertEqual(unwrap_service_location({"id": 1})["id"], 1)
        self.assertEqual(unwrap_service_location({"service_location": {"id": 2}})["id"], 2)

