# LIVE-FW-READ-1 — bounded Fieldwork identity/context read

Offline matcher/adapter/runner: **PASS** (unit).  
Live Fieldwork on this Cursor VM: **BLOCKED**.  
Always-on receiver: **unchanged** (still `grok_bot_client()` fixture only).  
Draft / enqueue / send: **not invoked**.

This is not a live HQ pass. Fixture results stay `FIELDWORK_FIXTURE_VERIFIED` / `live=false`. They are never relabeled live.

## Offline scorecard

| Scenario | Result | Notes |
| --- | --- | --- |
| Multi-identifier match on synthetic case 1; property `14` does not select `214` | PASS | Fixture catalog only |
| Synthetic case 2 alternate payer/contact preserved on the customer record | PASS | Identity ≠ service property |
| Synthetic case 3 missing account status stays `unknown`, never `active` | PASS | |
| Ambiguity probe: multi-property without street | PASS | Abstain / `ambiguous_match_needs_daniel` |
| Ambiguity probe: street number does not uniquely resolve two properties | PASS | Abstain |
| Synthetic no-match `ZZZ-NO-CUSTOMER-PROOF-9F3A` after complete searches | PASS | Creates no record |
| Auth failure / schema mismatch | PASS | `blocked`, not no-match |
| Truncated pagination | PASS | `incomplete`, not no-match |
| Unscoped work-order page | PASS | Omitted; not “no appointments” |
| Fixture vs live provenance cannot be confused | PASS | |
| Case Manager still uses fixture client | PASS | `live_read_client()` is not imported there |
| Zero Fieldwork writes in fixture and runner | PASS | |
| Live preflight from this VM | **BLOCKED** | `live_read_not_enabled`; no host token consumed here |
| Live resolve of the 3 authorized labels | **BLOCKED** | This VM is not the approved host |
| Independent live native-ID comparison | **BLOCKED** | Same reason |

## Authorized live selection (host only)

Resolve only these project-referenced labels, through existing authorized access, as **identity/context candidates**. They are historical references, not current status and not permission to contact.

1. authorized_case_1
2. authorized_case_2
3. authorized_case_3

Plus at most two derived ambiguity probes from that same bounded set, and one synthetic no-match query. If a required identifier or multiple-property coverage is missing, that row is **BLOCKED** / unavailable — do not substitute another customer.

Private host artifacts (not in git):

- Manifest `0600`: `/var/lib/bt-intake-proof/live-fw-read/manifest.json`
- Evidence dir `0700`: `/var/lib/bt-intake-proof/live-fw-read/evidence/`

Public git has the example manifest and synthetic catalog only. No live customer names, emails, phones, streets, or note bodies belong in GitHub artifacts.

## Host commands (approved GCE host only)

Do not run these against this Cursor VM. Do not copy the API key, login, or live records here.

```bash
# After this branch is on the host tree. Does not deploy or restart the receiver.
export BT_FIELDWORK_LIVE_READ=1
export FIELDWORK_API_KEY_FILE=/var/lib/bt-intake-proof/secrets/fieldwork_api_key
export PYTHONPATH=src
cd /opt/bt-intake-proof

# 1) Token file exists and check_connection works. Never prints the token.
python3 -m bt_intake_proof.cli live-fw-preflight --mode live

# Optional, host secret boundary only, if a key file does not exist yet:
# python3 -m bt_intake_proof.cli live-fw-issue-key --file "$FIELDWORK_API_KEY_FILE"

# 2) Resolve the 3 authorized labels to native IDs. 0 or >1 hits → BLOCKED.
python3 -m bt_intake_proof.cli live-fw-resolve --mode live \
  --out /var/lib/bt-intake-proof/live-fw-read/manifest.json

# 3) Bounded read + independent native-ID comparison. Does not draft or send.
python3 -m bt_intake_proof.cli live-fw-read --mode live \
  --manifest /var/lib/bt-intake-proof/live-fw-read/manifest.json \
  --out /var/lib/bt-intake-proof/live-fw-read/evidence
```

Offline fixture equivalent (safe anywhere):

```bash
PYTHONPATH=src python3 -m bt_intake_proof.cli live-fw-preflight --mode fixture
PYTHONPATH=src python3 -m bt_intake_proof.cli live-fw-read --mode fixture \
  --manifest config/live_fw_read_manifest.example.json \
  --out /tmp/live-fw-read-fixture
```

## Remaining limitations

- Work-order search has no documented `filter[customer_id]`. Unscoped pages are omitted / incomplete, not treated as empty history.
- Provider token permission is not independently verified as read-only. The adapter enforces GET + allowlist + no other-host credential redirects.
- Browser / Mac Fieldwork sessions are not the live-read adapter and are not used.
- The always-on receiver is not switched to live Fieldwork.
- No scheduling, notes, estimates, customers, or mail writes.
- Date window is declared (`date_window_days`, default 365). Unsupported or omitted slices stay visible on the private scorecard.
- Missing digital agreements are not inferred into contract terms.

## Overall

| Layer | Result |
| --- | --- |
| Offline implementation + unit tests | PASS (recorded after the test run on this branch) |
| Live bounded read from this VM | **BLOCKED** |
| Milestone LIVE-FW-READ-1 live proof | **BLOCKED** until Codex runs the host commands and compares private evidence |
