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
- Work-order notes do not persist a proposal. Typed read and identity relationships are not validated, so propose returns `live_patch_untested` with no before/after. Execute stays blocked. Live PATCH is untested.
- Create work order: response schema / remote idempotency / arrival-window representation are **unverified**. Execute reports `work_order_schema_unverified`. `use_time_window` is rejected as `arrival_window_unverified` so start/finish is not treated as a promised arrival window.
- No customer create. No Lead-status accounts. No `on_our_way` or messaging tools. No generic HTTP passthrough.

## Auth

- Resource-server JWT checks: issuer, audience, expiry, required scopes, permitted user.
- This process does not issue tokens. Authorization-server setup and live connector attach remain deployment gates.
- Homemade static bearer keys are rejected.
- Fieldwork GET auth is the `api_key` query parameter. Header `Authorization: Token token=...` is not used. Codex verified profile without key 401, with key 200, customer list 200. The key is a readonly API user. `GET /check_connection` is still not auth proof. This process does not call live HQ. URLs and HTTP exception text are never logged.
- GET `/work_orders` is an array. GET `/work_orders/{id}` and `/show_plain` wrap `{appointment_occurrence:{id, service_appointment_id, ...}}`. Three live samples showed distinct matching pairs. PATCH URL is the service-appointment id and nested occurrence `id` is the work-order id; live PATCH is untested, so execute stays closed (`live_patch_untested`).
- GET service location wraps `{service_location:{id,name,tax_rate_id,address:{id,notes}}}`. PATCH form keeps name, tax_rate_id, and address id via `address_attributes`.
- Arrival-window READ fields are known. The write contract is unknown, so schedule and create stay closed. Writes stay disabled. Readonly role blocks execute even if the writes flag is turned on.

## Secret

- Name only: `BT-fieldworks-key`.
- Future resource: `projects/bt-intake-proof/secrets/BT-fieldworks-key/versions/latest`.
- Production reads one secret, `projects/bt-intake-proof/secrets/BT-fieldworks-key/versions/latest`, through the Secret Manager client into `InMemoryApiKey`. Exceptions are replaced with `secret_read_failed` and are not chained. Env and file loads are offline-only. This package does not call GCP in tests.
