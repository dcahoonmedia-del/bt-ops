# LIVE-FW-READ-1 — host credential prerequisite

This runner does **not** mint, export, or refresh Fieldwork credentials. `live-fw-issue-key` is not part of this milestone. Browser / Mac Fieldwork sessions are not an adapter.

Host inspection for this milestone found **no** `FIELDWORK_*` names in `/etc/bt-intake-proof/env` and **no** Fieldwork secret file in the established secret directories. Live host execution is **BLOCKED** until project lead places an **already authorized** credential into the host secret boundary.

## Required before live-fw-preflight

1. Project lead confirms an existing authorized Fieldwork API credential (not a new access grant from this agent).
2. The credential is written on the approved GCE host only, as user `btintake`, mode `0600`, path chosen by project lead (example shape only: `/var/lib/bt-intake-proof/secrets/fieldwork_api_key`).
3. `/etc/bt-intake-proof/env` (or the receiver-safe overlay used for this explicit runner) sets:
   - `BT_FIELDWORK_LIVE_READ=1` for the one-shot runner only
   - `FIELDWORK_API_KEY_FILE=<that 0600 path>`
4. The always-on receiver environment is **not** switched to live Fieldwork.
5. The private manifest with source-evidence identifiers and selected property IDs is supplied on the host at `0600`. Real customer content stays off git.

Do not copy the credential, login, or live records to this Cursor VM. Do not use email/password login from this runner. Do not use the browser session.
