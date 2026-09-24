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
- Key file: tmpfs `/run/bt-fieldwork-write-mcp/api-key` mode 0400, loaded in memory only, never copied into the repo or logs

## Required env (defaults stay fail-closed)

```
FIELDWORK_WRITES_ENABLED=0
FIELDWORK_MAPPING_VERIFIED=0
FIELDWORK_API_BASE=https://api3.fieldworkhq.com/v3.1
FIELDWORK_API_KEY_FILE=/run/bt-fieldwork-write-mcp/api-key
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

## Live blockers that remain after this offline code

1. Authorization server (OAuth 2.1) not configured; connector attach not done.
2. Fieldwork API auth unresolved (`Token token=...` 401 on customers).
3. Receiver SA cannot read `BT-fieldworks-key`; isolated write SA + one-secret IAM not applied.
4. Work-order path/occurrence ID mapping unverified.
5. Create-order response schema, remote idempotency, and arrival-window representation unverified.
6. Writes remain disabled by default.
