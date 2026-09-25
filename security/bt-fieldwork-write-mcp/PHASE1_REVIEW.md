# Phase 1 review fixes

Bounded to the ChatGPT approval contract. No live Fieldwork calls, writes, or deploy.

1. Bridge and direct-JWT instructions and `execute_approved_write` say: read, propose, inspect and show the exact before and after, obtain explicit user approval, execute with `approved=true` and that exact digest, then show live readback.
2. `WriteService.readiness` performs one profile read and one auth snapshot. `report_gates` returns that snapshot. Top-level and nested `live_ready`, credentials, oauth, role auth, writes, and approval mode are the same values. `live_ready` requires a present API key, a usable auth configuration, a verified writer role, the writes flag, and `chatgpt_confirmation`. Any other approval mode is reported as `unsupported`.
3. Work-order `propose` metadata follows mapping verification only. A draft can still be prepared while writes are disabled. Execute still enforces the writes flag.
4. `list_users` stays unread. The reason is `not_implemented/not_live_verified` because Swagger documents `GET /v3.1/users` and this connector has not verified that call.
5. MCP `execute_approved_write` has no operator-approval parameter. If `FW_WRITE_APPROVAL_MODE` is not `chatgpt_confirmation`, the tool returns `approval_mode_unsupported` and does not run. HMAC minting remains on the internal CLI.
6. The proposal digest binds proposal id, payload, before, after, identity, target, `created_at`, and `expires_at`. A stored row whose digest does not match that binding, including an older v7 digest, is rejected and left unchanged.
