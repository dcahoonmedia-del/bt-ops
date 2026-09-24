# Codex handoff — Fieldwork write MCP (offline)

Branch: `cursor/bt-fw-write-mcp-e9a8` (local until Daniel authorizes a push).  
Base: `cursor/bt-intake-plus-ctrl-e9a8` @ `80dafaeaf8f72a900902fe55b1d49119803c3869`.  
Lead Desk, read-only Fieldwork, and receiver files were not modified.

## Retrieve and run tests

From a checkout that contains this commit:

```
cd security/bt-fieldwork-write-mcp
python3 -m pip install -r requirements.txt
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

or:

```
bash security/bt-fieldwork-write-mcp/scripts/run_offline_tests.sh
```

Needs Debian 12 Python 3.11+ (this SDK line requires Python >=3.10), `mcp>=2.2.0,<3` (`mcp.server.mcpserver`), and the rest of `requirements.txt`. No network, GCP, or Fieldwork access. MCP 1.x cannot import the server entry point.

This checkout is local only. Do not push. Retrieve the review archive from the base64 text file, not from GitHub.

## What Codex should independently confirm

- Default writes disabled; readonly role blocks execute; `approved=true` is not an approval.
- GET auth is `api_key` query parameter. Do not log URLs or HTTP exception strings.
- Identity mismatch, unknown fields, stale/expired/replayed approvals, concurrent duplicates, crash/ambiguous no-retry, failed readback, rejected OAuth.
- Work-order notes propose returns `live_patch_untested` with no before/after. Create-order execute stays `work_order_schema_unverified`.
- No customer create, Lead-status write, messaging, or HTTP passthrough tools.
- Secret value never appears in repr, audit, or tool results.
- Do not call live Fieldwork. Do not treat this package as live-ready.

## Remaining live blockers

Direct JWT mode remains the default. The optional Auth0 bridge (`FW_WRITE_AUTH_MODE=auth0_bridge`) uses FastMCP `Auth0Provider` and stays off until external HTTPS, consent, PKCE, exact callbacks, audience, encrypted durable storage, and a signing key are all present. Offline tests of that bridge are not live Auth0 or ChatGPT success.

The existing VM has only the receiver service account. A second Unix user is not cloud isolation. Do not grant the receiver the Fieldwork secret. Hosting and domain are not selected. Production Google social credentials are still a deployment gate; the local sign-in used Auth0 development keys.

OAuth authorization server is not configured for production. Current Fieldwork credential readiness is not live-verified (`check_connection` is not proof). Isolated SA and one-secret IAM are not applied. Live PATCH, create schema, and arrival-window writes are unverified. Writes stay disabled. `credential_ready` is not live readiness.
