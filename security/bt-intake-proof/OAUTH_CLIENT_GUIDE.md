# Create the Desktop OAuth client in `bt-intake-proof`

Do this in Google Cloud Console. I will not create the OAuth client, consent screen, or billing for you.

Stay in project **bt-intake-proof**. If Google asks to link billing, stop and tell me.

## 1. Confirm the project

Open: https://console.cloud.google.com/?project=bt-intake-proof

The top bar should show **bt-intake-proof**.

## 2. Enable only the two APIs this test needs

If they are not already on:

- https://console.cloud.google.com/apis/library/gmail.googleapis.com?project=bt-intake-proof → **Enable**
- https://console.cloud.google.com/apis/library/pubsub.googleapis.com?project=bt-intake-proof → **Enable**

If either button demands billing, stop and tell me. Do not enable other APIs.

## 3. OAuth consent screen

Open: https://console.cloud.google.com/auth/overview?project=bt-intake-proof

If Google shows the older page, use: https://console.cloud.google.com/apis/credentials/consent?project=bt-intake-proof

Set:

- App name: `B&T intake proof`
- User support email: your B&T admin address
- Audience: **Internal** if B&T Workspace allows it. If it forces External, add **only** `contactus@btpestcontrol.com` as a test user.
- Do **not** add Gmail send, modify, compose, or `mail.google.com` scopes.

If you can add a scope on this screen, add only:

`https://www.googleapis.com/auth/gmail.readonly`

## 4. Create the Desktop client

Open: https://console.cloud.google.com/auth/clients?project=bt-intake-proof

Or: https://console.cloud.google.com/apis/credentials?project=bt-intake-proof → **Create credentials** → **OAuth client ID**

- Application type: **Desktop app**
- Name: `bt-intake-proof-contactus-readonly`
- Create
- **Download JSON**

The file should contain an `"installed"` object and `"project_id": "bt-intake-proof"`. If it says `"web"`, that is the wrong type.

## 5. Send it back

Reply with the downloaded JSON (paste or attach).

Then I will stop and show the Gmail OAuth URL. You sign in as **contactus@btpestcontrol.com** and approve read-only only.

Do not sign in as daniel@. Do not send `BT-INTAKE-PROOF-*` emails yet.
