# Stopped for Daniel — Cloud permission for Pub/Sub

## Completed

- Project: `bt-intake-proof`
- Gmail sign-in: **contactus@btpestcontrol.com**
- Scope: `gmail.readonly` only
- Refresh token stored in gitignored secrets
- `daniel@` was not used

## Blocked

`users.watch` needs topic `bt-intake-proof-contactus`. Creating that topic with the Gmail read-only token failed:

`ACCESS_TOKEN_SCOPE_INSUFFICIENT` for `CreateTopic`

That is a **broader permission** than you authorized for Gmail. I did not request Cloud scopes, link billing, or create any Pub/Sub resource.

## Choose one

1. **You create the three authorized Pub/Sub resources** in Cloud Console. Follow `PUBSUB_CONSOLE_GUIDE.md`, then tell me they exist. I will register watch.
2. **You authorize a separate Cloud login** that can create only:
   - topic `bt-intake-proof-contactus`
   - subscription `bt-intake-proof-contactus-sub`
   - Publisher for `gmail-api-push@system.gserviceaccount.com` on that topic  
   This is not a Gmail send/modify grant. Say yes if you want me to start that Cloud consent.

If Google asks to link billing on the project, tell me instead of letting me pick a billing account.

Do not send `BT-INTAKE-PROOF-*` emails yet. Watch is not PASS.
