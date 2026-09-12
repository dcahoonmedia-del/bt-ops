# Bounded live walkthrough (later review only)

**Do not run this now.** This milestone used synthetic records on a throwaway
SQLite file. Production `/var/lib/bt-intake-proof/receipts.sqlite` was not
opened. Actions 1 and 2 stay untouched.

Customer sends remain OFF. Broad / shadow capture remains OFF. No Fieldwork
writes, scheduling, Grok cutover, new OAuth, or new service.

## Further approval required?

| Later message | Further approval required? |
| --- | --- |
| Any customer-facing email | **Yes.** Not granted here. Exact version-bound approval still required. |
| Any new `BT-DESK-ROUNDTRIP-SEND-E9A8` or other internal proof send | **Yes.** Action 2 already sent and receipt-verified. Do not resend. Do not recover `--execute`. |
| New isolated CASEMGR inbound inserted into live SQLite | **Yes, and not authorized here.** Do not insert live fixtures. |
| Internal CASE / RESULT packet contactus → daniel | **Yes.** Not authorized by this pack. |
| `--verify-recipient --enqueue-result` on action 2 | Already done on the reporting release. Do not repeat unless Daniel asks. |
| This isolated unit pack | **No live message.** Local temp store only. |

## If Daniel later wants a live office-acceptance review
1. Keep isolated `BT-INTAKE-PROOF-*` filters on.
2. Do not copy this pack's synthetic rows into production SQLite.
3. Use a **new** isolated marker inbound from daniel@ to contactus@, or a
   separately authorized CASE packet, after Daniel says to proceed.
4. ChatGPT interprets speech and sends one existing structured control
   (`hold`, `office_owned` + Brenda/Ally, `revise_draft`). Backend authorizes
   the exact current binding only.
5. Any send still needs a fresh exact packet approval. Office ownership or
   hold must continue to block competing send.
6. Stop and wait for Daniel to report completion.

No message in this milestone is authorized to leave the isolated pack.
