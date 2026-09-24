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

Needs Python 3, `mcp>=1.0`, `PyJWT>=2.7`. No network, GCP, or Fieldwork access.

Local HEAD: `cc16bf4c77eadd820c788ae114d4f55daf0929da` (cleanup). Implementation commit: `4c935a8e7385e2ac727d9a09a1e41a9e6253f790`.  
Until a push is authorized, Codex can retrieve this workspace at those SHAs (`git show cc16bf4`). After an authorized push: `git fetch origin cursor/bt-fw-write-mcp-e9a8 && git checkout cursor/bt-fw-write-mcp-e9a8`.

## What Codex should independently confirm

- Default writes disabled; `approved=true` is not an approval.
- Identity mismatch, unknown fields, stale/expired/replayed approvals, concurrent duplicates, crash/ambiguous no-retry, failed readback, rejected OAuth.
- Work-order notes and create-order execute fail closed and report mapping/schema gates.
- No customer create, Lead-status write, messaging, or HTTP passthrough tools.
- Secret value never appears in repr, audit, or tool results.
- Do not call live Fieldwork. Do not treat this package as live-ready.

## Remaining live blockers

OAuth authorization-server + connector attach; Fieldwork API auth (401 on token GET; `check_connection` is not proof); isolated SA + one-secret IAM not applied; mapping/schema/arrival-window unverified; writes disabled.
