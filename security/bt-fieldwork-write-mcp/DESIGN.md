# Fieldwork write MCP (offline design)

Isolated sibling of Lead Desk and the existing read-only Fieldwork client. This package does not import or patch `bt_intake_proof`.

## What is implemented

- Official MCP SDK `MCPServer` plus `TokenVerifier` / `AuthSettings` (OAuth 2.1 resource server).
- Typed operations only: standing location notes; existing-order notes; create work order.
- Immutable exact-before/after proposals bound to OAuth `sub`+`email`.
- Independent HMAC operator approval. Model `approved=true` is ignored.
- Durable SQLite audit, subject guards, and no-retry after ambiguous remote writes or process restart with an in-flight attempt.
- Stale-state rejection and readback-before-success for location notes.
- Writes disabled by default. Mapping/schema flags default false.

## Fail-closed (honest, not stub-as-verified)

- Location notes: typed GET/PATCH against an injected transport. Offline tests use `FakeTransport`. Live HQ is not called here.
- Work-order notes: path ID vs nested occurrence ID mapping is **unverified**. Execute reports `work_order_id_mapping_unverified` and does not PATCH.
- Create work order: response schema / remote idempotency / arrival-window representation are **unverified**. Execute reports `work_order_schema_unverified`. `use_time_window` is rejected as `arrival_window_unverified` so start/finish is not treated as a promised arrival window.
- No customer create. No Lead-status accounts. No `on_our_way` or messaging tools. No generic HTTP passthrough.

## Auth

- Resource-server JWT checks: issuer, audience, expiry, required scopes, permitted user.
- This process does not issue tokens. Authorization-server setup and live connector attach remain deployment gates.
- Homemade static bearer keys are rejected.
- Fieldwork `Authorization: Token token=...` remains unresolved live (401 on `GET /v3.1/customers?per_page=1`). `GET /check_connection` 204 without a key is **not** auth proof.

## Secret

- Name only: `BT-fieldworks-key`.
- Future resource: `projects/bt-intake-proof/secrets/BT-fieldworks-key/versions/latest`.
- Runtime loads env/file into `InMemoryApiKey`. Never logs or returns the value. This package does not call Secret Manager.
