# Office-ownership acceptance (isolated)

Isolation: throwaway SQLite. Customer sends OFF. Broad capture OFF.
Runtime `src/` was not changed. No immutable host release.

## Codex-observed (separate)

See `CODEX_OBSERVED_RECEIPT.md`. Reporting artifact `5af92d6e…` deployed.
Action 2 `recipient_receipt_verified`. RESULT `1a096c49ac2dd383`. Not a unit test.

## Scenarios

| # | Scenario | Result | Evidence |
| --- | --- | --- | --- |
| 1 | New inquiry → reviewable draft, no invented price or appointment | **PASS** (unit / fixture) | `tests/test_office_accept.py`; conservative draft; invented contrast kept for review and not sent |
| 2 | Existing customer service issue stays eligible | **PASS** (unit / fixture) | `existing_customer_service_issue` visible; case + draft created |
| 3 | Brenda, Ally, and hold block competing send | **PASS** (unit / fixture) | `approve_and_send_current` blocked; no queued action |
| 4 | New inbound / changed draft invalidates old authorization | **PASS** (unit / fixture) | Approval superseded; version 1 cannot authorize |
| 5 | Repeat decision / restart, no duplicate action | **PASS** (unit / fixture) | Same `gmail_message_id` skipped/replayed; one decision; no send |

## Unsupported / blocked
| Item | Result |
| --- | --- |
| Live unmarked customer mail | **BLOCKED** — isolated harness still on |
| Generic `office` owner without Brenda/Ally | **UNSUPPORTED** — existing policy; use `hold` |
| Backend price/appointment phrase parser | **UNSUPPORTED** — not added; pack-local reviewer check only |
| Live Codex `host_case_draft` | **BLOCKED** — not invoked |
| Live voice / phone / Mac-off | **BLOCKED** — walkthrough is simulated |
| This VM live deploy / SQLite insert | **BLOCKED** / not requested |
| Customer or proof send | **BLOCKED** — none authorized |

## How to re-run
```
cd security/bt-intake-proof
PYTHONPATH=src python3 -m unittest tests.test_office_accept
python3 scripts/write_office_accept_artifacts.py results/office-accept
```

User-facing case/owner/draft/outcome: `REVIEW_ARTIFACT.md` (LeadDesk) plus the
existing review-email shape in `format_review_email`.
