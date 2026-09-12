# Stopped for Daniel — project-owner Cloud login for impersonation

A JSON service-account key was **not** created.

This VM has no Google Cloud metadata identity and no Application Default Credentials. Impersonation of `bt-intake-proof-receiver` needs a short-lived project-owner Cloud login first. That is not a Gmail send/modify grant.

## Open this URL

Sign in as **daniel@btpestcontrol.com** (project owner). Do **not** sign in as contactus@.

https://accounts.google.com/o/oauth2/v2/auth?client_id=1028131400538-5r57fq95el2uhmmtp2m38m3lgab7loa8.apps.googleusercontent.com&redirect_uri=http%3A%2F%2Flocalhost&response_type=code&scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fcloud-platform&access_type=offline&prompt=consent&include_granted_scopes=false&login_hint=daniel%40btpestcontrol.com

Requested scope: `https://www.googleapis.com/auth/cloud-platform` only, so I can:

1. Create service account `bt-intake-proof-receiver`
2. Grant `roles/pubsub.subscriber` on `bt-intake-proof-contactus-sub` only
3. Impersonate that account
4. Pull

If Google says this app cannot request Cloud scopes, stop and tell me. Do not download a key. After approve, send the localhost address-bar URL.

Do not send `BT-INTAKE-PROOF-*` emails yet.
