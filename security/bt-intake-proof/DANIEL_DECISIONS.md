# Stopped for Daniel — create the Google Cloud project

You do need a real Google Cloud project. `<PUT_PROJECT_ID_HERE>` was a placeholder, so I did not use it. I still do not have the Desktop OAuth client JSON.

I will not create the project, enable billing, or pick an existing project for you.

## Already authorized (once a real project ID exists)

You already allowed me to create **only** these four things in the project you name:

- Pub/Sub topic `bt-intake-proof-contactus`
- Pub/Sub subscription `bt-intake-proof-contactus-sub`
- Publisher permission for `gmail-api-push@system.gserviceaccount.com` on that topic
- Gmail `users.watch` for `contactus@btpestcontrol.com`

Nothing else.

## What you build now

Use a Google account that can administer B&T Cloud/Workspace. Suggested name: **B&T Intake Proof**. Suggested ID: `bt-intake-proof`.

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create a **new project**.
2. Copy the **Project ID** (not just the display name). It looks like `bt-intake-proof` or `bt-intake-proof-123456`.
3. If Google asks to **enable billing**, stop and tell me before you do it — unless you already want billing on and will enable it yourself.
4. In that project, enable only these APIs:
   - [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com)
   - [Cloud Pub/Sub API](https://console.cloud.google.com/apis/library/pubsub.googleapis.com)
5. **APIs & Services → OAuth consent screen**
   - User type: **Internal** if B&T Workspace allows it
   - App name: `B&T intake proof`
   - Do not add Gmail send/modify scopes
6. **APIs & Services → Credentials → Create credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Download the JSON

## Reply here with

1. The real **project ID**
2. The Desktop OAuth client JSON (paste or attach)

Then I will show you the Gmail OAuth URL. You sign in as **contactus@btpestcontrol.com** and approve **read-only** only. Do not use daniel@.

Do not send any `BT-INTAKE-PROOF-*` emails until I confirm watch registration **PASS** and show project, mailbox, topic, subscription, history ID, and expiration.
