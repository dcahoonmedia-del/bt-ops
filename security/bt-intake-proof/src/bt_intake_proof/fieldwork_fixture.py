"""Read-only historical Fieldwork catalog. Not live HQ."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .fieldwork_readonly import FieldworkWriteForbidden, ReadOnlyFieldworkClient, _path_allowed, redact

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "config" / "phased_fieldwork_catalog.json"


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[-10:]


def load_catalog_blob(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or CATALOG).read_text(encoding="utf-8"))


def load_catalog(path: Path | None = None) -> list[dict[str, Any]]:
    return list(load_catalog_blob(path).get("customers") or [])


class GrokBotFieldwork(ReadOnlyFieldworkClient):
    """Read-only searches against the selected historical fixture catalog."""

    def __init__(self, customers: list[dict[str, Any]] | None = None, snapshot: str | None = None) -> None:
        super().__init__(token="fixture-grok-bot", getter=self._lookup)
        self.blob = load_catalog_blob()
        self.snapshot = snapshot or str(self.blob.get("default_snapshot") or "pre_booking")
        self.customers = customers if customers is not None else load_catalog()
        self.identity = {
            "name": "Grok Bot",
            "user_id": 242798,
            "mode": "read_only_fixture",
            "label": "FIELDWORK_FIXTURE_VERIFIED",
            "live": False,
            "snapshot": self.snapshot,
        }

    def snapshot_meta(self) -> dict[str, Any]:
        return dict((self.blob.get("snapshots") or {}).get(self.snapshot) or {})

    def _materialize(self, row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        by_snap = row.get("work_orders_by_snapshot")
        if isinstance(by_snap, dict):
            out["work_orders"] = list(by_snap.get(self.snapshot) or [])
        return out

    def _lookup(self, path: str, params: dict[str, Any]) -> Any:
        if not _path_allowed(path):
            raise FieldworkWriteForbidden(path)
        if path == "/v3.1/customers/search":
            return self._search(str(params.get("query") or ""), params.get("filter[customer_status]"))
        if path == "/v3.1/customers/search_by_phone":
            return self._search_phone(str(params.get("phone") or ""))
        if path.startswith("/v3.1/customers/") and path.endswith("/service_locations"):
            return self._by_id(path.split("/")[3]).get("locations") or []
        if path.startswith("/v3.1/customers/") and path.endswith("/contacts"):
            return self._by_id(path.split("/")[3]).get("contacts") or []
        if path.startswith("/v3.1/customers/") and path.endswith("/notes"):
            note = self._by_id(path.split("/")[3]).get("notes") or ""
            return [{"body": note}] if note else []
        if path.startswith("/v3.1/customers/") and path.count("/") == 3:
            return self._by_id(path.split("/")[3])
        if path == "/v3.1/work_orders/search":
            cid = str(params.get("filter[customer_id]") or "")
            return list(self._by_id(cid).get("work_orders") or [])
        if path == "/v3.1/service_agreement_setups":
            cid = str(params.get("filter[customer_id]") or "")
            return list(self._by_id(cid).get("agreements") or [])
        if path == "/v3.1/estimates":
            return []
        return []

    def _by_id(self, customer_id: str) -> dict[str, Any]:
        for row in self.customers:
            if str(row.get("id")) == str(customer_id):
                return self._materialize(row)
        return {}

    def _search(self, query: str, status: str | None) -> list[dict[str, Any]]:
        needle = query.strip().lower()
        phone = _digits(query)
        out = []
        for raw in self.customers:
            row = self._materialize(raw)
            if status and str(row.get("customer_status") or "").lower() != status.lower():
                continue
            blob = " ".join(
                [
                    str(row.get("name") or ""),
                    str(row.get("email") or ""),
                    str(row.get("phone") or ""),
                    json.dumps(row.get("locations") or []),
                    json.dumps(row.get("contacts") or []),
                ]
            ).lower()
            if needle and needle in blob:
                out.append(row)
            elif phone and phone == _digits(row.get("phone")):
                out.append(row)
        return redact(out)

    def _search_phone(self, phone: str) -> list[dict[str, Any]]:
        want = _digits(phone)
        return redact(
            [
                self._materialize(row)
                for row in self.customers
                if _digits(row.get("phone")) == want
                or any(_digits((loc.get("address") or {}).get("phone")) == want for loc in row.get("locations") or [])
            ]
        )
