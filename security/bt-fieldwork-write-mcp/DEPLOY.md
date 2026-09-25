# Isolated write-MCP deploy draft (APPLY NOTHING)

Verified host facts (do not change the receiver):

- Debian 12 e2-small, Python 3, no running containers
- `bt-intake-receiver.service` stays as `btintake` from `/opt/bt-intake-proof`, module `bt_intake_proof.cloud_host`
- Attached identity `bt-intake-proof-receiver@bt-intake-proof.iam.gserviceaccount.com` **cannot** access `BT-fieldworks-key`

This service is a **new** systemd unit and working tree. Do not install into `/opt/bt-intake-proof`. Do not touch receiver files.

## Proposed unit (not installed)

- Unit: `bt-fieldwork-write-mcp.service` (see `deploy/`)
- User: `btfwwrite` (new, not `btintake`)
- Root: `/opt/bt-fieldwork-write-mcp`
- Store: `/var/lib/bt-fieldwork-write-mcp/write.sqlite` (0600)
- Env file: `/etc/bt-fieldwork-write-mcp.env` (no API key value)
- API key: one in-memory Secret Manager read of `BT-fieldworks-key` (`FIELDWORK_USE_SECRET_MANAGER=1`). Env and key-file loads are offline-only and must not be the production path. Never copy the value into the repo or logs.

## Required env (defaults stay fail-closed)

```
FIELDWORK_WRITES_ENABLED=0
FIELDWORK_MAPPING_VERIFIED=0
FIELDWORK_API_BASE=https://api3.fieldworkhq.com/v3.1
FIELDWORK_USE_SECRET_MANAGER=1
FW_WRITE_STORE=/var/lib/bt-fieldwork-write-mcp/write.sqlite
FW_WRITE_TRANSPORT=http
FW_WRITE_OAUTH_ISSUER=
FW_WRITE_OAUTH_AUDIENCE=
FW_WRITE_OAUTH_RESOURCE=
FW_WRITE_OAUTH_JWKS_URL=
FW_WRITE_REQUIRED_SCOPES=fieldwork.write
FW_WRITE_PERMITTED_USERS=daniel@btpestcontrol.com
FW_WRITE_OPERATOR_KEY=   # independent HMAC key; not the Fieldwork secret
```

`FIELDWORK_WRITES_ENABLED` must stay `0` until Fieldwork API auth is proven on a real GET that requires the key. Do not treat `GET /check_connection` 204 as proof.

## Do not

- Deploy this unit
- Enable writes
- Call live Fieldwork
- Change IAM (see `IAM.md` draft only)
- Share or log the secret value
- Attach the write MCP to the existing hosted read-only Fieldwork MCP URL
- Restart or edit `bt-intake-receiver.service`

## Auth0 offline access (reuse the existing store)

Codex saved Allow Offline Access on the Auth0 API. Set `FW_WRITE_AUTH0_OFFLINE_ACCESS=1`. The bridge adds `offline_access` to the upstream authorize request and does not require that scope on the access token, so sessions issued before the upgrade keep working. A refresh token appears only after one new authorization.

Keep the current values. Do not rotate them for this change:

```
FW_WRITE_AUTH0_STORAGE_PATH=/var/lib/bt-fieldwork-write-mcp/auth0
FW_WRITE_AUTH0_STORAGE_KEY=<existing Fernet key>
FW_WRITE_AUTH0_JWT_SIGNING_KEY=<existing signing key>
```

`report_gates` shows whether those three are configured, `offline_access_requested`, and `offline_access_required_on_access_token: false`. This process does not observe the Auth0 dashboard.

## Identity and hosting (not applied)

The existing VM has only the receiver service account. A second Unix user is not cloud isolation. Do not grant that receiver identity the Fieldwork secret. Hosting and the public domain are not selected. Google social login in the local Auth0 proof used Auth0 development keys; production social credentials are a deployment gate. The Auth0 bridge is optional, off by default, and this checkout does not change Auth0, IAM, or cloud settings.

## Live blockers that remain after this offline code

1. Authorization server (OAuth 2.1) not configured; connector attach not done.
2. Current Fieldwork credential readiness is not live-verified. Historical GET protocol used the `api_key` query parameter. `check_connection` is not proof. The attached receiver identity cannot read the secret.
3. Receiver SA cannot read `BT-fieldworks-key`; isolated write SA + one-secret IAM not applied.
4. Work-order path/occurrence ID mapping unverified.
5. Create-order response schema, remote idempotency, and arrival-window representation unverified.
6. Writes remain disabled by default.
