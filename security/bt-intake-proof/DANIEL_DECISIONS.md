# Stopped for Daniel — Desktop OAuth client

Authorized project: **bt-intake-proof**.

You already allowed only these four later creates in that project:

- Pub/Sub topic `bt-intake-proof-contactus`
- Pub/Sub subscription `bt-intake-proof-contactus-sub`
- Publisher on that topic for `gmail-api-push@system.gserviceaccount.com`
- Gmail `users.watch` for `contactus@btpestcontrol.com`

I have not created those yet. I have no Cloud admin login here, and Gmail consent is not done. If creating the topic requires billing, I will stop instead of linking a billing account.

## Do this now

Follow `OAUTH_CLIENT_GUIDE.md`, then reply with the Desktop OAuth client JSON.

I cannot show the Gmail OAuth URL until that JSON is here. I will request **gmail.readonly** only, with login hint `contactus@btpestcontrol.com`.

Do not send `BT-INTAKE-PROOF-*` emails until watch registration is PASS and I show project, mailbox, topic, subscription, history ID, and expiration.
